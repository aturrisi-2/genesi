"""
GENESI — Meta Messaging Bot (Facebook Messenger + Instagram DM, Graph API)

Gestisce i messaggi diretti in arrivo da Messenger e Instagram tramite i
webhook Meta. Riusa la pipeline universale (message_pipeline.py):
ogni piattaforma resta ISOLATA (namespace utente dedicato) ma alimenta
gli stessi livelli di apprendimento del cervello di Genesi.

Isolamento piattaforme (zero contaminazione):
- user_id namespace: "fb_<psid>" per Messenger, "ig_<igsid>" per Instagram.
  Tutte le chiavi storage (profile:, chat:, episodes:, facts:, behavior:, ...)
  risultano quindi separate da WhatsApp/Telegram/web.
- Il payload viene accettato SOLO se il campo "object" corrisponde alla
  piattaforma del webhook chiamato (page → messenger, instagram → instagram).

Sicurezza:
- Firma X-Hub-Signature-256 verificata con HMAC-SHA256 (constant-time).
- Sender ID validato strettamente (solo cifre, max 32) — niente injection
  nelle chiavi storage.
- Deduplica message-id (protezione replay).
- Messaggi echo (inviati dalla pagina stessa) ignorati — niente loop.
- Testo troncato a 12000 caratteri (stesso limite di ChatRequest).
- Download immagini: solo https, content-type allowlist, max 20 MB.
"""

import asyncio
import hashlib
import hmac
import logging
import os
import re
from collections import OrderedDict

import httpx

from core.log import log

logger = logging.getLogger(__name__)

# ── Credenziali Meta (env-only: mai hardcoded) ───────────────────────────────
META_APP_SECRET    = os.getenv("META_APP_SECRET", "")
# La "Instagram API with Instagram Login" firma i webhook con l'Instagram App
# Secret (Instagram → API setup), DIVERSO dall'App Secret principale.
IG_APP_SECRET      = os.getenv("IG_APP_SECRET", "")
META_VERIFY_TOKEN  = os.getenv("META_VERIFY_TOKEN", "genesi_meta_verify")
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "")
IG_ACCESS_TOKEN      = os.getenv("IG_ACCESS_TOKEN", "")
META_API_VERSION   = "v19.0"
META_API_BASE      = f"https://graph.facebook.com/{META_API_VERSION}"
# I token Instagram "Instagram API with Instagram Login" (formato IGAA...)
# funzionano SOLO su graph.instagram.com, non su graph.facebook.com.
IG_API_BASE        = f"https://graph.instagram.com/{META_API_VERSION}"

# ── Configurazione piattaforme (isolamento garantito dal namespace) ──────────
PLATFORMS = {
    "messenger": {
        "object": "page",          # campo "object" atteso nel payload Meta
        "user_prefix": "fb_",      # namespace user_id → memorie isolate
        "token_env": "FB_PAGE_ACCESS_TOKEN",
        "api_base": META_API_BASE,
    },
    "instagram": {
        "object": "instagram",
        "user_prefix": "ig_",
        "token_env": "IG_ACCESS_TOKEN",
        "api_base": IG_API_BASE,
    },
}

# Limiti di sicurezza
MAX_TEXT_LEN       = 12000          # allineato a ChatRequest (api/chat.py)
MAX_IMAGE_BYTES    = 20 * 1024 * 1024
MSG_CHUNK_LEN      = 1900           # limite messaggio Messenger ~2000 char
_ALLOWED_IMG_MIME  = ("image/jpeg", "image/png", "image/webp", "image/gif")

# Sender ID Meta (PSID/IGSID): solo cifre. Blocca path traversal, spazi,
# caratteri di controllo e qualsiasi tentativo di forgiare chiavi storage.
_SENDER_RE = re.compile(r"^\d{1,32}$")

# ── Deduplica message-id (protezione replay webhook) ─────────────────────────
_SEEN_MIDS: OrderedDict[str, bool] = OrderedDict()
_SEEN_MIDS_MAX = 500


