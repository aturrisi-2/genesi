"""
Widget API — endpoint per il widget embeddabile.
Autenticazione tramite API key aziendale (X-Widget-Key header).
"""
import os
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

    # Istruzione comportamentale fissa per il widget
    WIDGET_INSTRUCTION_PRE = (
        "[SISTEMA WIDGET INTRANET - LEGGI PRIMA DI RISPONDERE]\n"
        "Sei un assistente integrato nel portale intranet aziendale C-Place.\n"
        "REGOLA ASSOLUTA SUI LINK: nel contesto pagina trovi una sezione 'LINK DISPONIBILI NELLA PAGINA'.\n"
        "Ogni volta che menzioni un contenuto che ha un link in quella sezione, DEVI scrivere il link "
        "nel formato ESATTO: [testo](URL_COMPLETO)\n"
        "ESEMPIO CORRETTO: [Statistiche infortuni Febbraio 2026](https://portale.esempio.it/salute)\n"
        "VIETATO ASSOLUTO: scrivere [testo] senza URL — è un errore grave.\n"
        "Risposte brevi: 2-3 frasi + link diretto.\n"
    )

    # Costruisce il messaggio arricchito col contesto pagina
    message = req.message
    if req.page_url or req.page_context:
        parts = []
        if req.page_url:
            parts.append(f"Pagina attuale: {req.page_url}")
        if req.page_title:
            parts.append(f"Titolo: {req.page_title}")
        if req.page_context:
            parts.append(f"Contenuto pagina (estratto):\n{req.page_context[:3000]}")
        message = (
            WIDGET_INSTRUCTION_PRE
            + "\n[CONTESTO PAGINA]\n"
            + "\n".join(parts)
            + "\n\n[DOMANDA UTENTE]\n"
            + req.message
        )
    else:
        message = WIDGET_INSTRUCTION_PRE + "\n[DOMANDA UTENTE]\n" + req.message

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
    return {
        "response": data.get("response") or data.get("message") or "",
        "intent":   data.get("intent", ""),
    }


# ── Endpoint health (per verificare che la chiave sia valida) ─────────────────

@router.get("/ping")
async def widget_ping(x_widget_key: str = Header(..., alias="X-Widget-Key")):
    if x_widget_key not in _WIDGET_CONFIGS:
        raise HTTPException(status_code=401, detail="API key non valida")
    return {"ok": True}
