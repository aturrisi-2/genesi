import os
import uuid
import subprocess
from pathlib import Path

# =========================
# CONFIGURAZIONE GOLD
# =========================

BASE_DIR = Path("/opt/genesi")
TTS_DIR = BASE_DIR / "data" / "tts"
MODEL_PATH = BASE_DIR / "models" / "leonardo-epoch=2024-step=996300.onnx"

PIPER_BIN = BASE_DIR / "venv" / "bin" / "piper"
FFMPEG_BIN = "/usr/bin/ffmpeg"

# Parametri voce (GOLD)
PIPER_ARGS = [
    "--noise-scale", "0.45",
    "--noise-w-scale", "0.9",
    "--length-scale", "1.0",
]

# Post-processing
PAD_SECONDS = "0.6"
TRIM_START = "0.12"

os.makedirs(TTS_DIR, exist_ok=True)


def synthesize(text: str) -> str:
    if not text or not text.strip():
        raise ValueError("Testo vuoto")

    uid = uuid.uuid4().hex

    raw_wav = TTS_DIR / f"raw_{uid}.wav"
    pad_wav = TTS_DIR / f"pad_{uid}.wav"
    final_wav = TTS_DIR / f"final_{uid}.wav"

    # =========================
    # 1. PIPER → raw.wav
    # =========================
    piper_cmd = [
        str(PIPER_BIN),
        "--model", str(MODEL_PATH),
        "--output_file", str(raw_wav),
        *PIPER_ARGS,
    ]

    piper = subprocess.Popen(
        piper_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    stdout, stderr = piper.communicate(text.encode("utf-8"))

    if piper.returncode != 0 or not raw_wav.exists():
        raise RuntimeError(f"Piper error: {stderr.decode()}")

    # =========================
    # 2. Padding finale
    # =========================
   # subprocess.run(
#     [
#         FFMPEG_BIN,
#         "-y",
#         "-i", str(pad_wav),
#         "-af", f"atrim=start={TRIM_START}",
#         str(final_wav),
#     ],
#     check=True,
# )


    # =========================
    # 3. Trim iniziale controllato
    # =========================
    # subprocess.run(
#     [
#         FFMPEG_BIN,
#         "-y",
#         "-i", str(pad_wav),
#         "-af", f"atrim=start={TRIM_START}",
#         str(final_wav),
#     ],
#     check=True,
# )

    # Cleanup (opzionale ma consigliato)
    raw_wav.unlink(missing_ok=True)
    pad_wav.unlink(missing_ok=True)

    return str(final_wav)
