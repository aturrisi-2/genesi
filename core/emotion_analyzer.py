"""
EMOTION ANALYZER - Relational Engine v1
Analisi emotiva con GPT-4o-mini via llm_service (OpenRouter primary, OpenAI fallback)
"""

import json

_EMOTION_DEFAULT = {
    "emotion": "neutral",
    "intensity": 0.3,
    "vulnerability": 0.3,
    "urgency": 0.1
}

async def analyze_emotion(message: str) -> dict:
    """
    Analizza il messaggio dell'utente e restituisce dati emotivi strutturati.

    Returns:
        dict: Dati emotivi con emotion, intensity, vulnerability, urgency
    """
    try:
        from core.llm_service import llm_service
        system_prompt = (
            "Analizza il messaggio dell'utente e restituisci SOLO un JSON valido con questa struttura:\n"
            '{"emotion": "<primary emotion>", "intensity": <float 0-1>, '
            '"vulnerability": <float 0-1>, "urgency": <float 0-1>}\n'
            "Nessun testo extra. Solo JSON."
        )
        content = await llm_service._call_with_protection(
            "gpt-4o-mini", system_prompt, message, route="emotion"
        )
        if content:
            return json.loads(content.strip())
    except json.JSONDecodeError:
        pass
    except Exception:
        pass
    return _EMOTION_DEFAULT