def _is_duplicate_mid(mid: str) -> bool:
    """True se il message-id è già stato processato (replay/redelivery)."""
    if not mid:
        return False
    if mid in _SEEN_MIDS:
        return True
    _SEEN_MIDS[mid] = True
    while len(_SEEN_MIDS) > _SEEN_MIDS_MAX:
        _SEEN_MIDS.popitem(last=False)
    return False


# ── Verifica webhook (GET challenge Meta) ────────────────────────────────────

def verify_webhook(mode: str, token: str, challenge: str) -> str | None:
    """Verifica la challenge Meta. Ritorna la challenge se valida, None altrimenti."""
    if mode == "subscribe" and token and hmac.compare_digest(token, META_VERIFY_TOKEN):
        logger.info("META_WEBHOOK_VERIFIED")
        return challenge
    logger.warning("META_WEBHOOK_VERIFY_FAILED mode=%s", mode)
    return None


# ── Verifica firma payload (POST) ────────────────────────────────────────────

def _secrets_for_platform(platform: str) -> list[str]:
    """
    Secret candidati per la verifica firma, in ordine di priorità.
    Instagram (Instagram Login) firma con l'Instagram App Secret; se non
    configurato si tenta comunque l'App Secret principale (app via Facebook Login).
    """
    ig_secret = os.getenv("IG_APP_SECRET", IG_APP_SECRET)
    main_secret = os.getenv("META_APP_SECRET", META_APP_SECRET)
    if platform == "instagram":
        return [s for s in (ig_secret, main_secret) if s]
    return [s for s in (main_secret,) if s]


def verify_signature(payload: bytes, signature_header: str,
                     platform: str = "messenger") -> bool:
    """
    Verifica X-Hub-Signature-256 (HMAC-SHA256 del body con l'app secret).
    Se nessun secret è configurato accetta (dev mode) ma logga warning.
    Confronto constant-time per evitare timing attack.
    """
    secrets = _secrets_for_platform(platform)
    if not secrets:
        logger.warning("META_SIGNATURE_SKIPPED app_secret non configurato")
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        logger.warning("META_SIGNATURE_MISSING")
        return False
    provided = signature_header.split("=", 1)[1].strip()
    for secret in secrets:
        expected = hmac.new(
            secret.encode("utf-8"), payload, hashlib.sha256
        ).hexdigest()
        if hmac.compare_digest(provided, expected):
            return True
    logger.warning("META_SIGNATURE_INVALID platform=%s", platform)
    return False


# ── Invio messaggi (Graph API Send) ──────────────────────────────────────────

def _ig_via_page() -> bool:
    """
    True se Instagram opera in modalità "Messenger API for Instagram":
    account IG collegato alla pagina Facebook, messaggi gestiti con il
    token della pagina su graph.facebook.com. Attivata con IG_VIA_PAGE=1
    nel .env (usata quando il flusso Instagram Login diretto non è
    disponibile, es. toggle 'accesso ai messaggi' assente nell'app IG).
    """
    return os.getenv("IG_VIA_PAGE", "") in ("1", "true", "yes")


def _get_access_token(platform: str) -> str:
    cfg = PLATFORMS.get(platform)
    if not cfg:
        return ""
    if platform == "instagram" and _ig_via_page():
        return os.getenv("FB_PAGE_ACCESS_TOKEN", "")
    # Lettura runtime dall'env: consente rotazione token senza restart import
    return os.getenv(cfg["token_env"], "")


def _get_api_base(platform: str) -> str:
    if platform == "instagram" and _ig_via_page():
        return META_API_BASE  # graph.facebook.com (flusso via pagina)
    return PLATFORMS.get(platform, {}).get("api_base", META_API_BASE)


