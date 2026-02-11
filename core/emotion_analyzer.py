"""
EMOTION ANALYZER - Relational Engine v1
Analisi emotiva con OpenAI GPT-4o-mini per relazioni evolutive
"""

import json
from openai import AsyncOpenAI

client = AsyncOpenAI()

async def analyze_emotion(message: str) -> dict:
    """
    Analizza il messaggio dell'utente e restituisce dati emotivi strutturati
    
    Args:
        message: Messaggio dell'utente da analizzare
        
    Returns:
        dict: Dati emotivi con emotion, intensity, vulnerability, urgency
    """
    try:
        system_prompt = """
Analizza il messaggio dell'utente e restituisci SOLO un JSON valido con questa struttura:

{
  "emotion": "<primary emotion>",
  "intensity": <float 0-1>,
  "vulnerability": <float 0-1>,
  "urgency": <float 0-1>
}

Nessun testo extra.
Solo JSON.
"""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message}
            ],
            temperature=0.2
        )

        content = response.choices[0].message.content.strip()

        try:
            return json.loads(content)
        except:
            return {
                "emotion": "neutral",
                "intensity": 0.3,
                "vulnerability": 0.3,
                "urgency": 0.1
            }
            
    except Exception as e:
        # Fallback sicuro in caso di errore API
        return {
            "emotion": "neutral",
            "intensity": 0.3,
            "vulnerability": 0.3,
            "urgency": 0.1
        }
