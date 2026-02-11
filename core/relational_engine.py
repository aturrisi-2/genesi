"""
RELATIONAL ENGINE - Relational Engine v1
Motore principale per generazione risposte evolutive con filtro identità
"""

from openai import AsyncOpenAI
from core.emotion_analyzer import analyze_emotion
from core.relational_state import load_state, update_state, get_state_summary
from core.identity_filter import filter_response_identity, build_identity_safe_prompt

client = AsyncOpenAI()

async def generate_relational_response(user_id: str, user_profile: dict, message: str) -> str:
    """
    Genera risposta relazionale evolutiva basata su stato emotivo e contesto
    con filtro identità per rimuovere riferimenti AI
    
    Args:
        user_id: ID utente
        user_profile: Profilo utente
        message: Messaggio utente
        
    Returns:
        str: Risposta generata da Genesi (filtrata)
    """
    try:
        # 1️⃣ Analisi emotiva messaggio
        emotion = await analyze_emotion(message)
        
        # 2️⃣ Caricamento stato relazionale
        state = load_state(user_id)
        
        # 3️⃣ Aggiornamento stato basato su emozioni
        state = update_state(user_id, emotion)
        
        # 4️⃣ Costruzione prompt sicuro per identità
        prompt = build_identity_safe_prompt(user_profile, state, emotion, message)
        
        # 5️⃣ Generazione risposta con GPT-4
        response = await client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "system", "content": prompt}],
            temperature=0.7
        )
        
        generated_response = response.choices[0].message.content.strip()
        
        # 6️⃣ FILTRO IDENTITÀ - controllo post-processing
        filtered_response = await filter_response_identity(user_id, user_profile, message, generated_response)
        
        # 7️⃣ Log per monitoring
        _log_relational_interaction(user_id, message, emotion, state, filtered_response)
        
        return filtered_response
        
    except Exception as e:
        # Fallback sicuro in caso di errore
        return "Mi dispiace, sto avendo qualche difficoltà. Potresti ripetere?"

def _log_relational_interaction(user_id: str, message: str, emotion: dict, state: dict, response: str):
    """
    Log dettagliato per monitoring relazionale
    
    Args:
        user_id: ID utente
        message: Messaggio utente
        emotion: Dati emotivi
        state: Stato relazionale
        response: Risposta generata (filtrata)
    """
    print(f"RELATIONAL_ENGINE: user_id={user_id}")
    print(f"RELATIONAL_EMOTION: {emotion['emotion']} (intensity={emotion['intensity']})")
    print(f"RELATIONAL_STATE: trust={state['trust_level']:.2f}, depth={state['emotional_depth']:.2f}, risk={state['attachment_risk']:.2f}")
    print(f"RELATIONAL_RESPONSE_LENGTH: {len(response)} chars (identity filtered)")

async def get_relational_insights(user_id: str) -> dict:
    """
    Ottieni insights relazionali per monitoring
    
    Args:
        user_id: ID utente
        
    Returns:
        dict: Insights relazionali
    """
    state_summary = get_state_summary(user_id)
    
    return {
        "user_id": user_id,
        "relational_state": state_summary,
        "engine_version": "v1",
        "capabilities": [
            "emotion_analysis",
            "relational_memory", 
            "adaptive_prompting",
            "attachment_monitoring",
            "identity_filtering"
        ]
    }

def reset_relational_state(user_id: str):
    """
    Reset stato relazionale utente (per testing/debug)
    
    Args:
        user_id: ID utente
    """
    from core.relational_state import _relational_memory
    if user_id in _relational_memory:
        del _relational_memory[user_id]
    print(f"RELATIONAL_STATE_RESET: user_id={user_id}")

# Test configurazione
print("RELATIONAL_ENGINE: Ready with identity filtering for pure relational responses")