async def send_message(platform: str, recipient_id: str, text: str) -> bool:
    """Invia un messaggio testuale via Graph API (Messenger o Instagram DM)."""
    if not text or not _SENDER_RE.match(recipient_id or ""):
        return False
    token = _get_access_token(platform)
    if not token:
        logger.warning("META_SEND_NO_TOKEN platform=%s", platform)
        return False
    api_base = _get_api_base(platform)

    chunks = [text[i:i + MSG_CHUNK_LEN] for i in range(0, len(text), MSG_CHUNK_LEN)]
    ok = True
    async with httpx.AsyncClient(timeout=15) as client:
        for chunk in chunks:
            payload = {
                "recipient": {"id": recipient_id},
                "message": {"text": chunk},
                "messaging_type": "RESPONSE",
            }
            try:
                res = await client.post(
                    f"{api_base}/me/messages",
                    params={"access_token": token},
                    json=payload,
                )
                if res.status_code != 200:
                    logger.error("META_SEND_FAIL platform=%s status=%d body=%.200s",
                                 platform, res.status_code, res.text)
                    ok = False
            except Exception as e:
                logger.error("META_SEND_ERROR platform=%s err=%s", platform, e)
                ok = False
            if len(chunks) > 1:
                await asyncio.sleep(0.3)
    return ok


# ── Download media (immagini allegate) ───────────────────────────────────────

async def download_image(url: str) -> tuple[bytes | None, str]:
    """
    Scarica un'immagine allegata. Ritorna (bytes, mime) o (None, "").
    Sicurezza: solo https, content-type allowlist, max 20 MB.
    """
    if not url or not url.startswith("https://"):
        logger.warning("META_MEDIA_REJECTED_SCHEME url=%.80s", url or "")
        return None, ""
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            res = await client.get(url)
            if res.status_code != 200:
                return None, ""
            mime = (res.headers.get("content-type", "") or "").split(";")[0].strip().lower()
            if mime not in _ALLOWED_IMG_MIME:
                logger.warning("META_MEDIA_REJECTED_MIME mime=%s", mime)
                return None, ""
            if len(res.content) > MAX_IMAGE_BYTES:
                logger.warning("META_MEDIA_REJECTED_SIZE bytes=%d", len(res.content))
                return None, ""
            return res.content, mime
    except Exception as e:
        logger.error("META_MEDIA_DOWNLOAD_ERROR err=%s", e)
        return None, ""


# ── Main update handler ──────────────────────────────────────────────────────

async def handle_update(payload: dict, platform: str):
    """
    Processa un update webhook Meta (chiamato dal router in background).
    `platform` è "messenger" o "instagram" — determinato dall'endpoint chiamato.
    """
    cfg = PLATFORMS.get(platform)
    if not cfg:
        logger.error("META_UNKNOWN_PLATFORM platform=%s", platform)
        return

    # Anti-contaminazione: il payload deve dichiarare l'object della
    # piattaforma del webhook chiamato. Un payload "instagram" arrivato
    # sull'endpoint messenger (o viceversa) viene scartato.
    obj = payload.get("object", "")
    if obj != cfg["object"]:
        logger.warning("META_OBJECT_MISMATCH platform=%s object=%s", platform, obj)
        return

    try:
        entries = payload.get("entry", [])
        n_events = sum(len(e.get("messaging", []) or []) for e in entries)
        logger.info("META_UPDATE_RECEIVED platform=%s entries=%d messaging_events=%d",
                    platform, len(entries), n_events)
        for entry in entries:
            for event in entry.get("messaging", []) or []:
                try:
                    await _process_event(event, platform, cfg)
                except Exception as e:
                    logger.error("META_PROCESS_EVENT_ERROR platform=%s err=%s", platform, e)
    except Exception as e:
        logger.error("META_HANDLE_UPDATE_ERROR platform=%s err=%s", platform, e)


