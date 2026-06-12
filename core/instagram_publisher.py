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

{news_block}

LINEE GUIDA:
- Se ci sono NOTIZIE REALI sopra, DEVI costruire il post su una di esse
  (preferisci tecnologia, scienza, mondo, eventi positivi o di interesse
  pubblico): il post deve sembrare ATTUALE, ancorato all'oggi. Nel campo
  "news_ref" riporta il titolo della notizia scelta.
- Tono sempre rispettoso e costruttivo; per fatti drammatici usa immagini
  simboliche/evocative, MAI esplicite o macabre. SOLO se TUTTE le notizie
  sono cronaca nera inadatta, usa un tema evergreen e metti news_ref=null.
- Temi evergreen di riserva: tecnologia e vita quotidiana, famiglia e ricordi,
  curiosità sull'AI, benessere digitale, momenti di vita italiana, natura e
  stagioni, motivazione, cucina e tradizioni.
- La caption: in italiano, calda e genuina, 2-4 frasi, MAI piatta o da marketing
  aggressivo. Se basata su una notizia, raccontala con la voce di Genesi.
  Chiudi con una domanda che invita al commento. Aggiungi 5-8 hashtag pertinenti.
- Il prompt immagine: in inglese, descrittivo e fotografico/artistico, senza testo
  nell'immagine, senza persone riconoscibili, stile coerente (warm, cozy,
  italian lifestyle, soft light).

{insights_block}

