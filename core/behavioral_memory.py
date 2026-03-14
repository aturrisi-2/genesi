"""
BEHAVIORAL MEMORY — Genesi Procedural Memory System

Implementa la Memoria Procedurale umana: impara HOW interagire con
questo specifico utente (non solo CHI è o COSA è successo).

Traccia:
- Stile di interazione preferito (lunghezza risposte, frequenza domande)
- Topic-Emotion binding (lavoro→stress, famiglia→preoccupazione)
- Engagement signals (quali argomenti generano follow-up vs chiusura)
- Ritmo temporale (quando l'utente è più attivo)

Zero-cost: nessun LLM, solo contatori e regex.
Fail-silent: mai blocca il flusso principale.
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Dict, Any, Optional

from core.log import log

logger = logging.getLogger("genesi")

_STORAGE_DIR = "memory/behavioral"
_MIN_SESSIONS_FOR_INJECTION = 3   # non iniettare fino a dati sufficienti
_MAX_TOPICS = 30                   # topic words tracciati per utente

# Stopwords italiane per topic extraction
_STOPWORDS = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una",
    "di", "da", "in", "con", "su", "per", "tra", "fra",
    "è", "e", "a", "o", "ma", "se", "non", "si", "mi", "ti",
    "ci", "vi", "ne", "già", "più", "che", "ho", "ha", "hai",
    "sono", "sei", "come", "cosa", "chi", "dove", "quando",
    "perché", "quindi", "però", "anche", "tutto", "tutti",
    "molto", "poco", "tanto", "proprio", "sempre", "mai",
    "oggi", "ieri", "ora", "poi", "dopo", "prima", "ancora",
    "questa", "questo", "questi", "queste", "quel", "quella",
    "ciao", "grazie", "prego", "bene", "male", "okay", "sì",
    "no", "forse", "davvero", "solito", "stato", "fatto",
    "dire", "fare", "avere", "essere", "stare", "andare",
    "volere", "potere", "dovere", "sapere", "vedere",
}


def _extract_topics(text: str, max_topics: int = 5):
    """Estrae parole chiave significative da un testo (zero-cost)."""
    words = re.findall(r'\b[a-zàáèéìíòóùú]{4,}\b', text.lower())
    topics = [w for w in words if w not in _STOPWORDS]
    # Conta frequenza e prendi le più frequenti
    from collections import Counter
    counts = Counter(topics)
    return [w for w, _ in counts.most_common(max_topics)]


class BehavioralMemory:
    """
    Memoria Procedurale di Genesi.
    Impara lo stile di interazione unico di ogni utente nel tempo.
    """

    def _path(self, user_id: str) -> str:
        os.makedirs(_STORAGE_DIR, exist_ok=True)
        return os.path.join(_STORAGE_DIR, f"{user_id}.json")

    def _load(self, user_id: str) -> Dict[str, Any]:
        try:
            path = self._path(user_id)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception:
            pass
        return self._default()

    def _save(self, user_id: str, data: Dict[str, Any]) -> None:
        try:
            with open(self._path(user_id), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.debug("BEHAVIORAL_MEMORY_SAVE_ERROR user=%s err=%s", user_id, e)

    def _default(self) -> Dict[str, Any]:
        return {
            "interaction_style": {
                "total_turns": 0,
                "total_user_chars": 0,
                "total_assistant_chars": 0,
                "questions_in_assistant": 0,   # quante domande ha fatto Genesi
                "user_followup_count": 0,       # quante volte user ha risposto a domande
                "avg_user_msg_length": 0.0,
            },
            "topic_emotion_map": {},    # {topic: {emotion: count}}
            "engagement_signals": {},   # {topic: {"followup": N, "drop": N}}
            "peak_hours": [0] * 24,
            "sessions_count": 0,
            "last_updated": None,
        }

    async def update(
        self,
        user_id: str,
        user_msg: str,
        assistant_msg: str,
        emotion: str = "neutral",
        prev_topics: list = None,
    ) -> None:
        """
        Aggiorna la memoria comportamentale dopo ogni turno.
        Chiamato in background — fail-silent.
        """
        try:
            data = self._load(user_id)
            style = data["interaction_style"]
            now_hour = datetime.now().hour

            # --- Interaction style ---
            style["total_turns"] += 1
            style["total_user_chars"] += len(user_msg)
            style["total_assistant_chars"] += len(assistant_msg)

            # Avg user message length (rolling)
            n = style["total_turns"]
            prev_avg = style.get("avg_user_msg_length", 0.0)
            style["avg_user_msg_length"] = (prev_avg * (n - 1) + len(user_msg)) / n

            # Conta domande nella risposta di Genesi
            q_count = assistant_msg.count("?")
            style["questions_in_assistant"] += q_count

            # Rileva se l'utente sta rispondendo a una domanda precedente
            # (euristica: messaggio corto dopo domanda di Genesi)
            if prev_topics and len(user_msg) > 5:
                style["user_followup_count"] += 1

            # --- Peak hours ---
            data["peak_hours"][now_hour] = data["peak_hours"][now_hour] + 1

            # --- Topic extraction dall'utente ---
            user_topics = _extract_topics(user_msg, max_topics=5)

            # --- Topic-Emotion binding ---
            topic_emotion = data["topic_emotion_map"]
            for topic in user_topics:
                if topic not in topic_emotion:
                    topic_emotion[topic] = {}
                em = emotion if emotion else "neutral"
                topic_emotion[topic][em] = topic_emotion[topic].get(em, 0) + 1

            # Tieni solo i top _MAX_TOPICS per frequenza totale
            if len(topic_emotion) > _MAX_TOPICS:
                totals = {t: sum(v.values()) for t, v in topic_emotion.items()}
                keep = sorted(totals, key=totals.get, reverse=True)[:_MAX_TOPICS]
                data["topic_emotion_map"] = {t: topic_emotion[t] for t in keep}

            # --- Engagement signals ---
            # Se i topic dell'utente si sovrappongono con il turno precedente → followup
            engagement = data["engagement_signals"]
            if prev_topics:
                overlap = set(user_topics) & set(prev_topics)
                for topic in overlap:
                    if topic not in engagement:
                        engagement[topic] = {"followup": 0, "drop": 0}
                    engagement[topic]["followup"] += 1
                # Topic del turno precedente NON ripresi → drop
                dropped = set(prev_topics) - set(user_topics)
                for topic in dropped:
                    if topic not in engagement:
                        engagement[topic] = {"followup": 0, "drop": 0}
                    engagement[topic]["drop"] += 1

            data["sessions_count"] = data.get("sessions_count", 0) + 1
            data["last_updated"] = datetime.utcnow().isoformat()

            self._save(user_id, data)
            log("BEHAVIORAL_MEMORY_UPDATE", user_id=user_id, turn=style["total_turns"])
        except Exception as e:
            logger.debug("BEHAVIORAL_MEMORY_UPDATE_ERROR user=%s err=%s", user_id, e)

    def get_behavioral_profile(self, user_id: str) -> Dict[str, Any]:
        """Restituisce il profilo comportamentale distillato."""
        try:
            return self._load(user_id)
        except Exception:
            return self._default()

    def get_context_snippet(self, user_id: str) -> Optional[str]:
        """
        Restituisce 1-2 righe di contesto comportamentale per il prompt LLM.
        Restituisce None se dati insufficienti (< _MIN_SESSIONS_FOR_INJECTION sessioni).
        """
        try:
            data = self._load(user_id)
            sessions = data.get("sessions_count", 0)
            if sessions < _MIN_SESSIONS_FOR_INJECTION:
                return None

            style = data.get("interaction_style", {})
            topic_emotion = data.get("topic_emotion_map", {})
            peak_hours = data.get("peak_hours", [0] * 24)

            parts = []

            # --- Stile risposta preferito ---
            total_user = style.get("total_user_chars", 0)
            total_asst = style.get("total_assistant_chars", 0)
            avg_user = style.get("avg_user_msg_length", 0)
            if total_user > 0 and total_asst > 0:
                ratio = total_user / total_asst
                if ratio < 0.25:
                    style_label = "risposte dettagliate"
                elif ratio < 0.6:
                    style_label = "risposte moderate"
                else:
                    style_label = "risposte brevi e dirette"
                parts.append(f"Stile preferito: {style_label}")

                # Lunghezza media messaggi utente
                if avg_user > 100:
                    parts[-1] += " | Scrive messaggi lunghi"
                elif avg_user < 30:
                    parts[-1] += " | Scrive messaggi brevi"

            # --- Orario prevalente ---
            peak_hour = max(range(24), key=lambda h: peak_hours[h])
            if peak_hours[peak_hour] > 2:
                if 6 <= peak_hour < 12:
                    time_label = "mattina"
                elif 12 <= peak_hour < 15:
                    time_label = "pausa pranzo"
                elif 15 <= peak_hour < 19:
                    time_label = "pomeriggio"
                elif 19 <= peak_hour < 23:
                    time_label = "sera"
                else:
                    time_label = "notte"
                if parts:
                    parts[-1] += f" | Orario prevalente: {time_label}"
                else:
                    parts.append(f"Orario prevalente: {time_label}")

            # --- Topic sensibili (top 4 con emozione dominante non-neutral) ---
            sensitive = []
            for topic, emotions in topic_emotion.items():
                total = sum(emotions.values())
                if total < 2:
                    continue
                # Emozione dominante
                dominant = max(emotions, key=emotions.get)
                dominant_count = emotions[dominant]
                if dominant != "neutral" and dominant_count >= 2:
                    sensitive.append((topic, dominant, dominant_count))
            if sensitive:
                sensitive.sort(key=lambda x: x[2], reverse=True)
                top = sensitive[:4]
                topic_str = ", ".join(f"{t}→{e} ({c}x)" for t, e, c in top)
                parts.append(f"Topic ricorrenti: {topic_str}")

            if not parts:
                return None

            snippet = "\n".join(parts)
            log("BEHAVIORAL_CONTEXT", user_id=user_id, snippet=snippet[:80])
            return snippet

        except Exception as e:
            logger.debug("BEHAVIORAL_CONTEXT_ERROR user=%s err=%s", user_id, e)
            return None


# Istanza globale
behavioral_memory = BehavioralMemory()
