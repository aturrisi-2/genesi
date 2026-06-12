"""
AUDIO ANALYSIS SERVICE — Genesi Core
Analisi audio universale platform-independent. Completa la triade sensoriale:
- image_vision_service  → immagini
- video_vision_service  → video
- audio_analysis_service → audio (questo file)

Capisce QUALSIASI audio:
- PARLATO: trascrizione + traduzione in italiano se in altra lingua
- MUSICA: genere, mood, strumenti, eventuale brano riconoscibile
- SUONI: rumori di vita quotidiana, ambienti, versi di animali

Primario: gpt-4o-audio-preview (comprensione nativa dell'audio).
Fallback: whisper-1 (solo trascrizione parlato).
Usato da message_pipeline.process_incoming_audio per tutte le piattaforme.
"""

import asyncio
import base64
import json
import logging
import os
import subprocess
import tempfile

from core.log import log

logger = logging.getLogger(__name__)

MAX_AUDIO_SECONDS = 300  # 5 minuti max (limite pratico per il modello audio)

_AUDIO_PROMPT = """Ascolta questo audio e analizzalo. Rispondi SOLO con JSON valido:

{"kind": "speech|music|sound|mixed",
 "language": "codice lingua se parlato (it, en, ...) altrimenti null",
 "transcription": "trascrizione fedele se c'è parlato, altrimenti null",
 "translation_it": "traduzione italiana SE il parlato non è in italiano, altrimenti null",
 "description": "descrizione in italiano di cosa si sente"}

REGOLE per "description":
- PARLATO: tono, emozione, contesto (es. "voce maschile calma che racconta...")
- MUSICA: genere, mood, strumenti, se riconosci il brano/artista dillo
- SUONI: descrivi i rumori (es. "traffico cittadino con clacson", "pioggia battente",
  "un cane che abbaia", "stoviglie in una cucina")
- MIXED: descrivi tutti gli elementi presenti
Massimo 3 frasi.

REGOLE ANTI-ALLUCINAZIONE (fondamentali):
- Trascrivi SOLO parole che senti chiaramente. Se non c'è parlato chiaro,
  "transcription" DEVE essere null. MAI inventare frasi.
- Toni sintetici, beep, sinusoidi, silenzio, rumore bianco → kind="sound",
  transcription=null, descrivi il suono per quello che è.
- Le stringhe JSON devono stare su UNA riga (niente a capo dentro le stringhe).
Nessun testo fuori dal JSON."""


def _convert_to_wav16k(src_path: str) -> str | None:
    """
    Converte qualsiasi formato audio in WAV 16kHz mono (formato accettato
    dal modello audio). Tronca a MAX_AUDIO_SECONDS. Ritorna il path o None.
    """
    out_path = src_path + ".conv.wav"
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", src_path, "-t", str(MAX_AUDIO_SECONDS),
             "-ac", "1", "-ar", "16000", "-f", "wav", out_path],
            capture_output=True, timeout=120,
        )
        if os.path.exists(out_path) and os.path.getsize(out_path) > 44:
            return out_path
        return None
    except Exception as e:
        logger.error("AUDIO_CONVERT_ERROR err=%s", e)
        return None


def _audio_clients() -> list[tuple]:
    """
    Client+modello per l'analisi audio in ordine di priorità.
    Modelli con input audio verificati sul catalogo OpenRouter:
    - google/gemini-3.5-flash (veloce, ottimo su suoni/musica/parlato)
    - openai/gpt-audio (fallback, sempre via OpenRouter)
    OpenAI diretto per ultimo (richiede quota sulla chiave dedicata).
    """
    from openai import AsyncOpenAI
    clients = []
    or_key = os.environ.get("OPENROUTER_API_KEY")
    oa_key = os.environ.get("OPENAI_API_KEY")
    if or_key:
        or_client = AsyncOpenAI(
            api_key=or_key, base_url="https://openrouter.ai/api/v1",
            default_headers={"HTTP-Referer": "https://genesi.app",
                             "X-Title": "Genesi"})
        clients.append((or_client, "openrouter", "google/gemini-3.5-flash"))
        clients.append((or_client, "openrouter", "openai/gpt-audio"))
    if oa_key:
        clients.append((AsyncOpenAI(api_key=oa_key), "openai", "gpt-4o-audio-preview"))
    return clients


async def _analyze_with_audio_model(wav_path: str) -> dict | None:
    """Analisi completa con gpt-4o-audio-preview (OpenRouter → OpenAI)."""
    clients = _audio_clients()
    if not clients:
        return None

    with open(wav_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()

    for client, provider, model in clients:
        try:
            res = await client.chat.completions.create(
                model=model,
                modalities=["text"],
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": _AUDIO_PROMPT},
                        {"type": "input_audio",
                         "input_audio": {"data": b64, "format": "wav"}},
                    ],
                }],
                max_tokens=1500,
            )
            raw = (res.choices[0].message.content or "").strip()
            data = _parse_json_lenient(raw)
            if isinstance(data, dict) and data.get("description"):
                log("AUDIO_MODEL_OK", provider=provider, model=model)
                return data
        except Exception as e:
            logger.warning("AUDIO_MODEL_FAILED provider=%s model=%s err=%s",
                           provider, model, str(e)[:200])
    return None


