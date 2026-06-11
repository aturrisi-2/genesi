"""
INSTAGRAM PUBLISHER — Genesi
Pubblicazione autonoma di contenuti su Instagram + apprendimento dagli insight.

Flusso (2 post/giorno agli orari configurati):
1. LLM sceglie tema e scrive caption + prompt immagine, informato dagli
   insight dei post precedenti (i temi con più like vengono favoriti)
2. Immagine generata via openrouter_image_service (Gemini image)
3. Salvata in static/ig_posts/ → URL pubblico
4. Pubblicata via Graph API (container → publish) sull'account IG
   collegato alla pagina Facebook
5. Insight (like/commenti) raccolti periodicamente e usati al punto 1

Env:
- IG_PUBLISHER_ENABLED=1   abilita lo scheduler (default: off)
- IG_PUBLISH_TIMES         orari Europe/Rome, default "10:30,17:30"
- PUBLIC_BASE_URL          default https://genesi.lucadigitale.eu

Permessi token pagina richiesti: instagram_content_publish (pubblicazione),
instagram_basic. Fail-silent: ogni errore è loggato, mai propagato.
"""

import asyncio
import base64
import json
import logging
import os
import time
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx

from core.log import log

logger = logging.getLogger(__name__)

GRAPH = "https://graph.facebook.com/v19.0"
STATE_FILE = "memory/ig_publisher.json"
IMG_DIR = "static/ig_posts"
TZ_ROME = ZoneInfo("Europe/Rome")

_ig_user_id_cache: str | None = None


def _page_token() -> str:
    return os.getenv("FB_PAGE_ACCESS_TOKEN", "")


def _enabled() -> bool:
    return os.getenv("IG_PUBLISHER_ENABLED", "") in ("1", "true", "yes")


def _publish_times() -> list[str]:
    raw = os.getenv("IG_PUBLISH_TIMES", "10:30,17:30")
    return [t.strip() for t in raw.split(",") if t.strip()]


def _public_base() -> str:
    return os.getenv("PUBLIC_BASE_URL", "https://genesi.lucadigitale.eu").rstrip("/")


# ── State ─────────────────────────────────────────────────────────────────────

def _load_state() -> dict:
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"posts": [], "published_slots": {}}


def _save_state(state: dict):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error("IG_PUB_STATE_SAVE_ERROR err=%s", e)


# ── Graph API helpers ─────────────────────────────────────────────────────────

async def get_ig_user_id() -> str:
    """ID dell'account Instagram business collegato alla pagina (cached)."""
    global _ig_user_id_cache
    if _ig_user_id_cache:
        return _ig_user_id_cache
    token = _page_token()
    if not token:
        return ""
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.get(
                f"{GRAPH}/me",
                params={"fields": "instagram_business_account", "access_token": token},
            )
            data = res.json()
            _ig_user_id_cache = (data.get("instagram_business_account") or {}).get("id", "")
            return _ig_user_id_cache
    except Exception as e:
        logger.error("IG_PUB_USER_ID_ERROR err=%s", e)
        return ""


# ── Content generation ────────────────────────────────────────────────────────

_CONTENT_PROMPT = """Sei il social media manager di "Genesi", un'assistente AI familiare italiana
(account Instagram @genesiai_official). Genera UN post Instagram.

LINEE GUIDA:
- Temi possibili: tecnologia e vita quotidiana, famiglia e ricordi, curiosità sull'AI,
  benessere digitale, momenti di vita italiana, natura e stagioni, motivazione, cucina e tradizioni.
- La caption: in italiano, calda e genuina, 2-4 frasi, MAI piatta o da marketing aggressivo.
  Chiudi con una domanda che invita al commento. Aggiungi 5-8 hashtag pertinenti in italiano.
- Il prompt immagine: in inglese, descrittivo e fotografico/artistico, senza testo nell'immagine,
  senza persone riconoscibili, stile coerente (warm, cozy, italian lifestyle, soft light).

{insights_block}

Rispondi SOLO con JSON valido:
{{"theme": "tema breve", "caption": "testo caption con hashtag", "image_prompt": "english image prompt"}}"""


