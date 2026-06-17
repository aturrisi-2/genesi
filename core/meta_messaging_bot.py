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
import json
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
MAX_VIDEO_BYTES    = 50 * 1024 * 1024
_ALLOWED_VIDEO_MIME = ("video/mp4", "video/quicktime", "video/webm", "video/3gpp")
MAX_AUDIO_BYTES    = 25 * 1024 * 1024
_ALLOWED_AUDIO_MIME = ("audio/mpeg", "audio/mp4", "audio/ogg", "audio/wav",
                       "audio/x-wav", "audio/aac", "audio/webm", "audio/amr")
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
    Usa le costanti di modulo (caricate dall'env all'import): il servizio viene
    riavviato ad ogni deploy e i test le patchano via monkeypatch.
    """
    if platform == "instagram":
        return [s for s in (IG_APP_SECRET, META_APP_SECRET) if s]
    return [s for s in (META_APP_SECRET,) if s]


def verify_signature(payload: bytes, signature_header: str,
                     platform: str = "messenger") -> bool:
    """
    Verifica X-Hub-Signature-256 (HMAC-SHA256 del body con l'app secret).
    Se nessun secret è configurato accetta (dev mode) ma logga warning.
    Confronto constant-time per evitare timing attack.
    """
    secrets = _secrets_for_platform(platform)
    if not secrets:
        # Fail-CLOSED in produzione: senza secret non si può autenticare il webhook.
        # Solo opt-in esplicito per sviluppo locale.
        if os.getenv("META_ALLOW_UNSIGNED", "").lower() in ("1", "true", "yes"):
            logger.warning("META_SIGNATURE_SKIPPED app_secret non configurato (dev opt-in)")
            return True
        logger.error("META_SIGNATURE_NO_SECRET reject — set META_APP_SECRET/IG_APP_SECRET")
        return False
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


async def send_sender_action(platform: str, recipient_id: str, action: str = "typing_on"):
    """
    Invia un sender_action (typing_on/typing_off/mark_seen) via Graph API.
    Mostra i puntini "sta scrivendo" mentre Genesi costruisce la risposta.
    Fail-silent: un errore qui non deve mai bloccare la risposta.
    """
    if not _SENDER_RE.match(recipient_id or ""):
        return
    token = _get_access_token(platform)
    if not token:
        return
    api_base = _get_api_base(platform)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{api_base}/me/messages",
                params={"access_token": token},
                json={"recipient": {"id": recipient_id}, "sender_action": action},
            )
    except Exception as e:
        logger.debug("META_SENDER_ACTION_ERR platform=%s action=%s err=%s",
                     platform, action, e)


async def show_typing(platform: str, recipient_id: str):
    """Segna come letto e mostra i puntini (typing_on dura ~20s su Meta)."""
    await send_sender_action(platform, recipient_id, "mark_seen")
    await send_sender_action(platform, recipient_id, "typing_on")


_MD_LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^\s\)]+)\)")


def _extract_source_links(text: str) -> tuple[str, list[tuple[str, str]]]:
    """
    Estrae i link markdown [titolo](url) dal testo (le fonti del live search).
    Ritorna (testo_pulito, [(titolo, url), ...]) — max 3 link deduplicati.
    """
    links = _MD_LINK_RE.findall(text or "")
    clean = _MD_LINK_RE.sub(r"\1", text or "")
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for title, url in links:
        if url not in seen:
            seen.add(url)
            out.append((title.strip(), url))
    return clean, out[:3]


def _domain_of(url: str) -> str:
    try:
        from urllib.parse import urlparse
        d = urlparse(url).netloc
        return d[4:] if d.startswith("www.") else d
    except Exception:
        return "fonte"


async def _send_source_buttons(platform: str, recipient_id: str,
                               links: list[tuple[str, str]]):
    """
    Invia le fonti come bottoni nativi (generic template con web_url):
    il link si apre nella webview interna di Messenger/Instagram.
    Fail-silent: un errore qui non blocca mai la conversazione.
    """
    token = _get_access_token(platform)
    if not token or not links:
        return
    api_base = _get_api_base(platform)
    elements = [{
        "title": (title or _domain_of(url))[:80],
        "subtitle": _domain_of(url)[:80],
        "buttons": [{"type": "web_url", "url": url, "title": "🌐 Apri fonte"}],
    } for title, url in links]
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"attachment": {"type": "template", "payload": {
            "template_type": "generic", "elements": elements,
        }}},
        "messaging_type": "RESPONSE",
    }
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(
                f"{api_base}/me/messages",
                params={"access_token": token},
                json=payload,
            )
            if res.status_code == 200:
                log("META_SOURCE_BUTTON_SENT", platform=platform, links=len(links))
            else:
                logger.warning("META_SOURCE_BUTTON_FAIL platform=%s status=%d body=%.200s",
                               platform, res.status_code, res.text)
    except Exception as e:
        logger.debug("META_SOURCE_BUTTON_ERR platform=%s err=%s", platform, e)


async def send_message(platform: str, recipient_id: str, text: str) -> bool:
    """Invia un messaggio testuale via Graph API (Messenger o Instagram DM)."""
    if not text or not _SENDER_RE.match(recipient_id or ""):
        return False
    token = _get_access_token(platform)
    if not token:
        logger.warning("META_SEND_NO_TOKEN platform=%s", platform)
        return False
    api_base = _get_api_base(platform)

    # Link markdown (fonti live search) → testo pulito + bottoni nativi dopo
    text, source_links = _extract_source_links(text)

    chunks = [text[i:i + MSG_CHUNK_LEN] for i in range(0, len(text), MSG_CHUNK_LEN)]
    ok = True
    async with httpx.AsyncClient(timeout=30) as client:
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
                logger.error("META_SEND_ERROR platform=%s err_type=%s err=%r",
                             platform, type(e).__name__, e)
                ok = False
            if len(chunks) > 1:
                await asyncio.sleep(0.3)

    # Fonti come bottoni dopo il testo (live search)
    if ok and source_links:
        await _send_source_buttons(platform, recipient_id, source_links)
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


async def _resolve_media_permalink(page_url: str) -> dict:
    """
    Quando l'allegato è un PERMALINK (es. instagram.com/reel/...) invece del
    file CDN, estrae dai meta tag della pagina: og:video (URL video reale),
    og:image (thumbnail) e og:description/title (testo del post).
    """
    out = {"video_url": "", "image_url": "", "text": ""}

    def _extract_og(html: str):
        for prop, key in (("og:video:secure_url", "video_url"), ("og:video", "video_url"),
                          ("og:image", "image_url"),
                          ("og:description", "text"), ("og:title", "text")):
            if out[key]:
                continue
            m = re.search(
                rf'<meta[^>]+property=["\']{re.escape(prop)}["\'][^>]+content=["\']([^"\']+)["\']', html)
            if not m:
                m = re.search(
                    rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']{re.escape(prop)}["\']', html)
            if m:
                import html as _html
                out[key] = _html.unescape(m.group(1))

    # Instagram serve gli og-tag SOLO ai crawler di link preview:
    # prova prima con lo UA di facebookexternalhit, poi browser classico
    for ua in ("facebookexternalhit/1.1 (+http://www.facebook.com/externalhit_uatext.php)",
               "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/124 Safari/537.36"):
        try:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True,
                                         headers={"User-Agent": ua}) as client:
                res = await client.get(page_url)
                if res.status_code == 200:
                    _extract_og(res.text)
            if out["video_url"] or out["image_url"]:
                break
        except Exception as e:
            logger.debug("META_PERMALINK_UA_ERR ua=%.20s err=%s", ua, e)

    # Fallback ufficiale: Instagram oEmbed (thumbnail + autore + titolo)
    if not out["video_url"] and not out["image_url"]:
        try:
            app_secret = os.getenv("META_APP_SECRET", META_APP_SECRET)
            if app_secret:
                app_token = f"959976033273333|{app_secret}"
                async with httpx.AsyncClient(timeout=20) as client:
                    res = await client.get(
                        f"{META_API_BASE}/instagram_oembed",
                        params={"url": page_url, "access_token": app_token,
                                "fields": "thumbnail_url,author_name,title"})
                    if res.status_code == 200:
                        d = res.json()
                        out["image_url"] = d.get("thumbnail_url", "")
                        _t = " — ".join(x for x in (d.get("author_name"), d.get("title")) if x)
                        if _t and not out["text"]:
                            out["text"] = _t
                    else:
                        logger.info("META_OEMBED_FAIL status=%d body=%.150s",
                                    res.status_code, res.text)
        except Exception as e:
            logger.debug("META_OEMBED_ERR err=%s", e)

    logger.info("META_PERMALINK_RESOLVED video=%s image=%s text_len=%d",
                bool(out["video_url"]), bool(out["image_url"]), len(out["text"]))
    return out


async def download_video(url: str) -> bytes | None:
    """
    Scarica un video allegato (Reel/video diretto).
    Sicurezza: solo https, content-type allowlist, max 50 MB.
    """
    if not url or not url.startswith("https://"):
        logger.warning("META_VIDEO_REJECTED_SCHEME url=%.80s", url or "")
        return None
    try:
        async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
            res = await client.get(url)
            if res.status_code != 200:
                return None
            mime = (res.headers.get("content-type", "") or "").split(";")[0].strip().lower()
            if mime and mime not in _ALLOWED_VIDEO_MIME:
                logger.warning("META_VIDEO_REJECTED_MIME mime=%s", mime)
                return None
            if len(res.content) > MAX_VIDEO_BYTES:
                logger.warning("META_VIDEO_REJECTED_SIZE bytes=%d", len(res.content))
                return None
            return res.content
    except Exception as e:
        logger.error("META_VIDEO_DOWNLOAD_ERROR err=%s", e)
        return None


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
            # Eventi non-messaging (commenti sui post, menzioni)
            for change in entry.get("changes", []) or []:
                try:
                    await _process_change(change, platform)
                except Exception as e:
                    logger.error("META_PROCESS_CHANGE_ERROR platform=%s err=%s", platform, e)
    except Exception as e:
        logger.error("META_HANDLE_UPDATE_ERROR platform=%s err=%s", platform, e)


_COMMENT_REPLY_PROMPT = (
    "Sei Genesi, assistente AI familiare italiana. Qualcuno ha commentato un tuo "
    "post Instagram. Rispondi al commento in modo caldo, breve (1-2 frasi), genuino "
    "e mai da marketing. Se il commento è una domanda, rispondi. Se è un complimento, "
    "ringrazia con personalità. Niente hashtag nelle risposte ai commenti."
)


async def reply_to_comment(comment_id: str, username: str, text: str) -> bool:
    """
    Genera e pubblica una risposta a un commento Instagram.
    Usata sia dal webhook handler che dal polling di fallback del publisher.
    """
    try:
        from core import automation_flags
        if not automation_flags.ensure_active("instagram_comment_replies"):
            return False

        from core.llm_service import llm_service
        ctx = f"Commento di @{username}: {text}" if username else f"Commento: {text}"
        reply = await llm_service._call_model(
            "openai/gpt-4o-mini", _COMMENT_REPLY_PROMPT, ctx,
            user_id="ig_comments", route="memory",
        )
        reply = (reply or "").strip()
        if not reply:
            return False

        token = _get_access_token("instagram")
        api_base = _get_api_base("instagram")
        async with httpx.AsyncClient(timeout=30) as client:
            res = await client.post(
                f"{api_base}/{comment_id}/replies",
                data={"message": reply[:900], "access_token": token},
            )
            if res.status_code == 200:
                log("META_COMMENT_REPLIED", comment_id=comment_id, user=username)
                logger.info("META_COMMENT_REPLIED comment_id=%s user=%s", comment_id, username)
                return True
            logger.error("META_COMMENT_REPLY_FAIL status=%d body=%.200s",
                         res.status_code, res.text)
            return False
    except Exception as e:
        logger.error("META_COMMENT_REPLY_ERROR err=%s", e)
        return False


async def _process_change(change: dict, platform: str):
    """
    Processa eventi 'changes' (non-messaging): commenti sui post Instagram.
    Risponde automaticamente ai commenti ricevuti sui propri post.
    """
    field = change.get("field", "")
    if field != "comments" or platform != "instagram":
        logger.info("META_CHANGE_SKIPPED platform=%s field=%s", platform, field)
        return

    value = change.get("value") or {}
    comment_id = value.get("id", "")
    text = (value.get("text") or "").strip()
    from_user = value.get("from") or {}
    from_id = str(from_user.get("id", ""))

    if not comment_id or not text:
        return

    # Anti-loop: ignora i commenti scritti da Genesi stessa
    try:
        from core.instagram_publisher import get_ig_user_id, is_comment_replied, mark_comment_replied
        own_id = await get_ig_user_id()
        if own_id and from_id == str(own_id):
            logger.info("META_COMMENT_OWN_SKIP")
            return
        # Dedup persistente condiviso con il polling
        if is_comment_replied(comment_id):
            return
    except Exception:
        pass

    # Deduplica in-memory (i webhook possono essere ri-consegnati)
    if _is_duplicate_mid(f"comment_{comment_id}"):
        return

    logger.info("META_COMMENT_RECEIVED from=%s text=%.80s", from_user.get("username", "?"), text)

    ok = await reply_to_comment(comment_id, from_user.get("username", ""), text)
    if ok:
        try:
            from core.instagram_publisher import mark_comment_replied
            mark_comment_replied(comment_id)
        except Exception:
            pass


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

    from core import automation_flags
    if not automation_flags.flag_enabled("meta_dm_replies"):
        log("AUTOMATION_SKIPPED", flag="meta_dm_replies", platform=platform)
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

    if attachments:
        logger.info("META_ATTACHMENTS platform=%s raw=%.500s",
                    platform, json.dumps(attachments, ensure_ascii=False))

    image_url = ""
    video_url = ""
    audio_url = ""
    other_types: list[str] = []
    for att in attachments:
        att_type = att.get("type", "")
        att_url = (att.get("payload") or {}).get("url", "")
        if att_type == "image" and not image_url:
            image_url = att_url
        elif att_type in ("video", "ig_reel", "reel", "animated_image_share") and not video_url:
            # Reel Instagram condivisi e video diretti
            video_url = att_url
        elif att_type == "audio" and not audio_url:
            audio_url = att_url
        elif att_type:
            other_types.append(att_type)

    if image_url:
        await _handle_image(user_id, sender_id, platform, image_url, caption=text)
        return

    if video_url:
        await _handle_video(user_id, sender_id, platform, video_url, caption=text)
        return

    if audio_url:
        await _handle_audio(user_id, sender_id, platform, audio_url, caption=text)
        return

    if not text:
        if other_types:
            # MAI silenzio: qualsiasi allegato non gestito riceve una risposta
            logger.info("META_ATTACHMENT_UNSUPPORTED platform=%s types=%s", platform, other_types)
            await send_message(platform, sender_id,
                "Per ora su questo canale gestisco testo, foto, video/Reel e audio. "
                "Questo contenuto non riesco ancora ad aprirlo!")
        return

    await _handle_text(user_id, sender_id, platform, text)


async def _handle_text(user_id: str, sender_id: str, platform: str, text: str):
    """Pipeline testo: face-naming state → chat → memoria."""
    from core.message_pipeline import process_incoming_text, schedule_memory_tasks
    from core.simple_chat import simple_chat_handler

    # Puntini "sta scrivendo" mentre Genesi costruisce la risposta
    asyncio.create_task(show_typing(platform, sender_id))

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

    # Puntini "sta scrivendo" — l'analisi foto può durare 10-15s
    asyncio.create_task(show_typing(platform, sender_id))

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


async def _handle_audio(user_id: str, sender_id: str, platform: str,
                        audio_url: str, caption: str = ""):
    """Pipeline audio: download sicuro → analisi (parlato/musica/suoni) → chat → memoria."""
    from core.message_pipeline import process_incoming_audio, schedule_memory_tasks
    from core.simple_chat import simple_chat_handler

    asyncio.create_task(show_typing(platform, sender_id))

    # Download con allowlist audio
    audio_bytes = None
    mime = "audio/ogg"
    try:
        if audio_url and audio_url.startswith("https://"):
            async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
                res = await client.get(audio_url)
                if res.status_code == 200 and len(res.content) <= MAX_AUDIO_BYTES:
                    mime = (res.headers.get("content-type", "") or "audio/ogg").split(";")[0].strip().lower()
                    if not mime.startswith("audio/") and mime not in _ALLOWED_AUDIO_MIME:
                        mime = "audio/ogg"
                    audio_bytes = res.content
    except Exception as e:
        logger.error("META_AUDIO_DOWNLOAD_ERROR err=%s", e)

    if not audio_bytes:
        await send_message(platform, sender_id,
            "Non sono riuscita a scaricare l'audio. Riprova!")
        return

    audio = await process_incoming_audio(
        session_id=user_id, user_id=user_id,
        audio_bytes=audio_bytes, platform=platform,
        content_type=mime, caption=caption,
    )
    analysis = audio.get("analysis", "")
    transcription = audio.get("transcription")

    if transcription and audio.get("kind") == "speech":
        # Vocale parlato: la trascrizione È il messaggio dell'utente
        user_msg = transcription
        if caption:
            user_msg = f"{caption}\n{transcription}"
        if analysis and analysis != transcription:
            user_msg += f"\n\n[Contesto audio: {analysis}]"
    elif analysis:
        user_msg = (caption or "Ascolta questo audio che ti ho inviato.") + \
                   f"\n\n[Contenuto audio: {analysis}]"
    else:
        user_msg = ((caption or "Ti ho inviato un audio.") +
                    "\n\n[SISTEMA: l'utente ha inviato un audio ma l'analisi non è "
                    "riuscita. Rispondi con curiosità, senza fingere di averlo sentito.]")

    response, intent = await simple_chat_handler(
        user_id=user_id, message=user_msg, platform=platform,
    )
    await send_message(platform, sender_id, response)
    log("META_AUDIO_OK", platform=platform, user_id=user_id, kind=audio.get("kind"))

    asyncio.create_task(schedule_memory_tasks(
        user_id=user_id, user_message=user_msg, response=response,
        platform=platform, intent=intent, is_group=False,
    ))


async def _handle_video(user_id: str, sender_id: str, platform: str,
                        video_url: str, caption: str = ""):
    """Pipeline video/Reel: download sicuro → frame/vision/biometria → chat → memoria."""
    from core.message_pipeline import (
        process_incoming_video, schedule_memory_tasks,
    )
    from core.simple_chat import simple_chat_handler

    # Puntini "sta scrivendo" — l'analisi video può durare 20-30s
    asyncio.create_task(show_typing(platform, sender_id))

    permalink_text = ""
    video_bytes = await download_video(video_url)

    # L'URL può essere un PERMALINK (pagina instagram.com/reel/...) invece
    # del file CDN: risolvi i meta tag per ottenere il video reale
    if not video_bytes and "instagram.com" in (video_url or ""):
        resolved = await _resolve_media_permalink(video_url)
        permalink_text = resolved.get("text", "")
        if resolved.get("video_url"):
            video_bytes = await download_video(resolved["video_url"])
        if not video_bytes and resolved.get("image_url"):
            # Fallback: analizza la thumbnail del Reel + testo del post
            _cap = caption or "Guarda questo Reel che ti ho condiviso."
            if permalink_text:
                _cap += f"\n[Testo del post: {permalink_text[:500]}]"
            await _handle_image(user_id, sender_id, platform,
                                resolved["image_url"], caption=_cap)
            return

    if not video_bytes:
        await send_message(platform, sender_id,
            "Non sono riuscita ad aprire questo contenuto. Riprova!")
        return

    video = await process_incoming_video(
        session_id=user_id, user_id=user_id,
        video_bytes=video_bytes, platform=platform, caption=caption,
    )
    user_msg = caption or "Guarda questo video che ti ho condiviso."
    if permalink_text:
        user_msg += f"\n[Testo del post: {permalink_text[:500]}]"
    analysis = video.get("analysis", "")
    if analysis:
        user_msg = f"{user_msg}\n\n[Contenuto video: {analysis}]"
        if video.get("sistema_msg"):
            user_msg += video["sistema_msg"]
    else:
        user_msg = (f"{user_msg}\n\n[SISTEMA: l'utente ha condiviso un video ma "
                    "l'analisi non è riuscita. Rispondi con curiosità chiedendo "
                    "di cosa parla, senza fingere di averlo visto.]")

    response, intent = await simple_chat_handler(
        user_id=user_id, message=user_msg, platform=platform,
    )
    await send_message(platform, sender_id, response)
    log("META_VIDEO_OK", platform=platform, user_id=user_id)

    asyncio.create_task(schedule_memory_tasks(
        user_id=user_id,
        user_message=user_msg,
        response=response,
        platform=platform,
        intent=intent,
        is_group=False,
    ))