async def _process_event(event: dict, platform: str, cfg: dict):
    """Processa un singolo evento messaging."""
    msg = event.get("message") or {}
    if not msg:
        # delivery, read, postback, reaction: non sono messaggi utente
        other = [k for k in event.keys() if k not in ("sender", "recipient", "timestamp")]
        logger.info("META_EVENT_SKIPPED platform=%s type=%s", platform, other)
        return
    if msg.get("is_echo"):
        # Messaggio inviato dalla pagina stessa → ignorare (previene loop)
        logger.info("META_EVENT_ECHO platform=%s", platform)
        return

    sender_id = (event.get("sender") or {}).get("id", "")
    if not _SENDER_RE.match(sender_id or ""):
        logger.warning("META_SENDER_REJECTED platform=%s sender=%.40r", platform, sender_id)
        return

    mid = msg.get("mid", "")
    if _is_duplicate_mid(mid):
        logger.info("META_DUPLICATE_MID platform=%s mid=%.60s", platform, mid)
        return

    # Namespace dedicato: memorie isolate per piattaforma, nessuna
    # contaminazione con WhatsApp/Telegram/web.
    user_id = f"{cfg['user_prefix']}{sender_id}"

    text = (msg.get("text") or "").strip()[:MAX_TEXT_LEN]
    attachments = msg.get("attachments") or []

    image_url = ""
    unsupported = False
    for att in attachments:
        att_type = att.get("type", "")
        if att_type == "image" and not image_url:
            image_url = (att.get("payload") or {}).get("url", "")
        elif att_type in ("audio", "video", "file", "template", "fallback"):
            unsupported = True

    if image_url:
        await _handle_image(user_id, sender_id, platform, image_url, caption=text)
        return

    if not text:
        if unsupported:
            await send_message(platform, sender_id,
                "Per ora su questo canale posso gestire testo e immagini. "
                "Scrivimi pure, o mandami una foto!")
        return

    await _handle_text(user_id, sender_id, platform, text)


async def _handle_text(user_id: str, sender_id: str, platform: str, text: str):
    """Pipeline testo: face-naming state → chat → memoria."""
    from core.message_pipeline import process_incoming_text, schedule_memory_tasks
    from core.simple_chat import simple_chat_handler

    pre = await process_incoming_text(
        session_id=user_id, user_id=user_id, text=text, platform=platform,
    )
    message = pre.get("augmented_text") or text

    response, intent = await simple_chat_handler(
        user_id=user_id, message=message, platform=platform,
    )
    await send_message(platform, sender_id, response)
    log("META_TEXT_OK", platform=platform, user_id=user_id)

    asyncio.create_task(schedule_memory_tasks(
        user_id=user_id,
        user_message=text,
        response=response,
        platform=platform,
        intent=intent,
        is_group=False,
    ))


async def _handle_image(user_id: str, sender_id: str, platform: str,
                        image_url: str, caption: str = ""):
    """Pipeline immagine: download sicuro → vision/face → chat → memoria."""
    from core.message_pipeline import (
        process_incoming_photo, schedule_memory_tasks,
    )
    from core.simple_chat import simple_chat_handler

    img_bytes, _mime = await download_image(image_url)
    if not img_bytes:
        await send_message(platform, sender_id,
            "Non sono riuscita a scaricare l'immagine. Riprova!")
        return

    photo = await process_incoming_photo(
        session_id=user_id, user_id=user_id,
        img_bytes=img_bytes, platform=platform, caption=caption,
    )
    user_msg = caption or "Analizza questa immagine che ti ho inviato."
    analysis = photo.get("analysis", "")
    if analysis:
        user_msg = f"{user_msg}\n\n[Contenuto immagine: {analysis}]"
        if photo.get("sistema_msg"):
            user_msg += photo["sistema_msg"]

    response, intent = await simple_chat_handler(
        user_id=user_id, message=user_msg, platform=platform,
    )
    await send_message(platform, sender_id, response)
    log("META_PHOTO_OK", platform=platform, user_id=user_id)

    asyncio.create_task(schedule_memory_tasks(
        user_id=user_id,
        user_message=user_msg,
        response=response,
        platform=platform,
        intent=intent,
        is_group=False,
    ))
