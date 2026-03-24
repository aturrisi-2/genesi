"""
Widget API — endpoint per il widget embeddabile.
Autenticazione tramite API key aziendale (X-Widget-Key header).
"""
import os
import re as _re
import time
import logging
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
import httpx

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/widget", tags=["widget"])

GENESI_URL = os.getenv("BASE_URL", "http://localhost:8000")

# ── Caricamento configurazioni widget da env ──────────────────────────────────
# Singola chiave: WIDGET_API_KEY / WIDGET_EMAIL / WIDGET_PASSWORD
# Multi-chiave:   WIDGET_KEYS=chiave1:email1:pass1,chiave2:email2:pass2

_WIDGET_CONFIGS: dict[str, dict] = {}


def _load_configs():
    key  = os.getenv("WIDGET_API_KEY", "")
    mail = os.getenv("WIDGET_EMAIL", "")
    pw   = os.getenv("WIDGET_PASSWORD", "")
    if key and mail and pw:
        _WIDGET_CONFIGS[key] = {"email": mail, "password": pw}

    for entry in os.getenv("WIDGET_KEYS", "").split(","):
        parts = entry.strip().split(":")
        if len(parts) == 3:
            k, e, p = parts
            _WIDGET_CONFIGS[k.strip()] = {"email": e.strip(), "password": p.strip()}


_load_configs()

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


def _find_best_link(user_message: str, link_map: dict[str, str]) -> Optional[tuple[str, str]]:
    """Restituisce (testo, url) del link più rilevante per il messaggio utente, o None."""
    if not link_map:
        return None
    msg_lower = user_message.lower()
    best_score = 0
    best_item: Optional[tuple[str, str]] = None
    for text, url in link_map.items():
        words = [w for w in _re.sub(r"[^\w\s]", " ", text.lower()).split() if len(w) > 3]
        score = sum(1 for w in words if w in msg_lower)
        if score > best_score:
            best_score = score
            best_item = (text, url)
    return best_item if best_score >= 1 else None


async def _fetch_subpage_text(url: str) -> str:
    """Scarica una sottopagina e restituisce il testo pulito (max 4000 char)."""
    try:
        async with httpx.AsyncClient(timeout=8, follow_redirects=True) as client:
            res = await client.get(url)
        if res.status_code != 200:
            return ""
        html = res.text
        # Rimuovi script, style, widget stesso
        html = _re.sub(r"<script[\s\S]*?</script>", " ", html, flags=_re.IGNORECASE)
        html = _re.sub(r"<style[\s\S]*?</style>", " ", html, flags=_re.IGNORECASE)
        html = _re.sub(r"<[^>]+>", " ", html)
        text = _re.sub(r"\s+", " ", html).strip()
        return text[:4000]
    except Exception as exc:
        logger.debug("WIDGET_FETCH_SUBPAGE_ERROR url=%s err=%s", url, exc)
        return ""


def _inject_bare_links(response: str, link_map: dict[str, str]) -> str:
    """
    Post-processing deterministico: ogni [testo] senza (url) nel testo della risposta
    viene completato con l'URL più pertinente dalla link_map.
    """
    if not link_map:
        return response

    def replacer(m: _re.Match) -> str:
        text = m.group(1)
        text_lower = text.lower()
        best_url: Optional[str] = None
        best_score = 0
        for link_text, url in link_map.items():
            words = [w for w in _re.sub(r"[^\w\s]", " ", link_text.lower()).split() if len(w) > 3]
            score = sum(1 for w in words if w in text_lower)
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
    page_url:     Optional[str] = None
    page_title:   Optional[str] = None
    page_context: Optional[str] = None   # testo visibile della pagina (troncato)
    conversation_id: Optional[str] = None


# ── Endpoint chat ─────────────────────────────────────────────────────────────

@router.post("/chat")
async def widget_chat(
    req: WidgetChatRequest,
    x_widget_key: str = Header(..., alias="X-Widget-Key"),
):
    token = await _get_token(x_widget_key)

    # Estrai link dalla pagina corrente
    link_map = _extract_page_links(req.page_context or "")

    # Auto-fetch: se la query matcha una sottopagina, scaricane il contenuto
    subpage_text = ""
    matched_link: Optional[tuple[str, str]] = None
    if link_map:
        matched_link = _find_best_link(req.message, link_map)
        if matched_link:
            _, subpage_url = matched_link
            subpage_text = await _fetch_subpage_text(subpage_url)
            if subpage_text:
                logger.info("WIDGET_SUBPAGE_FETCHED url=%s chars=%d", subpage_url, len(subpage_text))

    # Istruzione comportamentale (in coda, dopo il contesto)
    WIDGET_INSTRUCTION = (
        "\n\n[ISTRUZIONE WIDGET]\n"
        "Sei un assistente del portale intranet aziendale C-Place.\n"
        "Usa i dati del CONTENUTO PAGINA DI DETTAGLIO per fornire un breve riassunto con dati/trend.\n"
        "Termina SEMPRE con il link diretto nel formato esatto: [testo](URL_COMPLETO)\n"
        "Esempio: [Statistiche infortuni Febbraio 2026](https://portale.it/salute)\n"
        "Risposta: 3-5 righe di riassunto + 1 link."
    )

    # Costruisce il messaggio — req.message DEVE restare in testa (classificazione intent)
    parts = []
    if req.page_url:
        parts.append(f"Pagina attuale: {req.page_url}")
    if req.page_title:
        parts.append(f"Titolo: {req.page_title}")
    if req.page_context:
        parts.append(f"Contenuto pagina home (estratto):\n{req.page_context[:2000]}")
    if subpage_text and matched_link:
        _, subpage_url = matched_link
        parts.append(f"CONTENUTO PAGINA DI DETTAGLIO ({subpage_url}):\n{subpage_text}")

    if parts:
        message = req.message + "\n\n[CONTESTO PAGINA]\n" + "\n".join(parts) + WIDGET_INSTRUCTION
    else:
        message = req.message + WIDGET_INSTRUCTION

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

    # Post-processing deterministico: inietta URL nei [link] senza parentesi
    response_text = _inject_bare_links(response_text, link_map)

    # Se ancora nessun link Markdown nella risposta ma abbiamo una sottopagina, appendila
    if matched_link and not _re.search(r"\[.+\]\(http", response_text):
        link_label, link_url = matched_link
        # Estrai testo pulito del label (rimuovi emoji e tag multipli)
        clean_label = _re.sub(r"[^\w\s\-àèéìíòóùú]", "", link_label).strip()
        clean_label = _re.sub(r"\s+", " ", clean_label)[:60]
        response_text += f"\n\n[{clean_label}]({link_url})"

    return {
        "response": response_text,
        "intent":   data.get("intent", ""),
    }


# ── Endpoint health (per verificare che la chiave sia valida) ─────────────────

@router.get("/ping")
async def widget_ping(x_widget_key: str = Header(..., alias="X-Widget-Key")):
    if x_widget_key not in _WIDGET_CONFIGS:
        raise HTTPException(status_code=401, detail="API key non valida")
    return {"ok": True}
