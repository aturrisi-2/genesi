"""
VIDEO VISION SERVICE — Genesi Core
Analisi video platform-independent: ffmpeg estrae frame chiave, GPT-4o vision
li descrive in un'unica chiamata narrativa. Il frame centrale viene esposto
per il riconoscimento biometrico (volti umani + animali) con la stessa
pipeline delle foto.

Usato da message_pipeline.process_incoming_video per Telegram, WhatsApp,
Messenger, Instagram (Reel) e qualsiasi piattaforma futura.
"""

import asyncio
import base64
import logging
import os
import subprocess
import tempfile

from core.log import log

logger = logging.getLogger(__name__)

MAX_FRAMES = 4
FRAME_MAX_SIDE = 1024  # ridimensiona i frame per contenere i token vision


def _ffprobe_duration(path: str) -> float:
    """Durata del video in secondi (0 se non determinabile)."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, timeout=20,
        )
        return float(out.stdout.strip())
    except Exception:
        return 0.0


def _extract_frames(path: str, out_dir: str, n_frames: int = MAX_FRAMES) -> list[str]:
    """
    Estrae n_frames equidistanti dal video come JPEG.
    Ritorna i path dei frame in ordine temporale.
    """
    duration = _ffprobe_duration(path)
    frames: list[str] = []

    if duration > 0.5:
        # Timestamp equidistanti, evitando il primissimo e ultimissimo istante
        timestamps = [duration * (i + 1) / (n_frames + 1) for i in range(n_frames)]
    else:
        timestamps = [0.0]

    for i, ts in enumerate(timestamps):
        out_path = os.path.join(out_dir, f"frame_{i:02d}.jpg")
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", f"{ts:.2f}", "-i", path,
                 "-frames:v", "1",
                 "-vf", f"scale='min({FRAME_MAX_SIDE},iw)':-2",
                 "-q:v", "3", out_path],
                capture_output=True, timeout=30,
            )
            if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                frames.append(out_path)
        except Exception as e:
            logger.debug("VIDEO_FRAME_EXTRACT_ERR ts=%.1f err=%s", ts, e)

    return frames


async def describe_video(path: str) -> dict:
    """
    Analizza un video: estrae i frame e li descrive con GPT-4o vision
    in un'unica chiamata narrativa (cosa succede, chi/cosa è presente).

    Returns:
        {
          "description": str,     # descrizione narrativa del video
          "best_frame": str|None, # path del frame centrale (per biometria)
          "frames_count": int,
        }
    """
    log("VIDEO_VISION_START", path=path)
    tmp_dir = tempfile.mkdtemp(prefix="genesi_video_")

    try:
        frames = await asyncio.to_thread(_extract_frames, path, tmp_dir)
        if not frames:
            log("VIDEO_VISION_NO_FRAMES", path=path)
            return {"description": "", "best_frame": None, "frames_count": 0}

        best_frame = frames[len(frames) // 2]

        # Costruisci il contenuto multi-immagine per GPT-4o
        content = [{
            "type": "text",
            "text": (
                f"Questi sono {len(frames)} fotogrammi estratti in sequenza da un VIDEO. "
                "Descrivi in italiano cosa succede nel video in modo narrativo e naturale: "
                "soggetti presenti (persone, animali, oggetti), azioni, ambientazione, atmosfera. "
                "Se sembra un Reel/clip social descrivine il contenuto e il tono. "
                "NON descrivere i fotogrammi uno per uno: racconta il video come un tutto. "
                "Massimo 5 frasi."
            ),
        }]
        for fp in frames:
            with open(fp, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()
            content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"},
            })

        from core.image_vision_service import _get_vision_clients
        clients = _get_vision_clients()
        description = ""
        for client, provider in clients:
            try:
                model_name = "openai/gpt-4o" if provider == "openrouter" else "gpt-4o"
                res = await client.chat.completions.create(
                    model=model_name,
                    messages=[{"role": "user", "content": content}],
                    max_tokens=500,
                )
                description = (res.choices[0].message.content or "").strip()
                # Rifiuto del modello → prova provider successivo
                _refusals = ("i'm sorry", "i can't assist", "non posso aiutarti")
                if description and not (len(description) < 150 and
                                        any(m in description.lower() for m in _refusals)):
                    break
                description = ""
            except Exception as e:
                logger.warning("VIDEO_VISION_PROVIDER_FAILED provider=%s err=%s", provider, e)

        log("VIDEO_VISION_OK", frames=len(frames), chars=len(description))
        return {
            "description": description,
            "best_frame": best_frame,
            "frames_count": len(frames),
        }

    except Exception as e:
        logger.error("VIDEO_VISION_ERROR err=%s", e)
        return {"description": "", "best_frame": None, "frames_count": 0}
    # NB: tmp_dir viene pulito dal chiamante (process_incoming_video) DOPO
    # aver usato best_frame per la biometria.


def cleanup_video_tmp(result: dict):
    """Rimuove la directory temporanea dei frame (dopo l'uso di best_frame)."""
    bf = result.get("best_frame")
    if not bf:
        return
    import shutil
    try:
        shutil.rmtree(os.path.dirname(bf), ignore_errors=True)
    except Exception:
        pass