Rispondi SOLO con JSON valido:
{{"theme": "tema breve", "news_ref": "titolo notizia scelta oppure null",
 "caption": "testo caption con hashtag", "image_prompt": "english image prompt"}}"""


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

        # Notizie reali del giorno: anche i post si ancorano all'attualità
        news = await _fetch_current_news()
        news_block = (f"NOTIZIE REALI DI OGGI (fonte GNews):\n{news}" if news
                      else "Nessuna notizia disponibile oggi.")

        prompt = _CONTENT_PROMPT.format(insights_block=insights_block,
                                        news_block=news_block)
        user_msg = ("Genera il prossimo post basandolo su UNA delle notizie elencate."
                    if news else "Genera il prossimo post Instagram.")
        data = None
        for attempt in range(2):
            raw = await llm_service._call_model(
                "openai/gpt-4o-mini", prompt, user_msg,
                user_id="ig_publisher", route="memory",
            )
            clean = (raw or "").strip()
            if clean.startswith("```"):
                clean = clean.strip("`").lstrip("json").strip()
            try:
                data = json.loads(clean)
            except Exception:
                data = None
            _nref = (data or {}).get("news_ref")
            if news and (not _nref or str(_nref).lower() == "null") and attempt == 0:
                logger.info("IG_PUB_NEWS_ENFORCE retry: news_ref mancante")
                user_msg = ("OBBLIGATORIO: scegli una notizia dall'elenco e compila "
                            "news_ref con il suo titolo. Non usare temi evergreen.")
                continue
            break
        if data and data.get("caption") and data.get("image_prompt"):
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

            # 3. Pubblica — con retry sugli errori transitori di Instagram
            # (capita un 500 "is_transient: please retry" che perdeva il post)
            media_id = None
            for _try in range(4):
                res = await client.post(
                    f"{GRAPH}/{ig_id}/media_publish",
                    data={"creation_id": creation_id, "access_token": token},
                )
                pdata = res.json()
                media_id = pdata.get("id")
                if media_id:
                    break
                _err = (pdata.get("error") or {})
                if _err.get("is_transient") or res.status_code >= 500:
                    logger.warning("IG_PUB_PUBLISH_TRANSIENT try=%d body=%.200s",
                                   _try, res.text)
                    await asyncio.sleep(15 * (_try + 1))
                    continue
                logger.error("IG_PUB_PUBLISH_FAIL body=%.300s", res.text)
                return False
            if not media_id:
                logger.error("IG_PUB_PUBLISH_FAIL retries_exhausted")
                return False

        state.setdefault("posts", []).append({
            "media_id": media_id,
            "theme": content.get("theme", ""),
            "news_ref": content.get("news_ref") or None,
            "caption": content["caption"][:200],
            "image_url": image_url,
            "ts": int(time.time()),
            "likes": 0,
            "comments_count": 0,
        })
        state["posts"] = state["posts"][-100:]
        _save_state(state)

        log("IG_POST_PUBLISHED", media_id=media_id, theme=content.get("theme", ""),
            news_ref=(content.get("news_ref") or "")[:80])
        logger.info("IG_POST_PUBLISHED media_id=%s theme=%s", media_id, content.get("theme"))
        return True

    except Exception as e:
        logger.error("IG_PUB_ERROR err=%s", e)
        return False


# ── REELS: generazione e pubblicazione video originali ──────────────────────

def _reels_times() -> list[str]:
    raw = os.getenv("IG_REELS_TIMES", "13:00")
    return [t.strip() for t in raw.split(",") if t.strip()]


def manual_reel_allowed() -> tuple[bool, int]:
    """
    Cooldown per i Reel su comando (anti spese accidentali):
    default 30 min tra una richiesta e l'altra (IG_REEL_MANUAL_COOLDOWN sec).
    Ritorna (consentito, secondi_rimanenti).
    """
    state = _load_state()
    last = state.get("last_manual_reel_ts", 0)
    wait = int(os.getenv("IG_REEL_MANUAL_COOLDOWN", "1800"))
    rem = int(last + wait - time.time())
    return (rem <= 0, max(rem, 0))


def mark_manual_reel():
    state = _load_state()
    state["last_manual_reel_ts"] = int(time.time())
    _save_state(state)


def _reel_due(state: dict) -> bool:
    """
    True se è passato l'intervallo configurato dall'ultimo Reel
    (IG_REELS_EVERY_DAYS, default 3 giorni). Contiene i costi:
    ~4 immagini AI a Reel.
    """
    try:
        every_days = int(os.getenv("IG_REELS_EVERY_DAYS", "3"))
    except Exception:
        every_days = 3
    reels = [p for p in state.get("posts", []) if p.get("type") == "reel"]
    if not reels:
        return True
    last_ts = max(p.get("ts", 0) for p in reels)
    # margine di 1h: il Reel del giorno N esce allo slot anche con piccoli ritardi
    return (time.time() - last_ts) >= (every_days * 86400 - 3600)


async def _fetch_current_news(limit: int = 8) -> str:
    """
    Legge le notizie REALI del giorno (GNews: cronaca, politica, tecnologia,
    attualità italiana) per ancorare i Reel al presente. Fail-silent.
    """
    key = os.getenv("GNEWS_API_KEY", "")
    if not key:
        return ""
    lines: list[str] = []
    try:
        # nation vincolato all'Italia; tecnologia/mondo/scienza in italiano
        # senza vincolo country (le testate tech italiane coprono temi globali)
        queries = [
            ("nation",     {"lang": "it", "country": "it", "category": "nation"}),
            ("technology", {"lang": "it", "category": "technology"}),
            ("world",      {"lang": "it", "category": "world"}),
            ("science",    {"lang": "it", "category": "science"}),
        ]
        async with httpx.AsyncClient(timeout=20) as client:
            for qi, (topic, params) in enumerate(queries):
                if qi:
                    await asyncio.sleep(1.5)  # GNews free: rate limit sul burst
                try:
                    params = dict(params, max=3, apikey=key)
                    res = await client.get(
                        "https://gnews.io/api/v4/top-headlines", params=params)
                    for a in (res.json().get("articles") or [])[:3]:
                        t = (a.get("title") or "").strip()
                        d = (a.get("description") or "").strip()
                        if t:
                            lines.append(f"- [{topic}] {t}" + (f" — {d[:140]}" if d else ""))
                except Exception:
                    continue
        log("IG_REEL_NEWS_FETCHED", count=len(lines))
    except Exception as e:
        logger.warning("IG_REEL_NEWS_ERR err=%s", e)
    return "\n".join(lines[:limit])


_REEL_CONTENT_PROMPT = """Sei il social media manager di "Genesi", assistente AI familiare italiana
(@genesiai_official). Progetta un REEL breve (15 secondi, 4 scene visive in sequenza).