async def _generate_content(state: dict) -> dict | None:
    """LLM genera tema, caption e prompt immagine, informato dagli insight."""
    try:
        from core.llm_service import llm_service

        # Blocco insight: temi recenti e loro performance
        recent = state.get("posts", [])[-10:]
        if recent:
            lines = [
                f"- tema '{p.get('theme')}': {p.get('likes', 0)} like, {p.get('comments_count', 0)} commenti"
                for p in recent
            ]
            insights_block = (
                "PERFORMANCE POST RECENTI (favorisci i temi con più like, "
                "ma non ripetere lo stesso tema degli ultimi 2 post):\n" + "\n".join(lines)
            )
        else:
            insights_block = "Nessun post precedente: scegli liberamente un tema."

        prompt = _CONTENT_PROMPT.format(insights_block=insights_block)
        raw = await llm_service._call_model(
            "openai/gpt-4o-mini", prompt,
            "Genera il prossimo post Instagram.",
            user_id="ig_publisher", route="memory",
        )
        clean = (raw or "").strip()
        if clean.startswith("```"):
            clean = clean.strip("`").lstrip("json").strip()
        data = json.loads(clean)
        if data.get("caption") and data.get("image_prompt"):
            return data
        return None
    except Exception as e:
        logger.error("IG_PUB_CONTENT_ERROR err=%s", e)
        return None


async def _create_image(image_prompt: str) -> str:
    """Genera l'immagine e la salva in static/ig_posts/. Ritorna l'URL pubblico."""
    try:
        from core.openrouter_image_service import openrouter_image_service

        data_url = await openrouter_image_service.generate_image(image_prompt, user_id="ig_publisher")
        if not data_url or "," not in data_url:
            return ""
        header, b64 = data_url.split(",", 1)
        ext = "png" if "png" in header else "jpg"
        img_bytes = base64.b64decode(b64)

        os.makedirs(IMG_DIR, exist_ok=True)
        fname = f"{uuid.uuid4().hex}.{ext}"
        with open(os.path.join(IMG_DIR, fname), "wb") as f:
            f.write(img_bytes)

        return f"{_public_base()}/static/ig_posts/{fname}"
    except Exception as e:
        logger.error("IG_PUB_IMAGE_ERROR err=%s", e)
        return ""


# ── Publishing ────────────────────────────────────────────────────────────────

async def publish_one_post() -> bool:
    """Genera e pubblica un post completo. Ritorna True se pubblicato."""
    token = _page_token()
    ig_id = await get_ig_user_id()
    if not token or not ig_id:
        logger.warning("IG_PUB_SKIP no_token_or_ig_id")
        return False

    state = _load_state()
    content = await _generate_content(state)
    if not content:
        return False

    image_url = await _create_image(content["image_prompt"])
    if not image_url:
        return False

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            # 1. Crea il container media
            res = await client.post(
                f"{GRAPH}/{ig_id}/media",
                data={
                    "image_url": image_url,
                    "caption": content["caption"][:2200],
                    "access_token": token,
                },
            )
            cdata = res.json()
            creation_id = cdata.get("id")
            if not creation_id:
                logger.error("IG_PUB_CONTAINER_FAIL body=%.300s", res.text)
                return False

            # 2. Attendi che il container sia pronto (l'immagine va scaricata da IG)
            for _ in range(12):
                await asyncio.sleep(5)
                st = await client.get(
                    f"{GRAPH}/{creation_id}",
                    params={"fields": "status_code", "access_token": token},
                )
                if st.json().get("status_code") == "FINISHED":
                    break

            # 3. Pubblica
            res = await client.post(
                f"{GRAPH}/{ig_id}/media_publish",
                data={"creation_id": creation_id, "access_token": token},
            )
            pdata = res.json()
            media_id = pdata.get("id")
            if not media_id:
                logger.error("IG_PUB_PUBLISH_FAIL body=%.300s", res.text)
                return False

        state.setdefault("posts", []).append({
            "media_id": media_id,
            "theme": content.get("theme", ""),
            "caption": content["caption"][:200],
            "image_url": image_url,
            "ts": int(time.time()),
            "likes": 0,
            "comments_count": 0,
        })
        state["posts"] = state["posts"][-100:]
        _save_state(state)

        log("IG_POST_PUBLISHED", media_id=media_id, theme=content.get("theme", ""))
        logger.info("IG_POST_PUBLISHED media_id=%s theme=%s", media_id, content.get("theme"))
        return True

    except Exception as e:
        logger.error("IG_PUB_ERROR err=%s", e)
        return False


# ── Dedup risposte commenti (condiviso webhook + polling) ───────────────────

def is_comment_replied(comment_id: str) -> bool:
    state = _load_state()
    return comment_id in state.get("replied_comments", [])


