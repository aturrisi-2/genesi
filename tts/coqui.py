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


def _add_micro_pauses(text: str) -> str:
    """Inserisce micro-pause variabili su virgole e cambi frase per ritmo naturale."""
    import random
    # Pause su virgole: 50-120 ms casuali (0.05-0.12s)
    text = re.sub(r",\s*", lambda m: f",{random.randint(50, 120)}ms ", text)
    # Pause su punto fine frase (non dopo ellipsis): 80-150 ms
    text = re.sub(r"\.(\s+|$)", lambda m: f".{random.randint(80, 150)}ms ", text)
    # Rimuovi spazi doppi dopo pause
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _should_breathe(text: str) -> bool:
    """Decide se inserire un respiro contestuale: SOLO risposte lunghe/densi/cambio argomento."""
    word_count = len(text.split())
    # Risposta lunga (>30 parole) o densa (>3 frasi)
    sentence_count = len(re.findall(r"[.!?]+", text))
    if word_count > 30 or sentence_count > 3:
        return True
    # Cambio argomento: indicatori espliciti
    topic_shift = re.search(r"\b(?:a parte questo|però|comunque|d'altronde|invece|altra cosa|cambiando argomento)\b", text, re.I)
    if topic_shift:
        return True
    return False


def _add_contextual_breath(text: str) -> str:
    """Aggiunge un respiro brevissimo e non udibile come 'effetto'."""
    import random
    # Respiro: 200-400 ms, inserito solo all'inizio se serve
    if _should_breathe(text):
        breath_ms = random.randint(200, 400)
        return f"{breath_ms}ms {text}"
    return text


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
    processed = _add_contextual_breath(processed)  # respiro SOLO se serve
    processed = _add_micro_pauses(processed)  # micro-pause variabili
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
