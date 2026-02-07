import asyncio
import uuid
import io
import re
from pathlib import Path

import edge_tts


# ===============================
# VOICE CONFIG
# ===============================
VOICE = "it-IT-IsabellaNeural"

OUTPUT_DIR = Path("data/tts_cache")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ===============================
# EMOTIONAL DETECTION
# ===============================
_EMO_HEAVY = frozenset({
    "dolore", "paura", "ansia", "triste", "piango", "solo", "sola",
    "perso", "persa", "male", "morto", "morta", "morte", "soffro",
    "soffrire", "abbandono", "vuoto", "buio", "stanco", "stanca",
    "pesante", "difficile", "fatica", "non ce la faccio", "non riesco",
    "aiuto", "disperato", "disperata", "panico", "terrore", "angoscia",
    "lacrime", "piangere", "ferita", "ferito", "depresso", "depressa",
})

_EMO_LIGHT = frozenset({
    "bene", "felice", "contento", "contenta", "bello", "bella",
    "ridere", "gioia", "grazie", "fantastico", "fantastica", "forte",
    "energia", "sorriso", "amore", "sereno", "serena", "divertente",
    "ridendo", "allegro", "allegra",
})


def _detect_emotional_weight(text: str) -> float:
    low = text.lower()
    heavy = sum(1 for w in _EMO_HEAVY if w in low)
    light = sum(1 for w in _EMO_LIGHT if w in low)
    if heavy >= 2:
        return 0.9
    if heavy >= 1:
        return 0.7
    if light >= 2:
        return 0.2
    if light >= 1:
        return 0.35
    return 0.5


# ===============================
# TEXT PREPROCESSING
# ===============================
def _soften_closings(text: str) -> str:
    # "eh" / "eh." / ", eh." as final token → trailing ellipsis
    text = re.sub(r",?\s*eh\.?\s*$", "… eh…", text)
    # "dai." / "sai." / "ecco." as bare closing → ellipsis
    text = re.sub(r",?\s*(dai|sai|ecco)\.?\s*$", r"… \1…", text)
    # Trailing bare period after short emotional word → ellipsis
    text = re.sub(r"(?:^|\s)(già|bene|vero|insomma)\.\s*$", r" \1…", text)
    text = text.strip()
    return text


def _preprocess(text: str) -> str:
    text = re.sub(r"\s+", " ", text.strip())
    # Soften emotional closings
    text = _soften_closings(text)
    # Soften exclamation marks
    text = text.replace("!", ".")
    # Riduci ellipsis multiple a singolo punto (meno pause)
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r"…", ",", text)
    return text.strip()


def _split_sentences(text: str) -> list:
    parts = re.split(r"(?<=\.\.\.)\s+|(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip() and len(p.strip()) > 2]




# ===============================
# PROSODY — MICRO-VARIED PER SEGMENT
# ===============================
_VARIATION_CYCLE = [0, -0.5, +0.5, -0.3, +0.4, -0.2]


def _format_val(val: float, suffix: str, lo: int, hi: int) -> str:
    """Formatta valore per edge-tts: richiede segno esplicito (+5% o -5%)."""
    v = max(lo, min(hi, int(round(val))))
    if v == 0:
        v = -1
    sign = "+" if v > 0 else ""
    return f"{sign}{v}{suffix}"


def _get_prosody(emo: float, idx: int) -> tuple:
    # Veloce e fluida. Aumento base rate +5% (da 12 a 17). Emotional → solo leggermente più lenta.
    base_rate = 17 - (emo * 14)    # light≈+14, neutral≈+10, heavy≈+4
    base_pitch = 0 - (emo * 1.5)   # light≈0, neutral≈-0.75, heavy≈-1.5
    v = _VARIATION_CYCLE[idx % len(_VARIATION_CYCLE)]
    rate = base_rate + v
    pitch = base_pitch + (v * 0.2)
    return _format_val(rate, "%", -5, 20), _format_val(pitch, "Hz", -3, 1)


# ===============================
# SEGMENT SYNTHESIS
# ===============================
async def _synth_segment(text: str, rate: str, pitch: str) -> bytes:
    c = edge_tts.Communicate(text=text, voice=VOICE, rate=rate, pitch=pitch)
    buf = io.BytesIO()
    async for chunk in c.stream():
        if chunk["type"] == "audio":
            buf.write(chunk["data"])
    return buf.getvalue()


# ===============================
# MAIN PIPELINE
# ===============================
async def _synthesize_async(text: str) -> bytes:
    emo = _detect_emotional_weight(text)
    processed = _preprocess(text)
    sentences = _split_sentences(processed)

    if not sentences:
        sentences = [processed]

    all_audio = io.BytesIO()
    for i, sent in enumerate(sentences):
        rate, pitch = _get_prosody(emo, i)
        audio = await _synth_segment(sent, rate, pitch)
        all_audio.write(audio)

    return all_audio.getvalue()


def synthesize_bytes(text: str) -> bytes:
    if not text or not isinstance(text, str) or not text.strip():
        raise ValueError("Testo vuoto")
    return asyncio.run(_synthesize_async(text.strip()))


async def synthesize_bytes_async(text: str) -> bytes:
    if not text or not isinstance(text, str) or not text.strip():
        raise ValueError("Testo vuoto")
    return await _synthesize_async(text.strip())


def synthesize(text: str) -> str:
    audio_bytes = synthesize_bytes(text)
    out_file = OUTPUT_DIR / f"tts_{uuid.uuid4().hex}.mp3"
    out_file.write_bytes(audio_bytes)
    return str(out_file.resolve())


if __name__ == "__main__":
    path = synthesize("Ciao, sono Genesi. Sono qui con te.")
    print(f"Audio: {path}")