def mark_comment_replied(comment_id: str):
    state = _load_state()
    replied = state.setdefault("replied_comments", [])
    if comment_id not in replied:
        replied.append(comment_id)
        state["replied_comments"] = replied[-500:]
        _save_state(state)


# ── Polling commenti (fallback se i webhook non arrivano) ───────────────────

async def poll_and_reply_comments():
    """
    Controlla i commenti sui post recenti e risponde a quelli nuovi.
    Fallback robusto: i webhook comments via flusso pagina possono non
    arrivare; questo polling garantisce che nessun commento resti ignorato.
    """
    token = _page_token()
    ig_id = await get_ig_user_id()
    if not token or not ig_id:
        return

    state = _load_state()
    posts = state.get("posts", [])[-5:]
    if not posts:
        return

    try:
        from core.meta_messaging_bot import reply_to_comment
        async with httpx.AsyncClient(timeout=30) as client:
            for p in posts:
                mid = p.get("media_id")
                if not mid:
                    continue
                res = await client.get(
                    f"{GRAPH}/{mid}/comments",
                    params={"fields": "id,text,username,from", "access_token": token},
                )
                for c in (res.json().get("data") or []):
                    cid = c.get("id", "")
                    text = (c.get("text") or "").strip()
                    from_id = str((c.get("from") or {}).get("id", ""))
                    if not cid or not text:
                        continue
                    # Anti-loop: salta i commenti/risposte di Genesi stessa
                    if from_id == str(ig_id):
                        continue
                    if is_comment_replied(cid):
                        continue
                    ok = await reply_to_comment(cid, c.get("username", ""), text)
                    if ok:
                        mark_comment_replied(cid)
                    await asyncio.sleep(2)
    except Exception as e:
        logger.error("IG_COMMENT_POLL_ERROR err=%s", e)


# ── Insights (apprendimento da like/commenti) ────────────────────────────────

async def refresh_insights():
    """Aggiorna like/commenti dei post recenti — alimenta la scelta dei temi."""
    token = _page_token()
    if not token:
        return
    state = _load_state()
    posts = state.get("posts", [])[-20:]
    if not posts:
        return
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            for p in posts:
                mid = p.get("media_id")
                if not mid:
                    continue
                res = await client.get(
                    f"{GRAPH}/{mid}",
                    params={"fields": "like_count,comments_count", "access_token": token},
                )
                d = res.json()
                if "like_count" in d:
                    p["likes"] = d.get("like_count", 0)
                    p["comments_count"] = d.get("comments_count", 0)
        _save_state(state)
        log("IG_INSIGHTS_REFRESHED", posts=len(posts))
    except Exception as e:
        logger.error("IG_INSIGHTS_ERROR err=%s", e)


# ── Scheduler ─────────────────────────────────────────────────────────────────

async def instagram_publisher_scheduler():
    """
    Loop: controlla ogni 5 minuti se è ora di pubblicare (orari IG_PUBLISH_TIMES,
    timezone Europe/Rome). Ogni slot pubblica al massimo una volta al giorno.
    Insights aggiornati una volta ogni ~6 ore.
    """
    last_insights = 0.0
    while True:
        try:
            if _enabled():
                now = datetime.now(TZ_ROME)
                today = now.strftime("%Y-%m-%d")
                now_hm = now.strftime("%H:%M")

                state = _load_state()
                slots_done = state.setdefault("published_slots", {}).get(today, [])

                for slot in _publish_times():
                    if slot not in slots_done and now_hm >= slot:
                        logger.info("IG_PUB_SLOT_TRIGGER slot=%s", slot)
                        ok = await publish_one_post()
                        # Marca lo slot anche se fallito: evita retry-loop infiniti
                        # (il post mancato si recupera allo slot successivo)
                        state = _load_state()
                        state.setdefault("published_slots", {}).setdefault(today, []).append(slot)
                        # Pulizia: tieni solo gli ultimi 7 giorni
                        ps = state["published_slots"]
                        if len(ps) > 7:
                            for k in sorted(ps.keys())[:-7]:
                                ps.pop(k, None)
                        _save_state(state)
                        log("IG_PUB_SLOT_DONE", slot=slot, published=ok)

                # Polling commenti ad ogni ciclo (5 min) — fallback dei webhook
                await poll_and_reply_comments()

                if time.time() - last_insights > 6 * 3600:
                    await refresh_insights()
                    last_insights = time.time()

        except Exception as e:
            logger.error("IG_PUB_SCHEDULER_ERROR err=%s", e)

        await asyncio.sleep(300)