def _parse_json_lenient(raw: str) -> dict | None:
    """
    Parser tollerante per l'output del modello audio: gestisce backtick,
    testo extra attorno al JSON e JSON troncati (estrae i campi via regex).
    """
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        s = s.strip("`").lstrip("json").strip()
    # Tentativo standard
    try:
        return json.loads(s)
    except Exception:
        pass
    # Estrai il blocco {...} più esterno
    start, end = s.find("{"), s.rfind("}")
    if start != -1 and end > start:
        try:
            return json.loads(s[start:end + 1])
        except Exception:
            pass
    # Ultima risorsa: estrai i campi noti via regex (JSON troncato)
    import re as _re
    out = {}
    for key in ("kind", "language", "transcription", "translation_it", "description"):
        m = _re.search(rf'"{key}"\s*:\s*"((?:[^"\\]|\\.)*)' , s)
        if m:
            out[key] = m.group(1).replace('\\"', '"').replace("\\n", " ").strip()
        elif _re.search(rf'"{key}"\s*:\s*null', s):
            out[key] = None
    return out if out.get("description") else None


async def _fallback_whisper(audio_bytes: bytes, content_type: str) -> dict | None:
    """Fallback: solo trascrizione via whisper-1 (riusa l'infrastruttura STT)."""
    try:
        from api.stt import transcribe_audio
        result = await transcribe_audio(audio_bytes, content_type)
        text = (result.get("text") or "").strip()
        if not text:
            return None
        return {
            "kind": "speech",
            "language": None,
            "transcription": text,
            "translation_it": None,
            "description": "Messaggio vocale trascritto.",
        }
    except Exception as e:
        logger.warning("AUDIO_WHISPER_FALLBACK_FAILED err=%s", e)
        return None


async def analyze_audio(audio_bytes: bytes, content_type: str = "audio/ogg") -> dict:
    """
    Analizza qualsiasi audio. Ritorna SEMPRE un dict:
        {
          "kind": "speech|music|sound|mixed|unknown",
          "language": str|None,
          "transcription": str|None,
          "translation_it": str|None,
          "description": str,        # "" se l'analisi è fallita del tutto
        }
    Fail-safe: nessuna eccezione propagata.
    """
    log("AUDIO_ANALYSIS_START", bytes=len(audio_bytes or b""), mime=content_type)
    _empty = {"kind": "unknown", "language": None, "transcription": None,
              "translation_it": None, "description": ""}

    if not audio_bytes:
        return _empty

    tmp_path, wav_path = None, None
    try:
        ext = {"audio/ogg": ".ogg", "audio/mpeg": ".mp3", "audio/mp4": ".m4a",
               "audio/wav": ".wav", "audio/x-wav": ".wav", "audio/aac": ".aac",
               "audio/amr": ".amr", "audio/webm": ".webm"}.get(
                   (content_type or "").split(";")[0].strip().lower(), ".ogg")
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False, prefix="genesi_audio_") as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name

        wav_path = await asyncio.to_thread(_convert_to_wav16k, tmp_path)
        if not wav_path:
            # Conversione fallita → prova whisper sui bytes originali
            result = await _fallback_whisper(audio_bytes, content_type)
            if result:
                log("AUDIO_ANALYSIS_OK", kind=result["kind"], via="whisper_no_convert")
                return result
            return _empty

        # 1° tentativo: modello audio nativo (capisce suoni/musica/parlato)
        result = await _analyze_with_audio_model(wav_path)
        if result:
            result.setdefault("kind", "unknown")
            result.setdefault("language", None)
            result.setdefault("transcription", None)
            result.setdefault("translation_it", None)
            log("AUDIO_ANALYSIS_OK", kind=result["kind"], via="audio_model",
                has_transcription=bool(result.get("transcription")))
            return result

        # 2° tentativo: whisper (solo parlato)
        result = await _fallback_whisper(audio_bytes, content_type)
        if result:
            log("AUDIO_ANALYSIS_OK", kind=result["kind"], via="whisper_fallback")
            return result

        log("AUDIO_ANALYSIS_EMPTY")
        return _empty

    except Exception as e:
        logger.error("AUDIO_ANALYSIS_ERROR err=%s", e)
        return _empty
    finally:
        for p in (tmp_path, wav_path):
            if p:
                try:
                    os.unlink(p)
                except Exception:
                    pass


def build_audio_context(result: dict) -> str:
    """
    Costruisce il blocco [Contenuto audio: ...] per il LLM conversazionale,
    combinando trascrizione, traduzione e descrizione.
    Ritorna "" se non c'è nulla di utile.
    """
    if not result:
        return ""
    parts = []
    desc = (result.get("description") or "").strip()
    trans = (result.get("transcription") or "").strip()
    trad = (result.get("translation_it") or "").strip()
    lang = result.get("language")

    if trans:
        if lang and str(lang).lower() not in ("it", "ita", "italian", "italiano"):
            parts.append(f'Parlato ({lang}): "{trans}"')
            if trad:
                parts.append(f'Traduzione italiana: "{trad}"')
        else:
            parts.append(f'Parlato: "{trans}"')
    if desc and desc != "Messaggio vocale trascritto.":
        parts.append(desc)

    return " | ".join(parts)
