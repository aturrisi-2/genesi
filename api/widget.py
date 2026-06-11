"""
Widget API — endpoint per il widget embeddabile.
Autenticazione tramite API key aziendale (X-Widget-Key header).
"""
import os
import re as _re
import shutil
import time
import logging
from collections import defaultdict
from pathlib import Path
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
import httpx

try:
    import jwt as _jwt
except ImportError:
    _jwt = None  # type: ignore

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/widget", tags=["widget"])

GENESI_URL = os.getenv("BASE_URL", "http://localhost:8000")
_OPENROUTER_KEY = os.getenv("OPENROUTER_API_KEY", "")
_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

# ── Caricamento configurazioni widget da env ──────────────────────────────────
# Singola chiave: WIDGET_API_KEY / WIDGET_EMAIL / WIDGET_PASSWORD
# Multi-chiave:   WIDGET_KEYS=chiave1:email1:pass1,chiave2:email2:pass2

_WIDGET_CONFIGS: dict[str, dict] = {}

# ── Visual config per chiave: api_key → {name, color, welcome, position, placeholder, allowed_domains} ──
_WIDGET_VISUAL: dict[str, dict] = {}

# ── Usage tracking: api_key → {calls, last_call, created_at, label} ──────────
_WIDGET_USAGE: dict[str, dict] = {}

# ── Rate limiting per demo key: ip → [timestamp, ...] ────────────────────────
_RATE_BUCKETS: dict[str, list] = defaultdict(list)
_RATE_LIMIT_KEYS: set[str] = set()   # chiavi soggette a rate limit (caricate da env)
_RATE_MAX    = int(os.getenv("WIDGET_RATE_MAX", "20"))    # max messaggi
_RATE_WINDOW = int(os.getenv("WIDGET_RATE_WINDOW", "86400"))  # finestra secondi (default 24h)

_WIDGET_ADMIN_TOKEN = os.getenv("WIDGET_ADMIN_TOKEN", "")
_JWT_SECRET         = os.getenv("JWT_SECRET", "")


def _load_configs():
    """Popola _WIDGET_CONFIGS da env. Può essere chiamata più volte (idempotente)."""
    _WIDGET_CONFIGS.clear()

    key  = os.getenv("WIDGET_API_KEY", "")
    mail = os.getenv("WIDGET_EMAIL", "")
    pw   = os.getenv("WIDGET_PASSWORD", "")
    if key and mail and pw:
        _WIDGET_CONFIGS[key] = {"email": mail, "password": pw}
        _WIDGET_USAGE.setdefault(key, {"calls": 0, "last_call": None, "created_at": time.time(), "label": key})

    for entry in os.getenv("WIDGET_KEYS", "").split(","):
        parts = entry.strip().split(":")
        if len(parts) == 3:
            k, e, p = parts
            k = k.strip()
            _WIDGET_CONFIGS[k] = {"email": e.strip(), "password": p.strip()}
            _WIDGET_USAGE.setdefault(k, {"calls": 0, "last_call": None, "created_at": time.time(), "label": k})

    # Chiavi soggette a rate limit (es. chiavi demo)
    for k in os.getenv("WIDGET_RATE_LIMITED_KEYS", "").split(","):
        k = k.strip()
        if k:
            _RATE_LIMIT_KEYS.add(k)

    # Inizializza _WIDGET_VISUAL con defaults per ogni chiave (se non già presente)
    for key in list(_WIDGET_CONFIGS.keys()):
        _WIDGET_VISUAL.setdefault(key, {
            "name": "Assistente",
            "color": "#7c3aed",
            "welcome": "Ciao! Come posso aiutarti oggi?",
            "position": "bottom-right",
            "placeholder": "Scrivi un messaggio...",
            "allowed_domains": [],
        })


_load_configs()


def _check_rate_limit(api_key: str, client_ip: str):
    """Blocca richieste in eccesso per chiavi demo (rate-limited)."""
    if api_key not in _RATE_LIMIT_KEYS:
        return
    now = time.time()
    bucket_key = f"{api_key}:{client_ip}"
    timestamps = _RATE_BUCKETS[bucket_key]
    # Rimuovi timestamp fuori finestra
    _RATE_BUCKETS[bucket_key] = [t for t in timestamps if now - t < _RATE_WINDOW]
    if len(_RATE_BUCKETS[bucket_key]) >= _RATE_MAX:
        raise HTTPException(
            status_code=429,
            detail=f"Limite demo raggiunto ({_RATE_MAX} messaggi/giorno). Contattaci per l'accesso completo."
        )
    _RATE_BUCKETS[bucket_key].append(now)

