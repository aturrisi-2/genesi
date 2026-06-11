"""
message_pipeline.py — Pipeline universale Genesi per qualsiasi piattaforma.

Questo modulo è LA FONTE UNICA di verità per tutta la logica che deve funzionare
identicamente su qualsiasi piattaforma (Telegram, WhatsApp, web, e future).

Per aggiungere una NUOVA PIATTAFORMA:
1. Implementa la ricezione/invio nativa (es. Instagram DM adapter)
2. Per ogni foto in arrivo: chiama process_incoming_photo()
3. Per ogni testo in arrivo: chiama process_incoming_text()
4. Chiama simple_chat_handler() per la risposta
5. Chiama schedule_memory_tasks() dopo la risposta

Tutto il resto (face recognition, pet recognition, memoria, audit, behavioral)
è automatico — zero codice aggiuntivo per platform.
"""

import asyncio
import logging
import os
import tempfile

from core.log import log

logger = logging.getLogger("genesi")

# Semaforo per limitare LLM calls concorrenti in background
_BACKGROUND_SEM = asyncio.Semaphore(3)


# ─── PHOTO PROCESSING ─────────────────────────────────────────────────────────

async def process_incoming_photo(
    session_id: str,
    user_id: str,
    img_bytes: bytes,
    platform: str,
    caption: str | None = None,
) -> dict:
    """
    Elabora una foto in arrivo da QUALSIASI piattaforma.

    Esegue in sequenza:
    1. Analisi visiva (GPT-4o vision)
    2. Riconoscimento biometrico volti umani
    3. Riconoscimento biometrico animali domestici
    4. Gestione stato awaiting_faces
    5. Eventuale estrazione nomi da caption

    Returns:
        {
          "analysis": str,           # descrizione visiva completa con tag biometrici
          "sistema_msg": str,        # messaggio [SISTEMA] da appendere all'input utente
          "faces_saved": bool,
          "saved_names": list[str],
          "remaining": int,          # sconosciuti ancora da identificare
          "augmented_caption": str,  # caption + sistema_msg (pronto per la chat)
        }
    """
    from core.image_vision_service import describe_image
    from core.face_memory_service import handle_photo_identification

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False, prefix="genesi_pipe_") as tmp:
            tmp.write(img_bytes)
            tmp_path = tmp.name

        analysis = await describe_image(tmp_path)
        log("PIPELINE_PHOTO_ANALYZED", platform=platform, session=session_id, len=len(analysis))

        face_result = await handle_photo_identification(session_id, img_bytes, analysis, caption)

        augmented_caption = (caption or "") + (face_result.get("sistema_msg") or "")

        log("PIPELINE_PHOTO_DONE", platform=platform, faces_saved=face_result["faces_saved"],
            saved=face_result["saved_names"], remaining=face_result["remaining"])

        return {
            "analysis": analysis,
            "sistema_msg": face_result.get("sistema_msg", ""),
            "faces_saved": face_result.get("faces_saved", False),
            "saved_names": face_result.get("saved_names", []),
            "remaining": face_result.get("remaining", 0),
            "augmented_caption": augmented_caption,
        }

    except Exception as e:
        logger.error("PIPELINE_PHOTO_ERROR platform=%s session=%s err=%s", platform, session_id, e)
        return {
            "analysis": "",
            "sistema_msg": "",
            "faces_saved": False,
            "saved_names": [],
            "remaining": 0,
            "augmented_caption": caption or "",
        }
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass


# ─── TEXT PROCESSING ──────────────────────────────────────────────────────────

async def process_incoming_text(
    session_id: str,
    user_id: str,
    text: str,
    platform: str,
) -> dict:
    """
    Elabora un testo in arrivo da QUALSIASI piattaforma.

    Se c'è uno stato awaiting_faces attivo per questa sessione, tenta di
    estrarre i nomi dall'testo e aggiorna il contatore dei sconosciuti.

    Returns:
        {
          "was_awaiting": bool,
          "augmented_text": str,   # text + sistema_msg se nomi salvati
          "face_result": dict,     # risultato completo di handle_text_identification
        }
    """
    from core.face_memory_service import handle_text_identification

    try:
        face_result = await handle_text_identification(session_id, text)
        augmented = text
        if face_result.get("was_awaiting") and face_result.get("faces_saved"):
            augmented = text + (face_result.get("sistema_msg") or "")

        return {
            "was_awaiting": face_result.get("was_awaiting", False),
            "augmented_text": augmented,
            "face_result": face_result,
        }

    except Exception as e:
        logger.error("PIPELINE_TEXT_ERROR platform=%s session=%s err=%s", platform, session_id, e)
        return {"was_awaiting": False, "augmented_text": text, "face_result": {}}


# ─── MEMORY BACKGROUND TASKS ─────────────────────────────────────────────────

