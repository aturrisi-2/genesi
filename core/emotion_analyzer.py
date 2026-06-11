"""
EMOTION ANALYZER - Relational Engine v2
Analisi emotiva con GPT-4o-mini via llm_service.
Restituisce: emotion, intensity, vulnerability, urgency, needs.
"""

import json

_EMOTION_DEFAULT = {
    "emotion": "neutral",
    "intensity": 0.3,
    "vulnerability": 0.3,
    "urgency": 0.1,
    "needs": "ascolto"
}

_SYSTEM_PROMPT = (
    "Analizza il messaggio dell'utente e restituisci SOLO un JSON valido con questa struttura:\n"
    '{"emotion": "<emozione primaria in inglese>", "intensity": <float 0-1>, '
    '"vulnerability": <float 0-1>, "urgency": <float 0-1>, '
    '"needs": "<cosa cerca l\'utente tra: conforto|soluzione|ascolto|sfogo|informazione|motivazione|condivisione>"}\n'
    "Nessun testo extra. Solo JSON puro.\n"
    "Esempi di emotion: neutral, happy, sad, anxious, stressed, angry, tired, lonely, frustrated, hopeful, worried.\n"
    "needs: scegli il termine più appropriato tra quelli elencati."
)


async def analyze_emotion(message: str) -> dict:
    """
    Analizza il messaggio dell'utente e restituisce dati emotivi strutturati.
    Returns dict con: emotion, intensity, vulnerability, urgency, needs
    """
    if not message or not message.strip():
        return dict(_EMOTION_DEFAULT)
    try:
        from core.llm_service import llm_service
        content = await llm_service._call_with_protection(
            "gpt-4o-mini", _SYSTEM_PROMPT, message[:400], route="emotion"
        )
        if content:
            data = json.loads(content.strip())
            # Valida e normalizza
            result = dict(_EMOTION_DEFAULT)
            result["emotion"] = str(data.get("emotion", "neutral")).lower()
            result["intensity"] = max(0.0, min(1.0, float(data.get("intensity", 0.3))))
            result["vulnerability"] = max(0.0, min(1.0, float(data.get("vulnerability", 0.3))))
            result["urgency"] = max(0.0, min(1.0, float(data.get("urgency", 0.1))))
            result["needs"] = str(data.get("needs", "ascolto"))
            return result
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    except Exception:
        pass
    return dict(_EMOTION_DEFAULT)