# JWT cache: api_key → {token, expires_at}
_token_cache: dict[str, dict] = {}


async def _get_token(api_key: str) -> str:
    if api_key not in _WIDGET_CONFIGS:
        raise HTTPException(status_code=401, detail="API key non valida")

    cached = _token_cache.get(api_key)
    if cached and cached["expires_at"] > time.time() + 300:
        return cached["token"]

    cfg = _WIDGET_CONFIGS[api_key]
    async with httpx.AsyncClient(timeout=15) as client:
        res = await client.post(
            f"{GENESI_URL}/auth/login",
            json={"email": cfg["email"], "password": cfg["password"]},
        )
    if res.status_code != 200:
        logger.error("WIDGET_AUTH_FAILED key=%s", api_key[:8])
        raise HTTPException(status_code=503, detail="Autenticazione widget fallita")

    token = res.json().get("access_token", "")
    # 30 giorni (allineato con ACCESS_TOKEN_EXPIRE_MINUTES=43200)
    _token_cache[api_key] = {"token": token, "expires_at": time.time() + 43200 * 60}
    logger.info("WIDGET_TOKEN_REFRESHED key=%s", api_key[:8])
    return token


# ── Helper: estrai link dal contesto pagina ───────────────────────────────────

def _extract_page_links(page_context: str) -> dict[str, str]:
    """Ritorna {testo_link: url} dalla sezione LINK DISPONIBILI NELLA PAGINA."""
    link_map: dict[str, str] = {}
    if not page_context or "LINK DISPONIBILI NELLA PAGINA:" not in page_context:
        return link_map
    section = page_context.split("LINK DISPONIBILI NELLA PAGINA:", 1)[1]
    for line in section.strip().split("\n"):
        line = line.strip().lstrip("- ")
        if ": http" in line:
            parts = line.rsplit(": ", 1)
            if len(parts) == 2:
                text, url = parts[0].strip(), parts[1].strip()
                if text:
                    link_map[text] = url
    return link_map


async def _find_best_link(user_message: str, link_map: dict[str, str]) -> Optional[tuple[str, str]]:
    """
    Usa il LLM per trovare il link più pertinente al messaggio utente.
    Restituisce (testo, url) oppure None se nessun link è rilevante.
    """
    if not link_map:
        return None

    # Costruisce lista numerata per parsing deterministico
    items = list(link_map.items())
    links_list = "\n".join(f"{i+1}. {text}" for i, (text, _) in enumerate(items))
    prompt = (
        f"Messaggio utente: \"{user_message}\"\n\n"
        f"Quale di questi link del portale intranet è più pertinente alla domanda?\n"
        f"Rispondi SOLO con il numero (1-{len(items)}) oppure 0 se nessuno è pertinente.\n\n"
        f"{links_list}"
    )

    if _OPENROUTER_KEY:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                res = await client.post(
                    _OPENROUTER_URL,
                    headers={"Authorization": f"Bearer {_OPENROUTER_KEY}"},
                    json={
                        "model": "openai/gpt-4o-mini",
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": 5,
                        "temperature": 0,
                    },
                )
            if res.status_code == 200:
                raw = res.json()["choices"][0]["message"]["content"].strip()
                # Estrai primo numero dalla risposta
                m = _re.search(r"\d+", raw)
                if m:
                    idx = int(m.group()) - 1
                    if 0 <= idx < len(items):
                        logger.info("WIDGET_LLM_LINK_MATCH idx=%d text=%r", idx + 1, items[idx][0])
                        return items[idx]
                logger.info("WIDGET_LLM_LINK_MATCH none (raw=%r)", raw)
                return None
        except Exception as exc:
            logger.debug("WIDGET_LLM_LINK_ERROR: %s", exc)

    # Fallback keyword se OpenRouter non disponibile
    msg_words = set(_re.sub(r"[^\w\s]", " ", user_message.lower()).split())
    best_score = 0
    best_item: Optional[tuple[str, str]] = None
    for text, url in items:
        words = [w for w in _re.sub(r"[^\w\s]", " ", text.lower()).split() if len(w) > 3]
        score = sum(1 for w in words if w in msg_words)
        if score > best_score:
            best_score = score
            best_item = (text, url)
    return best_item if best_score >= 1 else None