{news_block}

LINEE GUIDA:
- Se ci sono NOTIZIE REALI sopra, DEVI costruire il Reel su una di esse
  (preferisci tecnologia, scienza, mondo, eventi positivi o di interesse
  pubblico): il Reel deve sembrare ATTUALE, ancorato all'oggi. Nel campo
  "news_ref" riporta il titolo della notizia scelta.
- Tono sempre rispettoso e costruttivo; per fatti drammatici usa scene
  simboliche/evocative, MAI esplicite o macabre. SOLO se TUTTE le notizie
  sono cronaca nera inadatta, usa un tema evergreen e metti news_ref=null.
- Temi evergreen di riserva: vita quotidiana italiana, natura e stagioni,
  famiglia e ricordi, curiosità AI, benessere, cucina, paesaggi.
- Le 4 scene devono raccontare una mini-storia visiva COERENTE (stesso stile, stessa
  palette): es. alba → mattina → tramonto → notte sullo stesso luogo.
- scene_prompts: in inglese, fotografici/cinematografici, formato VERTICALE,
  senza testo nell'immagine, senza persone riconoscibili, stile coerente
  (warm tones, italian aesthetic, cinematic light). Ripeti lo stile in ogni prompt.
- caption: italiana, calda, 2-3 frasi + domanda + 5-8 hashtag.
- narration: il testo che la voce di Genesi narra sopra il video — italiano,
  caldo e poetico, tra 35 e 45 parole (~15 secondi di parlato), una frase
  per ciascuna delle 4 scene, in sequenza. Niente hashtag, niente emoji:
  solo parole da ascoltare.

{insights_block}

