"""
STT API - Genesi Core v2
Speech-to-Text via OpenAI Whisper API.
Accetta audio multipart/form-data (webm, wav, mp4, ogg).
Restituisce JSON: {"text": "trascrizione"}
"""

from fastapi import APIRouter, UploadFile, File, Depends
import logging
import tempfile
import os
from openai import AsyncOpenAI
from core.log import log
from auth.router import require_auth
from auth.models import AuthUser

router = APIRouter(prefix="/stt")
logger = logging.getLogger(__name__)

# Client inizializzato pigramente per evitare crash all'avvio se manca la chiave
_client_instance = None

def get_stt_client():
    global _client_instance
    if _client_instance is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            logger.warning("STT_INIT_WARNING: OPENAI_API_KEY non trovata. Il servizio STT non funzionerà.")
            return None
        _client_instance = AsyncOpenAI(api_key=api_key)
    return _client_instance

_local_model_instance = None

def get_local_stt_model():
    global _local_model_instance
    if _local_model_instance is None:
        from faster_whisper import WhisperModel
        cache_dir = "/opt/models/whisper"
        if not os.path.exists(cache_dir):
            try:
                os.makedirs(cache_dir, exist_ok=True)
            except Exception:
                cache_dir = None
        model_name = os.environ.get("STT_MODEL", "small")  # 'small' = molto meglio del 'base' per l'italiano
        logger.info("STT_LOCAL_INIT: Loading Whisper '%s' model (device=cpu, compute_type=int8, cache=%s)...", model_name, cache_dir)
        _local_model_instance = WhisperModel(model_name, device="cpu", compute_type="int8", download_root=cache_dir)
        logger.info("STT_LOCAL_INIT: Whisper model '%s' loaded successfully.", model_name)
    return _local_model_instance

# Estensioni supportate da OpenAI Whisper API
_SUPPORTED_EXTENSIONS = {
    "audio/webm": ".webm",
    "audio/webm;codecs=opus": ".webm",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/wave": ".wav",
    "audio/ogg": ".ogg",
    "audio/ogg;codecs=opus": ".ogg",
    "audio/mp4": ".mp4",
    "audio/mpeg": ".mp3",
    "audio/mp3": ".mp3",
}


def _ext_for_content_type(content_type: str) -> str:
    """Map content-type to file extension for Whisper API."""
    if not content_type:
        return ".webm"
    ct = content_type.lower().strip()
    return _SUPPORTED_EXTENSIONS.get(ct, ".webm")


async def transcribe_audio(audio_data: bytes, content_type: str, filename: str = "audio") -> dict:
    """
    Transcribe audio bytes via local Whisper (if STT_LOCAL=true) or OpenAI Whisper API.
    Returns dict with 'text' and optional 'stt_status'.
    """
    if len(audio_data) < 100:
        logger.warning("STT_DATA_TOO_SMALL size=%d", len(audio_data))
        return {"text": "", "stt_status": "empty"}

    ext = _ext_for_content_type(content_type)
    tmp_path = None

    try:
        # Write to temp file (Whisper API needs a file-like with name)
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(audio_data)
            tmp_path = tmp.name

        # 1. Local STT Path
        if os.environ.get("STT_LOCAL", "false").lower() in ("true", "1", "yes"):
            try:
                # Runs CPU execution of faster-whisper model
                model = get_local_stt_model()
                logger.info("STT_LOCAL_START transcribing %s (size=%d)", filename, len(audio_data))
                
                # Execute blocking transcribe in thread pool to avoid blocking async event loop
                loop = asyncio.get_running_loop()
                def _run_transcribe():
                    segments, info = model.transcribe(tmp_path, beam_size=5, language="it")
                    return list(segments), info
                
                segments_list, info = await loop.run_in_executor(None, _run_transcribe)
                text = "".join(seg.text for seg in segments_list).strip()
                
                logger.info("STT_LOCAL_SUCCESS text_len=%d text=%s lang=%s", len(text), repr(text[:80]), info.language)
                log("STT_TRANSCRIPTION_RESULT", text_len=len(text), source="local")
                
                if not text or len(text) < 2:
                    return {"text": "", "stt_status": "empty"}
                return {"text": text}
            except Exception as le:
                logger.error("STT_LOCAL_ERROR: local transcription failed, trying remote OpenAI fallback: %s", le, exc_info=True)

        # 2. Remote OpenAI Whisper API Fallback
        client = get_stt_client()
        if not client:
            return {"text": "", "stt_status": "error", "error": "OPENAI_API_KEY non configurata"}
            
        with open(tmp_path, "rb") as audio_file:
            transcript = await client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="it",
                response_format="text",
            )

        text = transcript.strip() if isinstance(transcript, str) else str(transcript).strip()
        logger.info("STT_TRANSCRIPTION_RESULT text_len=%d text=%s", len(text), repr(text[:80]))
        log("STT_TRANSCRIPTION_RESULT", text_len=len(text), source="openai")

        if not text or len(text) < 2:
            return {"text": "", "stt_status": "empty"}

        return {"text": text}

    except Exception as e:
        logger.error("STT_WHISPER_ERROR error=%s", str(e), exc_info=True)
        log("STT_ERROR", error=str(e))
        return {"text": "", "stt_status": "error", "error": str(e)}

    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


@router.post("/")
async def speech_to_text(audio: UploadFile = File(...), user: AuthUser = Depends(require_auth)):
    """
    POST /api/stt/
    Accepts multipart/form-data with field 'audio'.
    Supports: audio/webm, audio/wav, audio/ogg, audio/mp4.
    Returns: {"text": "trascrizione"} or {"text": "", "stt_status": "error|empty|noise"}
    """
    content_type = audio.content_type or "audio/webm"
    audio_data = await audio.read()

    logger.info("STT_REQUEST_RECEIVED size=%d content_type=%s filename=%s",
                len(audio_data), content_type, audio.filename)
    log("STT_REQUEST_RECEIVED", size=len(audio_data), content_type=content_type)

    result = await transcribe_audio(audio_data, content_type, audio.filename or "audio")
    return result