async def _fetch_subpage_text(url: str) -> tuple[str, str]:
    """Scarica una sottopagina. Ritorna (page_title, testo_pulito max 4000 char)."""
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            res = await client.get(url)
        if res.status_code != 200:
            return "", ""
        html = res.text
        # Estrai <title>
        title_m = _re.search(r"<title[^>]*>([^<]+)</title>", html, _re.IGNORECASE)
        page_title = title_m.group(1).strip() if title_m else ""
        # Rimuovi script, style, widget stesso
        html = _re.sub(r"<script[\s\S]*?</script>", " ", html, flags=_re.IGNORECASE)
        html = _re.sub(r"<style[\s\S]*?</style>", " ", html, flags=_re.IGNORECASE)
        html = _re.sub(r"<[^>]+>", " ", html)
        text = _re.sub(r"\s+", " ", html).strip()
        return page_title, text[:4000]
    except Exception as exc:
        logger.debug("WIDGET_FETCH_SUBPAGE_ERROR url=%s err=%s", url, exc)
        return "", ""


def _inject_bare_links(response: str, link_map: dict[str, str]) -> str:
    """
    Post-processing deterministico: ogni [testo] senza (url) nel testo della risposta
    viene completato con l'URL più pertinente dalla link_map.
    """
    if not link_map:
        return response

    def replacer(m: _re.Match) -> str:
        text = m.group(1)
        text_words = set(_re.sub(r"[^\w\s]", " ", text.lower()).split())
        best_url: Optional[str] = None
        best_score = 0
        for link_text, url in link_map.items():
            words = [w for w in _re.sub(r"[^\w\s]", " ", link_text.lower()).split() if len(w) > 3]
            def _wm(w: str) -> bool:
                if w in text_words:
                    return True
                if len(w) >= 6:
                    stem = w[:-1]
                    return any(len(m) >= 6 and m[:-1] == stem for m in text_words)
                return False
            score = sum(1 for w in words if _wm(w))
            if score > best_score:
                best_score = score
                best_url = url
        if best_url:
            return f"[{text}]({best_url})"
        return m.group(0)  # lascia invariato se non trova match

    return _re.sub(r"\[([^\]]+)\](?!\()", replacer, response)


# ── Schema richiesta ──────────────────────────────────────────────────────────

class WidgetChatRequest(BaseModel):
    message: str
    page_url:        Optional[str] = None
    page_title:      Optional[str] = None
    page_context:    Optional[str] = None   # testo visibile della pagina (troncato)
    conversation_id: Optional[str] = None
    user_name:       Optional[str] = None   # nome dell'utente loggato nella intranet
    user_role:       Optional[str] = None   # ruolo/reparto dell'utente
    workspace_token: Optional[str] = None   # Google OAuth token — riservato per integrazione futura


# ── Google Workspace integration (placeholder) ────────────────────────────────
# Per attivare: implementare _fetch_workspace_context() con le Google API
# (Gmail, Calendar, Drive) usando req.workspace_token come Bearer token.
# Il contesto restituito va iniettato nel messaggio prima di WIDGET_INSTRUCTION.

async def _fetch_workspace_context(workspace_token: str, user_message: str) -> str:
    """
    Recupera contesto Google Workspace (mail, calendario, drive) rilevante
    per il messaggio utente. Ritorna stringa da iniettare nel contesto.

    TODO: implementare con Google API (gmail.readonly, calendar.readonly).
    """
    return ""  # placeholder — non attivo


# ── Endpoint chat ─────────────────────────────────────────────────────────────

