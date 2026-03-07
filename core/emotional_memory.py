"""
EMOTIONAL MEMORY — Genesi Cognitive System
Traccia lo storico emotivo persistente per utente (rolling window 20 record).
Permette a Genesi di riconoscere pattern emotivi across sessioni.
Fail-silent: nessun errore interrompe il flusso chat.
"""

import logging
from datetime import datetime
from typing import List, Dict, Optional
from collections import Counter

from core.storage import storage

logger = logging.getLogger("genesi")

_STORAGE_KEY = "emotional_log:{user_id}"
_MAX_RECORDS = 20


async def log_emotion(user_id: str, emotion_data: dict) -> None:
    """
    Salva lo stato emotivo corrente nel log persistente (rolling window).
    emotion_data: {emotion, intensity, vulnerability, urgency, message_preview, needs?}
    """
    if not user_id:
        return
    try:
        key = _STORAGE_KEY.format(user_id=user_id)
        log = await storage.load(key, default=[])
        if not isinstance(log, list):
            log = []

        record = {
            "emotion": emotion_data.get("emotion", "neutral"),
            "intensity": round(float(emotion_data.get("intensity", 0.3)), 2),
            "vulnerability": round(float(emotion_data.get("vulnerability", 0.3)), 2),
            "urgency": round(float(emotion_data.get("urgency", 0.1)), 2),
            "needs": emotion_data.get("needs", ""),
            "message_preview": (emotion_data.get("message_preview", ""))[:80],
            "ts": datetime.utcnow().isoformat(),
        }
        log.append(record)

        # Rolling window: mantieni solo gli ultimi _MAX_RECORDS
        if len(log) > _MAX_RECORDS:
            log = log[-_MAX_RECORDS:]

        await storage.save(key, log)
        logger.info("EMOTION_LOGGED user=%s emotion=%s intensity=%.2f",
                    user_id, record["emotion"], record["intensity"])
    except Exception as e:
        logger.debug("EMOTIONAL_MEMORY_LOG_ERROR user=%s err=%s", user_id, e)


async def get_recent_emotions(user_id: str, n: int = 5) -> List[Dict]:
    """Restituisce gli ultimi N stati emotivi con timestamp."""
    if not user_id:
        return []
    try:
        key = _STORAGE_KEY.format(user_id=user_id)
        log = await storage.load(key, default=[])
        if not isinstance(log, list):
            return []
        return log[-n:] if log else []
    except Exception:
        return []


async def get_emotion_trend_summary(user_id: str, n: int = 8) -> Optional[str]:
    """
    Analizza gli ultimi N stati emotivi e restituisce una sintesi in italiano.
    Es: "Nelle ultime sessioni hai mostrato spesso preoccupazione (4 volte) e stanchezza (2 volte)."
    Restituisce None se non ci sono abbastanza dati.
    """
    if not user_id:
        return None
    try:
        emotions = await get_recent_emotions(user_id, n=n)
        if len(emotions) < 2:
            return None

        # Conta emozioni escludendo "neutral"
        non_neutral = [e["emotion"] for e in emotions if e["emotion"] not in ("neutral", "neutro", "")]
        if not non_neutral:
            return None

        counts = Counter(non_neutral)
        total = len(emotions)

        # Traduzione emozioni → italiano
        _IT = {
            "sad": "tristezza", "sadness": "tristezza", "triste": "tristezza",
            "angry": "rabbia", "anger": "rabbia", "arrabbiato": "rabbia",
            "anxious": "ansia", "anxiety": "ansia", "ansioso": "ansia",
            "stressed": "stress", "stress": "stress", "stressato": "stress",
            "tired": "stanchezza", "stanco": "stanchezza", "exhausted": "stanchezza",
            "happy": "gioia", "joy": "gioia", "felice": "gioia",
            "worried": "preoccupazione", "preoccupato": "preoccupazione",
            "lonely": "solitudine", "solo": "solitudine",
            "frustrated": "frustrazione", "frustrato": "frustrazione",
            "hopeful": "speranza", "content": "serenità",
        }

        top = counts.most_common(3)
        parts = []
        for emotion, count in top:
            label = _IT.get(emotion.lower(), emotion)
            freq = "spesso" if count >= total * 0.5 else ("qualche volta" if count >= 2 else "una volta")
            parts.append(f"{label} ({freq})")

        if not parts:
            return None

        # Intensità media recente
        avg_intensity = sum(e.get("intensity", 0.3) for e in emotions[-4:]) / min(4, len(emotions))
        intensity_note = ""
        if avg_intensity > 0.7:
            intensity_note = " con intensità alta"
        elif avg_intensity > 0.5:
            intensity_note = " con intensità moderata"

        summary = f"Nelle ultime {total} interazioni hai mostrato: {', '.join(parts)}{intensity_note}."

        # Aggiungi nota su needs se ricorrente
        needs_list = [e.get("needs", "") for e in emotions[-5:] if e.get("needs")]
        if needs_list:
            needs_counts = Counter(needs_list)
            top_need = needs_counts.most_common(1)[0][0]
            if needs_counts[top_need] >= 2 and top_need not in ("informazione", ""):
                summary += f" Sembra cercare principalmente: {top_need}."

        return summary
    except Exception as e:
        logger.debug("EMOTIONAL_TREND_ERROR user=%s err=%s", user_id, e)
        return None