Rispondi SOLO con JSON valido:
{{"theme": "tema", "news_ref": "titolo notizia scelta oppure null",
 "caption": "caption con hashtag",
 "narration": "testo narrato 35-45 parole",
 "scene_prompts": ["scena 1", "scena 2", "scena 3", "scena 4"]}}"""


async def _generate_reel_content(state: dict, custom_theme: str = "") -> dict | None:
    """
    LLM progetta il Reel: tema, caption e 4 prompt di scena coerenti.
    custom_theme (richiesta diretta dell'utente via chat) ha priorità
    ASSOLUTA su notizie ed evergreen.
    """
    try:
        from core.llm_service import llm_service
        recent = [p for p in state.get("posts", []) if p.get("type") == "reel"][-6:]
        if recent:
            lines = [f"- tema '{p.get('theme')}': {p.get('likes', 0)} like" for p in recent]
            insights_block = ("PERFORMANCE REEL RECENTI (favorisci i temi con più like, "
                              "non ripetere l'ultimo tema):\n" + "\n".join(lines))
        else:
            insights_block = "Nessun Reel precedente: scegli liberamente."

        # Richiesta diretta dell'utente → vince su notizie ed evergreen
        if custom_theme:
            news = ""
            news_block = ("RICHIESTA DIRETTA DELL'UTENTE (priorità assoluta, ignora "
                          f"notizie ed evergreen):\n{custom_theme}\n"
                          "Costruisci il Reel ESATTAMENTE su questo tema/istruzioni. "
                          "news_ref=null.")
            user_msg = "Progetta il Reel seguendo la richiesta dell'utente."
        else:
            # Notizie reali del giorno: il Reel si ancora all'attualità
            news = await _fetch_current_news()
            news_block = (f"NOTIZIE REALI DI OGGI (fonte GNews):\n{news}" if news
                          else "Nessuna notizia disponibile oggi.")
            user_msg = ("Progetta il prossimo Reel basandolo su UNA delle notizie elencate."
                        if news else "Progetta il prossimo Reel.")
        data = None
        for attempt in range(2):
            raw = await llm_service._call_model(
                "openai/gpt-4o-mini",
                _REEL_CONTENT_PROMPT.format(insights_block=insights_block,
                                            news_block=news_block),
                user_msg, user_id="ig_publisher", route="memory")
            clean = (raw or "").strip()
            if clean.startswith("```"):
                clean = clean.strip("`").lstrip("json").strip()
            try:
                data = json.loads(clean)
            except Exception:
                data = None
            # Enforcement: con notizie disponibili news_ref è OBBLIGATORIO
            _nref = (data or {}).get("news_ref")
            if news and (not _nref or str(_nref).lower() == "null") and attempt == 0:
                logger.info("IG_REEL_NEWS_ENFORCE retry: news_ref mancante")
                user_msg = ("OBBLIGATORIO: scegli una notizia dall'elenco e compila "
                            "news_ref con il suo titolo. Non usare temi evergreen.")
                continue
            break
        if not data:
            return None
        scenes = data.get("scene_prompts") or []
        if data.get("caption") and len(scenes) >= 3:
            data["scene_prompts"] = scenes[:4]
            return data
        return None
    except Exception as e:
        logger.error("IG_REEL_CONTENT_ERROR err=%s", e)
        return None


_REEL_TTS_INSTRUCTIONS = (
    "Voce sussurrata, intima e teatrale, come la narrazione di un documentario "
    "poetico o di un trailer cinematografico. Italiano madrelingua, accento "
    "italiano naturale. Ritmo lento, pause espressive, intensità emotiva "
    "crescente. Quasi un sussurro confidenziale all'orecchio di chi ascolta."
)


async def _synthesize_narration(text: str, out_path: str) -> bool:
    """
    Voce di Genesi per la narrazione del Reel.
    Primaria: OpenAI gpt-4o-mini-tts voce Fable con istruzioni TEATRALI
    (sussurrata, da trailer — scelta utente). Costo: centesimi per ~15s.
    Fallback: EdgeTTS (gratis) → Piper locale.
    """
    # 1° tentativo: OpenAI Fable teatrale
    try:
        from core.tts_provider import OpenAITTSProvider
        voice = os.getenv("IG_REEL_OPENAI_VOICE", "fable")
        instructions = os.getenv("IG_REEL_TTS_INSTRUCTIONS", _REEL_TTS_INSTRUCTIONS)
        p = OpenAITTSProvider(voice=voice, model="gpt-4o-mini-tts",
                              instructions=instructions)
        audio = await p.synthesize(text)
        if audio and len(audio) > 1000:
            with open(out_path, "wb") as f:
                f.write(audio)
            logger.info("IG_REEL_TTS_OPENAI_OK voice=%s bytes=%d", voice, len(audio))
            return True
    except Exception as e:
        logger.warning("IG_REEL_TTS_OPENAI_ERR err=%s", e)

    # 2° tentativo: EdgeTTS (voce neurale gratuita)
    try:
        from core.tts_provider import EdgeTTSProvider
        voice = os.getenv("IG_REEL_VOICE", "it-IT-IsabellaNeural")
        audio = await EdgeTTSProvider(voice=voice).synthesize(text)
        if audio and len(audio) > 1000:
            with open(out_path, "wb") as f:
                f.write(audio)
            logger.info("IG_REEL_TTS_EDGE_OK voice=%s bytes=%d", voice, len(audio))
            return True
    except Exception as e:
        logger.warning("IG_REEL_TTS_EDGE_ERR err=%s", e)

    # Fallback: Piper locale
    import subprocess
    try:
        piper_bin = os.getenv("PIPER_BINARY", "/opt/piper/piper/piper")
        piper_model = os.getenv("PIPER_MODEL", "/opt/piper/voices/it_IT-paola-medium.onnx")
        if not (os.path.exists(piper_bin) and os.path.exists(piper_model)):
            return False
        r = subprocess.run([piper_bin, "--model", piper_model, "--output_file", out_path],
                           input=text.encode(), capture_output=True, timeout=90)
        return r.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 1000
    except Exception as e:
        logger.warning("IG_REEL_TTS_ERROR err=%s", e)
        return False


def _build_reel_video(image_paths: list[str], out_path: str,
                      narration_wav: str = "", seg_seconds: float = 3.0) -> bool:
    """
    Monta le immagini in un video verticale 1080x1920 con effetto Ken Burns
    (zoom lento) — seg_seconds a scena, 25fps. Se narration_wav è presente,
    la voce di Genesi viene muxata sull'audio. Costo zero (ffmpeg locale).
    """
    import subprocess
    try:
        seg_seconds = max(2.0, min(float(seg_seconds or 3.0), 6.0))
        d_frames = int(seg_seconds * 25)
        zoom_step = round(0.15 / d_frames, 6)
        seg_paths = []
        for i, img in enumerate(image_paths):
            seg = out_path + f".seg{i}.mp4"
            zoom_dir = (f"min(zoom+{zoom_step},1.15)" if i % 2 == 0
                        else f"if(eq(on,1),1.15,max(zoom-{zoom_step},1.0))")
            r = subprocess.run([
                "ffmpeg", "-y", "-loop", "1", "-i", img, "-t", f"{seg_seconds:.2f}",
                "-vf", (f"scale=1080:1920:force_original_aspect_ratio=increase,"
                        f"crop=1080:1920,zoompan=z='{zoom_dir}':d={d_frames}:s=1080x1920:fps=25"),
                "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "fast", seg,
            ], capture_output=True, timeout=180)
            if os.path.exists(seg) and os.path.getsize(seg) > 1000:
                seg_paths.append(seg)
            else:
                logger.error("IG_REEL_SEG_FAIL i=%d rc=%s stderr=%.300s",
                             i, r.returncode, r.stderr.decode(errors="replace")[-300:])

        if len(seg_paths) < 2:
            return False

        # Concatenazione — path ASSOLUTI: ffmpeg risolve i path del file-lista
        # relativi alla directory della lista, non alla cwd
        list_path = out_path + ".list.txt"
        with open(list_path, "w") as f:
            for s in seg_paths:
                f.write(f"file '{os.path.abspath(s)}'\n")
        # Senza narrazione: concat diretto. Con narrazione: concat in un file
        # intermedio, poi mux della voce (apad riempie di silenzio fino alla
        # fine del video, -shortest taglia alla durata del video)
        concat_out = out_path + ".noaudio.mp4" if narration_wav else out_path
        rc = subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0",
                             "-i", list_path, "-c", "copy", concat_out],
                            capture_output=True, timeout=60)
        if rc.returncode != 0:
            logger.error("IG_REEL_CONCAT_FAIL rc=%s stderr=%.300s",
                         rc.returncode, rc.stderr.decode(errors="replace")[-300:])

        if narration_wav and os.path.exists(concat_out):
            rc2 = subprocess.run(
                ["ffmpeg", "-y", "-i", concat_out, "-i", narration_wav,
                 "-c:v", "copy", "-c:a", "aac", "-b:a", "128k",
                 "-af", "apad", "-shortest", out_path],
                capture_output=True, timeout=60)
            if rc2.returncode != 0:
                logger.error("IG_REEL_MUX_FAIL rc=%s stderr=%.300s",
                             rc2.returncode, rc2.stderr.decode(errors="replace")[-300:])
                # Fallback: pubblica senza audio piuttosto che fallire
                os.replace(concat_out, out_path)
            else:
                try:
                    os.unlink(concat_out)
                except Exception:
                    pass

        for s in seg_paths + [list_path]:
            try:
                os.unlink(s)
            except Exception:
                pass
        return os.path.exists(out_path) and os.path.getsize(out_path) > 10000
    except Exception as e:
        logger.error("IG_REEL_VIDEO_BUILD_ERROR err=%s", e)
        return False


async def publish_one_reel(custom_theme: str = "") -> bool:
    """
    Genera e pubblica un Reel completo. Ritorna True se pubblicato.
    custom_theme: tema/istruzioni dell'utente (richiesta diretta via chat).
    """
    token = _page_token()
    ig_id = await get_ig_user_id()
    if not token or not ig_id:
        logger.warning("IG_REEL_SKIP no_token_or_ig_id")
        return False

    state = _load_state()
    content = await _generate_reel_content(state, custom_theme=custom_theme)
    if not content:
        return False

    # Genera le immagini delle scene (il grosso del costo: ~4 immagini)
    frame_paths: list[str] = []
    try:
        from core.openrouter_image_service import openrouter_image_service
        os.makedirs(IMG_DIR, exist_ok=True)
        for i, prompt in enumerate(content["scene_prompts"]):
            data_url = None
            for attempt in range(2):  # 1 retry per scena
                data_url = await openrouter_image_service.generate_image(
                    prompt + " — vertical 9:16 composition", user_id="ig_publisher")
                if data_url and "," in data_url:
                    break
                await asyncio.sleep(3)
            logger.info("IG_REEL_FRAME scene=%d ok=%s", i, bool(data_url and "," in data_url))
            if not data_url or "," not in data_url:
                continue
            img_bytes = base64.b64decode(data_url.split(",", 1)[1])
            fp = os.path.join(IMG_DIR, f"reel_{uuid.uuid4().hex[:8]}_{i}.jpg")
            with open(fp, "wb") as f:
                f.write(img_bytes)
            frame_paths.append(fp)
    except Exception as e:
        logger.error("IG_REEL_FRAMES_ERROR err=%s", e)

    if len(frame_paths) < 3:
        logger.warning("IG_REEL_FRAMES_INSUFFICIENT got=%d need=3", len(frame_paths))
        for fp in frame_paths:
            try:
                os.unlink(fp)
            except Exception:
                pass
        return False

    # Voce di Genesi (narrazione) — locale, costo zero
    narration_wav = ""
    narration_text = (content.get("narration") or "").strip()
    if narration_text:
        # Edge produce MP3, Piper WAV — ffmpeg li accetta entrambi
        _wav = os.path.join(IMG_DIR, f"reel_voice_{uuid.uuid4().hex[:8]}.audio")
        if await _synthesize_narration(narration_text, _wav):
            narration_wav = _wav
            logger.info("IG_REEL_NARRATION ok=True words=%d", len(narration_text.split()))
        else:
            logger.info("IG_REEL_NARRATION ok=False (video senza audio)")

    # La durata delle scene si adatta alla voce: il video dura quanto la
    # narrazione (+0.8s di coda), così non resta mai silenzio
    seg_seconds = 3.0
    if narration_wav:
        try:
            from core.video_vision_service import _ffprobe_duration
            audio_dur = _ffprobe_duration(narration_wav)
            if audio_dur > 1.0:
                seg_seconds = (audio_dur + 0.8) / max(len(frame_paths), 1)
                logger.info("IG_REEL_TIMING audio=%.1fs scenes=%d seg=%.2fs",
                            audio_dur, len(frame_paths), seg_seconds)
        except Exception as _te:
            logger.debug("IG_REEL_TIMING_ERR %s", _te)

    # Monta il video
    video_name = f"reel_{uuid.uuid4().hex}.mp4"
    video_path = os.path.join(IMG_DIR, video_name)
    ok = await asyncio.to_thread(_build_reel_video, frame_paths, video_path,
                                 narration_wav, seg_seconds)
    if narration_wav:
        try:
            os.unlink(narration_wav)
        except Exception:
            pass
    logger.info("IG_REEL_BUILD ok=%s size=%s", ok,
                os.path.getsize(video_path) if os.path.exists(video_path) else "missing")
    for fp in frame_paths:
        try:
            os.unlink(fp)
        except Exception:
            pass
    if not ok:
        return False

    video_url = f"{_public_base()}/static/ig_posts/{video_name}"
    logger.info("IG_REEL_VIDEO_URL url=%s", video_url)

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            # 1. Container REELS
            res = await client.post(
                f"{GRAPH}/{ig_id}/media",
                data={"media_type": "REELS", "video_url": video_url,
                      "caption": content["caption"][:2200], "access_token": token})
            creation_id = res.json().get("id")
            if not creation_id:
                logger.error("IG_REEL_CONTAINER_FAIL body=%.300s", res.text)
                return False

            logger.info("IG_REEL_CONTAINER id=%s", creation_id)
            # 2. Attendi l'elaborazione video (più lunga delle foto)
            published = False
            for _poll in range(30):
                await asyncio.sleep(6)
                st = await client.get(f"{GRAPH}/{creation_id}",
                                      params={"fields": "status_code,status", "access_token": token})
                code = st.json().get("status_code")
                if _poll % 5 == 0 or code in ("FINISHED", "ERROR"):
                    logger.info("IG_REEL_STATUS poll=%d code=%s detail=%.150s",
                                _poll, code, str(st.json().get("status", "")))
                if code == "FINISHED":
                    published = True
                    break
                if code == "ERROR":
                    logger.error("IG_REEL_PROCESSING_ERROR body=%.200s", st.text)
                    return False
            if not published:
                logger.error("IG_REEL_PROCESSING_TIMEOUT")
                return False

            # 3. Pubblica — con retry sugli errori transitori di Instagram
            media_id = None
            for _try in range(4):
                res = await client.post(f"{GRAPH}/{ig_id}/media_publish",
                                        data={"creation_id": creation_id, "access_token": token})
                pdata = res.json()
                media_id = pdata.get("id")
                if media_id:
                    break
                _err = (pdata.get("error") or {})
                if _err.get("is_transient") or res.status_code >= 500:
                    logger.warning("IG_REEL_PUBLISH_TRANSIENT try=%d body=%.200s",
                                   _try, res.text)
                    await asyncio.sleep(15 * (_try + 1))
                    continue
                logger.error("IG_REEL_PUBLISH_FAIL body=%.300s", res.text)
                return False
            if not media_id:
                logger.error("IG_REEL_PUBLISH_FAIL retries_exhausted")
                return False

        state = _load_state()
        state.setdefault("posts", []).append({
            "media_id": media_id, "type": "reel",
            "theme": content.get("theme", ""),
            "news_ref": content.get("news_ref") or None,
            "caption": content["caption"][:200],
            "ts": int(time.time()), "likes": 0, "comments_count": 0,
        })
        state["posts"] = state["posts"][-100:]
        _save_state(state)
        log("IG_REEL_PUBLISHED", media_id=media_id, theme=content.get("theme", ""),
            news_ref=(content.get("news_ref") or "")[:80])
        return True

    except Exception as e:
        logger.error("IG_REEL_ERROR err=%s", e)
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

                # Reel ogni IG_REELS_EVERY_DAYS giorni (default 3) allo slot orario
                for slot in _reels_times():
                    _rslot = f"reel@{slot}"
                    if _rslot not in slots_done and now_hm >= slot:
                        if not _reel_due(state):
                            # Non è ancora il giorno del Reel: marca lo slot e salta
                            state.setdefault("published_slots", {}).setdefault(today, []).append(_rslot)
                            _save_state(state)
                            slots_done = state["published_slots"].get(today, [])
                            log("IG_REEL_SLOT_SKIP", slot=slot, reason="interval_not_due")
                            continue
                        logger.info("IG_REEL_SLOT_TRIGGER slot=%s", slot)
                        rok = await publish_one_reel()
                        state = _load_state()
                        state.setdefault("published_slots", {}).setdefault(today, []).append(_rslot)
                        _save_state(state)
                        log("IG_REEL_SLOT_DONE", slot=slot, published=rok)
                        slots_done = state["published_slots"].get(today, [])

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