@router.post("/chat")
async def widget_chat(
    req: WidgetChatRequest,
    x_widget_key: str = Header(..., alias="X-Widget-Key"),
    x_forwarded_for: Optional[str] = Header(None, alias="X-Forwarded-For"),
    x_real_ip: Optional[str] = Header(None, alias="X-Real-IP"),
):
    client_ip = x_real_ip or (x_forwarded_for or "").split(",")[0].strip() or "unknown"
    _check_rate_limit(x_widget_key, client_ip)

    token = await _get_token(x_widget_key)

    # Estrai link dalla pagina corrente
    link_map = _extract_page_links(req.page_context or "")

    # Auto-fetch: se la query matcha una sottopagina, scaricane il contenuto
    subpage_text = ""
    subpage_title = ""
    matched_link: Optional[tuple[str, str]] = None
    if link_map:
        matched_link = await _find_best_link(req.message, link_map)
        if matched_link:
            _, subpage_url = matched_link
            subpage_title, subpage_text = await _fetch_subpage_text(subpage_url)
            if subpage_text:
                logger.info("WIDGET_SUBPAGE_FETCHED url=%s title=%r chars=%d", subpage_url, subpage_title, len(subpage_text))

    # Google Workspace context (placeholder — attivare quando integrazione pronta)
    # workspace_block = ""
    # if req.workspace_token:
    #     workspace_block = await _fetch_workspace_context(req.workspace_token, req.message)

    # Blocco identità utente (se disponibile)
    # Usa solo il primo nome — il CMS può passare nome completo ma il widget saluta informalmente
    user_identity_block = ""
    if req.user_name:
        _first_name = req.user_name.strip().split()[0] if req.user_name.strip() else req.user_name
        user_identity_block = f"\n[UTENTE LOGGATO — IDENTITÀ CERTA]\nL'utente con cui stai parlando ORA si chiama: {_first_name}"
        if req.user_role:
            user_identity_block += f"\nRuolo: {req.user_role}"
        user_identity_block += (
            f"\nUSA SEMPRE e SOLO il nome '{_first_name}' quando ti rivolgi all'utente — mai nome+cognome."
            f"\nIGNORA qualsiasi altro nome che compare nel contesto storico (es. nomi di altri partecipanti a conversazioni precedenti)."
            f"\nSe hai dubbi su chi sia l'utente, la risposta è: {_first_name}.\n"
        )

    # Istruzione comportamentale — condizionale
    if subpage_text and matched_link:
        # Subpage recuperata: chiedi riassunto + link
        WIDGET_INSTRUCTION = (
            "\n\n[ISTRUZIONE WIDGET]\n"
            "Sei un assistente del portale intranet aziendale C-Place.\n"
            "Usa i dati del CONTENUTO PAGINA DI DETTAGLIO per fornire un breve riassunto con dati/trend.\n"
            "Termina SEMPRE con il link diretto nel formato esatto: [testo](URL_COMPLETO)\n"
            "Esempio: [Statistiche infortuni Febbraio 2026](https://portale.it/salute)\n"
            "Risposta: 3-5 righe di riassunto + 1 link."
        )
    else:
        # Messaggio conversazionale: rispondi naturalmente, niente riassunti non richiesti
        WIDGET_INSTRUCTION = (
            "\n\n[ISTRUZIONE WIDGET]\n"
            "Sei un assistente del portale intranet aziendale C-Place.\n"
            "Rispondi in modo naturale alla domanda dell'utente.\n"
            "NON elencare contenuti della pagina se non esplicitamente chiesto."
        )

    # Costruisce il messaggio — req.message DEVE restare in testa (classificazione intent)
    # Il blocco [CONTESTO PAGINA] viene aggiunto SOLO se c'è contenuto di una subpage fetchata,
    # altrimenti disturba il fast-track intent (greeting, how_are_you, ecc.)
    if subpage_text and matched_link:
        _, subpage_url = matched_link
        parts = []
        if req.page_url:
            parts.append(f"Pagina attuale: {req.page_url}")
        if req.page_title:
            parts.append(f"Titolo: {req.page_title}")
        if req.page_context:
            parts.append(f"Contenuto pagina home (estratto):\n{req.page_context[:2000]}")
        parts.append(f"CONTENUTO PAGINA DI DETTAGLIO ({subpage_url}):\n{subpage_text}")
        message = req.message + "\n\n[CONTESTO PAGINA]\n" + "\n".join(parts) + user_identity_block + WIDGET_INSTRUCTION
    else:
        message = req.message + user_identity_block + WIDGET_INSTRUCTION

    payload = {"message": message, "platform": "widget"}
    if req.conversation_id:
        payload["conversation_id"] = req.conversation_id

    async with httpx.AsyncClient(timeout=60) as client:
        res = await client.post(
            f"{GENESI_URL}/api/chat",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        if res.status_code == 401:
            # Token scaduto: svuota cache e riprova una volta
            _token_cache.pop(x_widget_key, None)
            token = await _get_token(x_widget_key)
            res = await client.post(
                f"{GENESI_URL}/api/chat",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )

    if res.status_code != 200:
        raise HTTPException(status_code=503, detail="Genesi non disponibile")

    data = res.json()
    response_text = data.get("response") or data.get("message") or ""

    # Post-processing deterministico
    # 1) Prova a iniettare URL nei [link] senza parentesi tramite keyword match
    response_text = _inject_bare_links(response_text, link_map)

    # 2) Se abbiamo fetchato una sottopagina, garantisci sempre il link in fondo
    if matched_link:
        _, matched_url = matched_link
        if not _re.search(r"\[.+\]\(http", response_text):
            # Rimuovi i [link vuoti] rimasti dal LLM (es. [Leggi di più])
            response_text = _re.sub(r"\[([^\]]+)\](?!\()", r"\1", response_text).strip()
            # Usa il <title> della pagina come label del link
            link_label = subpage_title or "Approfondisci"
            response_text += f"\n\n[{link_label}]({matched_url})"

    # Aggiorna usage stats
    usage = _WIDGET_USAGE.setdefault(x_widget_key, {"calls": 0, "last_call": None, "created_at": time.time(), "label": x_widget_key})
    usage["calls"] += 1
    usage["last_call"] = time.time()

    return {
        "response": response_text,
        "intent":   data.get("intent", ""),
    }


# ── Endpoint health (per verificare che la chiave sia valida) ─────────────────

@router.get("/ping")
async def widget_ping(x_widget_key: str = Header(..., alias="X-Widget-Key")):
    if x_widget_key not in _WIDGET_CONFIGS:
        _load_configs()  # fallback: ricarica se configs vuoti al momento dell'import
    if x_widget_key not in _WIDGET_CONFIGS:
        raise HTTPException(status_code=401, detail="API key non valida")
    return {"ok": True}


# ── Admin endpoints ────────────────────────────────────────────────────────────

def _require_admin(
    x_admin_token: Optional[str] = None,
    authorization: Optional[str] = None,
):
    """Accetta X-Admin-Token diretto OPPURE JWT admin di Genesi (stesso JWT_SECRET)."""
    if _WIDGET_ADMIN_TOKEN and x_admin_token == _WIDGET_ADMIN_TOKEN:
        return
    if authorization and authorization.startswith("Bearer ") and _JWT_SECRET and _jwt:
        try:
            payload = _jwt.decode(
                authorization[7:], _JWT_SECRET, algorithms=["HS256"]
            )
            if payload.get("admin"):
                return
        except Exception:
            pass
    raise HTTPException(status_code=403, detail="Accesso non autorizzato")


class AdminKeyCreate(BaseModel):
    key:      str
    email:    str
    password: str
    label:    Optional[str] = None
    rate_limited: bool = False


@router.get("/admin/keys")
async def admin_list_keys(
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    _require_admin(x_admin_token, authorization)
    # Ricarica da env (gestisce import anticipato prima di load_dotenv)
    if not _WIDGET_CONFIGS:
        _load_configs()
    result = []
    for key, cfg in _WIDGET_CONFIGS.items():
        usage = _WIDGET_USAGE.get(key, {})
        result.append({
            "key":          key,
            "label":        usage.get("label", key),
            "email":        cfg["email"],
            "calls":        usage.get("calls", 0),
            "last_call":    usage.get("last_call"),
            "created_at":   usage.get("created_at"),
            "rate_limited": key in _RATE_LIMIT_KEYS,
        })
    return {"keys": result}


@router.post("/admin/keys", status_code=201)
async def admin_create_key(
    body: AdminKeyCreate,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    _require_admin(x_admin_token, authorization)
    if body.key in _WIDGET_CONFIGS:
        raise HTTPException(status_code=409, detail="Chiave già esistente")
    _WIDGET_CONFIGS[body.key] = {"email": body.email, "password": body.password}
    _WIDGET_USAGE[body.key] = {
        "calls": 0, "last_call": None,
        "created_at": time.time(),
        "label": body.label or body.key,
    }
    if body.rate_limited:
        _RATE_LIMIT_KEYS.add(body.key)
    logger.info("WIDGET_KEY_CREATED key=%s label=%s rate_limited=%s", body.key, body.label, body.rate_limited)
    return {"ok": True, "key": body.key}


@router.delete("/admin/keys/{key}")
async def admin_revoke_key(
    key: str,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    _require_admin(x_admin_token, authorization)
    if key not in _WIDGET_CONFIGS:
        raise HTTPException(status_code=404, detail="Chiave non trovata")
    _WIDGET_CONFIGS.pop(key, None)
    _token_cache.pop(key, None)
    _RATE_LIMIT_KEYS.discard(key)
    logger.info("WIDGET_KEY_REVOKED key=%s", key)
    return {"ok": True, "revoked": key}


# ── Endpoint config visuale (pubblico) ────────────────────────────────────────

@router.get("/config")
async def widget_config(x_widget_key: str = Header(..., alias="X-Widget-Key")):
    """Ritorna la configurazione visuale del widget per una data chiave (pubblico)."""
    if x_widget_key not in _WIDGET_CONFIGS:
        _load_configs()
    if x_widget_key not in _WIDGET_CONFIGS:
        raise HTTPException(status_code=401, detail="API key non valida")
    visual = _WIDGET_VISUAL.get(x_widget_key, {})
    return {
        "name":        visual.get("name", "Assistente"),
        "color":       visual.get("color", "#7c3aed"),
        "welcome":     visual.get("welcome", "Ciao! Come posso aiutarti oggi?"),
        "position":    visual.get("position", "bottom-right"),
        "placeholder": visual.get("placeholder", "Scrivi un messaggio..."),
    }


# ── Endpoint aggiornamento config visuale (admin) ─────────────────────────────

class AdminConfigUpdate(BaseModel):
    name:            Optional[str]       = None
    color:           Optional[str]       = None
    welcome:         Optional[str]       = None
    position:        Optional[str]       = None
    placeholder:     Optional[str]       = None
    allowed_domains: Optional[list[str]] = None


@router.get("/admin/config/{key}")
async def admin_get_config(
    key: str,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    _require_admin(x_admin_token, authorization)
    if key not in _WIDGET_CONFIGS:
        _load_configs()
    if key not in _WIDGET_CONFIGS:
        raise HTTPException(status_code=404, detail="Chiave non trovata")
    config = _WIDGET_VISUAL.get(key, {
        "name": "Assistente",
        "color": "#7c3aed",
        "welcome": "Ciao! Come posso aiutarti oggi?",
        "position": "bottom-right",
        "placeholder": "Scrivi un messaggio...",
        "allowed_domains": [],
    })
    return {"ok": True, "config": config}


@router.patch("/admin/config/{key}")
async def admin_update_config(
    key: str,
    body: AdminConfigUpdate,
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    _require_admin(x_admin_token, authorization)
    if key not in _WIDGET_CONFIGS:
        _load_configs()
    if key not in _WIDGET_CONFIGS:
        raise HTTPException(status_code=404, detail="Chiave non trovata")
    current = _WIDGET_VISUAL.setdefault(key, {
        "name": "Assistente",
        "color": "#7c3aed",
        "welcome": "Ciao! Come posso aiutarti oggi?",
        "position": "bottom-right",
        "placeholder": "Scrivi un messaggio...",
        "allowed_domains": [],
    })
    for field, val in body.model_dump(exclude_none=True).items():
        current[field] = val
    logger.info("WIDGET_CONFIG_UPDATED key=%s fields=%s", key, list(body.model_dump(exclude_none=True).keys()))
    return {"ok": True, "config": current}


@router.post("/admin/demo/reset")
async def admin_demo_reset(
    x_admin_token: Optional[str] = Header(None, alias="X-Admin-Token"),
    authorization: Optional[str] = Header(None, alias="Authorization"),
):
    """Ripristina i file HTML dell'intranet di demo allo stato pulito (senza widget)."""
    _require_admin(x_admin_token, authorization)
    # INTRANET_DEMO_DIR permette al widget-service di puntare alla dir di Genesi
    _demo_root = os.getenv("INTRANET_DEMO_DIR") or str(Path(__file__).resolve().parent.parent / "static" / "intranet")
    intranet_dir  = Path(_demo_root)
    templates_dir = intranet_dir / "templates"
    if not templates_dir.exists():
        raise HTTPException(status_code=500, detail="Directory templates non trovata")
    restored = []
    for tmpl in templates_dir.glob("*.html"):
        shutil.copy(tmpl, intranet_dir / tmpl.name)
        restored.append(tmpl.name)
    logger.info("DEMO_RESET restored=%s", restored)
    return {"ok": True, "restored": sorted(restored)}