async def schedule_memory_tasks(
    user_id: str,
    user_message: str,
    response: str,
    platform: str,
    intent: str = "chat_free",
    is_group: bool = False,
) -> None:
    """
    Lancia tutti i task di memoria in background dopo ogni risposta.
    Uniforme su TUTTE le piattaforme — zero duplicazione.

    Task lanciati:
    - personal_facts extraction (fatti appresi dalla conversazione)
    - episode extraction (eventi temporali)
    - episode resolution (follow-up su episodi aperti)
    - global memory consolidation (pattern comportamentali cross-sessione)
    - predictive engine update (predizione prossimo turno)
    - behavioral memory update (abitudini di comunicazione)
    - audit trigger (ogni 100 turni, qualità del sistema)
    - capability gap detection (opportunità di miglioramento)

    I task di gruppo (group history, family relationships) rimangono
    nelle rispettive piattaforme perché usano dati platform-specific
    (Telegram member_id, WhatsApp JID, ecc.).
    """
    if not user_message or not response:
        return

    # Task con LLM (usa semaforo per limitare concorrenza)
    async def _personal_facts():
        async with _BACKGROUND_SEM:
            try:
                from core.personal_facts_service import personal_facts_service as _pfs
                await _pfs.extract_and_save(user_message, response, user_id)
            except Exception as e:
                logger.debug("PIPELINE_PERSONAL_FACTS_ERR %s", e)

    async def _episodes():
        async with _BACKGROUND_SEM:
            try:
                from core.episode_extractor import extract_episodes
                from core.episode_memory import episode_memory as _em
                episodes = await extract_episodes(user_message, user_id)
                for ep in episodes:
                    await _em.add(user_id, ep)
                    log("EPISODE_SAVED", user_id=user_id, platform=platform, text=ep.get("text", "")[:60])
            except Exception as e:
                logger.debug("PIPELINE_EPISODES_ERR %s", e)

    async def _global_memory():
        async with _BACKGROUND_SEM:
            try:
                from core.global_memory_service import global_memory_service
                await global_memory_service.consolidate_if_needed(user_id)
            except Exception as e:
                logger.debug("PIPELINE_GLOBAL_MEMORY_ERR %s", e)

    async def _predictive():
        async with _BACKGROUND_SEM:
            try:
                from core.predictive_engine import predictive_engine as _pe
                await _pe.update_prediction(user_id, user_message, response)
            except Exception as e:
                logger.debug("PIPELINE_PREDICTIVE_ERR %s", e)

    # Task senza LLM (veloci, nessun semaforo)
    async def _episode_resolution():
        try:
            from core.episode_memory import episode_memory as _em
            await _em.resolve_episodes(user_id, user_message)
        except Exception as e:
            logger.debug("PIPELINE_EPISODE_RESOLUTION_ERR %s", e)

    async def _behavioral():
        try:
            from core.behavioral_memory import behavioral_memory as _bm
            await _bm.update(user_id=user_id, user_msg=user_message, assistant_msg=response)
        except Exception as e:
            logger.debug("PIPELINE_BEHAVIORAL_ERR %s", e)

    async def _audit():
        try:
            from core.genesi_auditor import genesi_auditor as _auditor
            _counter_file = "monitor_trigger_count.txt"
            try:
                with open(_counter_file, "r") as cf:
                    count = int(cf.read().strip())
            except Exception:
                count = 0
            count += 1
            with open(_counter_file, "w") as cf:
                cf.write(str(count))
            if count % 100 == 0:
                log("AUDIT_AUTO_TRIGGER", platform=platform, turn=count, user_id=user_id)
                await _auditor.generate_report()
        except Exception as e:
            logger.debug("PIPELINE_AUDIT_ERR %s", e)

    async def _capability_gap():
        try:
            from core.capability_awareness import detect_gap, log_gap
            is_gap, gap_type = detect_gap(user_message, response, intent)
            if is_gap and gap_type:
                await log_gap(user_message, response, intent,
                              platform=platform, user_id=user_id, gap_type=gap_type)
        except Exception as e:
            logger.debug("PIPELINE_CAP_GAP_ERR %s", e)

    # Lancia tutti (group riduce frequenza per risparmiare crediti LLM)
    import random
    should_run_llm = not is_group or random.random() < 0.10

    if should_run_llm and len(user_message) > 10:
        asyncio.create_task(_personal_facts())
        asyncio.create_task(_episodes())
    asyncio.create_task(_global_memory())
    asyncio.create_task(_predictive())
    asyncio.create_task(_episode_resolution())
    asyncio.create_task(_behavioral())
    asyncio.create_task(_audit())
    asyncio.create_task(_capability_gap())

    log("PIPELINE_MEMORY_STARTED", platform=platform, user_id=user_id,
        tasks=8 if should_run_llm else 6)
