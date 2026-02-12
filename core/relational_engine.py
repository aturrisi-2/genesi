"""
RELATIONAL ENGINE - Relational Engine v1
Motore principale per generazione risposte evolutive con memoria persistente
"""

import logging
from openai import AsyncOpenAI
from core.emotion_analyzer import analyze_emotion
from core.relational_state import relational_state
from core.semantic_memory import semantic_memory
from core.identity_filter import filter_response_identity, build_identity_safe_prompt

logger = logging.getLogger(__name__)

client = AsyncOpenAI()

async def generate_relational_response(user_id: str, user_profile: dict, message: str, 
                                      emotion: Optional[Dict[str, Any]] = None, 
                                      context: Optional[Dict[str, Any]] = None) -> str:
    """
    Genera risposta relazionale evolutiva con memoria persistente
    
    Args:
        user_id: ID utente reale (no anonymous)
        user_profile: Profilo utente completo
        message: Messaggio utente
        emotion: Dati emotivi (opzionale)
        context: Contesto episodico (opzionale)
        
    Returns:
        str: Risposta generata da Genesi (filtrata)
    """
    try:
        # 0️⃣ RISPOSTA DETERMINISTICA SU DOMANDA NOME
        full_profile = await semantic_memory.get_user_profile(user_id)
        
        # Check for name question patterns
        name_patterns = ["come mi chiamo", "ti ricordi il mio nome", "qual è il mio nome", "come ti chiami"]
        if any(pattern.lower() in message.lower() for pattern in name_patterns):
            if full_profile.get("name"):
                logger.info(f"NAME_DETERMINISTIC_RESPONSE user_id={user_id} name={full_profile['name']}")
                return f"Ti chiami {full_profile['name']}."
            else:
                logger.info(f"NAME_QUESTION_NO_PROFILE user_id={user_id}")
                return "Non ho ancora imparato come ti chiami. Come ti chiami?"
        
        # 1️⃣ Analisi emotiva messaggio (se non fornita)
        if emotion is None:
            emotion = await analyze_emotion(message)
        
        # 2️⃣ Estrazione e salvataggio dati semantici
        await semantic_memory.extract_and_store_personal_data(message, user_id)
        
        # 3️⃣ Caricamento stato relazionale persistente
        state = await relational_state.load_state(user_id)
        
        # 4️⃣ Aggiornamento stato relazionale
        state = await relational_state.update_state(user_id, emotion)
        
        # 5️⃣ Aggiornamento pattern emotivi nel profilo
        await semantic_memory.update_emotional_pattern(user_id, emotion.get("emotion", "neutral"), emotion.get("intensity", 0.3))
        
        # 6️⃣ Log caricamento profilo (already loaded above)
        logger.info(f"PROFILE_LOADED user_id={user_id} has_name={bool(full_profile.get('name'))} name={full_profile.get('name')}")
        
        # 7️⃣ Costruzione prompt con memoria completa
        prompt = build_identity_safe_prompt(full_profile, state, emotion, message)
        
        # 8️⃣ Generazione risposta con GPT-4
        response = await client.chat.completions.create(
            model="gpt-4",
            messages=[{"role": "system", "content": prompt}],
            temperature=0.7
        )
        
        generated_response = response.choices[0].message.content.strip()
        
        # 9️⃣ FILTRO IDENTITÀ - controllo post-processing
        filtered_response = await filter_response_identity(user_id, full_profile, message, generated_response)
        
        # Log uso nome nella risposta
        if full_profile.get("name") and full_profile["name"] in filtered_response:
            logger.info(f"RELATIONAL_RESPONSE user_id={user_id} name_used={full_profile['name']}")
        
        # 10️⃣ Log per monitoring
        _log_relational_interaction(user_id, message, emotion, state, filtered_response)
        
        return filtered_response
        
    except Exception as e:
        # Log errore esplicito e rilancia - nessun fallback silenzioso
        logger.error(f"RELATIONAL_ENGINE_ERROR user_id={user_id} error={str(e)} message={message[:50]}")
        raise RuntimeError(f"Relational engine failed: {str(e)}")

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
    print(f"RELATIONAL_HISTORY: messages={state['relationship_history']['total_messages']}")
    print(f"RELATIONAL_RESPONSE_LENGTH: {len(response)} chars (identity filtered)")

async def get_relational_insights(user_id: str) -> dict:
    """
    Ottieni insights relazionali completi per monitoring
    
    Args:
        user_id: ID utente
        
    Returns:
        dict: Insights relazionali e memoria
    """
    try:
        # Stato relazionale
        state_summary = await relational_state.get_state_summary(user_id)
        
        # Memoria semantica
        memory_summary = await semantic_memory.get_memory_summary(user_id)
        
        return {
            "user_id": user_id,
            "relational_state": state_summary,
            "semantic_memory": memory_summary,
            "engine_version": "v1",
            "capabilities": [
                "emotion_analysis",
                "relational_memory", 
                "semantic_memory",
                "persistent_state",
                "identity_filtering"
            ]
        }
    except Exception as e:
        return {"error": str(e), "user_id": user_id}

def reset_relational_state(user_id: str):
    """
    Reset stato relazionale utente (per testing/debug)
    
    Args:
        user_id: ID utente
    """
    from core.storage import storage
    # Resetta stato relazionale
    storage.delete(f"relational_state:{user_id}")
    # Resetta profilo utente
    storage.delete(f"long_term_profile:{user_id}")
    print(f"RELATIONAL_STATE_RESET: user_id={user_id}")

# Test configurazione
print("RELATIONAL_ENGINE: Ready with persistent memory and semantic extraction")
