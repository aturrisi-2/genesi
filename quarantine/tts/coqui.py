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
    # Veloce e fluida. Aumento base rate +8% (da 17 a 18). Compensato da micro-pause intelligenti.
    base_rate = 18 - (emo * 14)    # light≈+15, neutral≈+11, heavy≈+5
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
# AUDIO CONTROLS (separati dal testo)
# ===============================
class AudioControls:
    def __init__(self):
        self.pauses_after = []  # [(index, duration_ms), ...]
        self.should_breathe = False
        self.breath_position = 0  # index where to insert breath

def _analyze_audio_controls(text: str, sentences: list) -> AudioControls:
    """Analizza il testo per determinare controlli audio SENZA modificare il testo."""
    controls = AudioControls()
    word_count = len(text.split())
    sentence_count = len(sentences)
    
    # Respirazione contestuale SOLO per risposte lunghe/densi/cambio argomento
    if word_count > 30 or sentence_count > 3:
        # Cambio argomento: indicatori espliciti
        topic_shift = re.search(r"\b(?:a parte questo|però|comunque|d'altronde|invece|altra cosa|cambiando argomento)\b", text, re.I)
        if topic_shift:
            controls.should_breathe = True
            controls.breath_position = 0  # All'inizio
        elif word_count > 40:  # Risposta molto lunga
            controls.should_breathe = True
            controls.breath_position = 0
    
    # Micro-pause dopo virgole e frasi brevi
    import random
    for i, sent in enumerate(sentences):
        # Pause dopo virgole: 40-80 ms
        if ',' in sent and len(sent.split()) < 8:  # Frasi brevi
            pause_ms = random.randint(40, 80)
            controls.pauses_after.append((i, pause_ms))
        # Pause dopo frasi dense: 80-140 ms
        elif len(sent.split()) > 10 and i < len(sentences) - 1:  # Non ultima frase
            pause_ms = random.randint(80, 140)
            controls.pauses_after.append((i, pause_ms))
    
    return controls

def _create_silence(duration_ms: int) -> bytes:
    """Crea un buffer di silenzio della durata specificata."""
    # Edge TTS usa 16kHz, 16-bit, mono
    sample_rate = 16000
    bytes_per_sample = 2
    num_samples = int(sample_rate * duration_ms / 1000)
    silence = b'\x00' * (num_samples * bytes_per_sample)
    return silence

def _create_breath_audio() -> bytes:
    """Crea un respiro brevissimo e non udibile come effetto."""
    # Per ora usiamo silenzio con durata molto breve (200-400ms)
    import random
    duration_ms = random.randint(200, 400)
    return _create_silence(duration_ms)

# ===============================
# MAIN PIPELINE
# ===============================
async def _synthesize_async(text: str) -> bytes:
    # STEP 1: Analisi testo TTS (immutabile)
    emo = _detect_emotional_weight(text)
    processed = _preprocess(text)
    sentences = _split_sentences(processed)
    
    if not sentences:
        sentences = [processed]
    
    # STEP 2: Analisi controlli audio (separati dal testo)
    controls = _analyze_audio_controls(text, sentences)
    
    # STEP 3: Sintesi con controlli audio
    all_audio = io.BytesIO()
    
    # Respirazione iniziale se necessaria
    if controls.should_breathe and controls.breath_position == 0:
        breath_audio = _create_breath_audio()
        all_audio.write(breath_audio)
    
    # Sintesi frasi con pause
    for i, sent in enumerate(sentences):
        rate, pitch = _get_prosody(emo, i)
        audio = await _synth_segment(sent, rate, pitch)
        all_audio.write(audio)
        
        # Micro-pause dopo questa frase?
        for pause_idx, pause_ms in controls.pauses_after:
            if pause_idx == i:
                silence = _create_silence(pause_ms)
                all_audio.write(silence)
                break
    
    return all_audio.getvalue()


def synthesize_bytes(text: str) -> bytes:
    if not text or not isinstance(text, str) or not text.strip():
        raise ValueError("Testo vuoto")
    
    # SICUREZZA: assert nessun parametro temporale nel testo
    if "ms" in text.lower():
        import re
        if re.search(r'\d+ms', text):
            print(f"[TTS] WARNING: rilevati parametri temporali nel testo: {text}", flush=True)
            # Rimuovi ms per sicurezza
            text = re.sub(r'\d+\s?ms', '', text)
    
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
