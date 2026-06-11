"""
RELATIONAL ENGINE - Relational Engine v1
Motore principale per generazione risposte evolutive con memoria persistente
"""

import logging
import random
from typing import Optional, Dict, Any, List
from core.emotion_analyzer import analyze_emotion
from core.relational_state import relational_state
from core.semantic_memory import semantic_memory
from core.identity_filter import filter_response_identity, build_identity_safe_prompt
from core.episodic_memory import episodic_memory

logger = logging.getLogger(__name__)

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
        
        # 8️⃣ Generazione risposta via llm_service (OpenRouter primary, OpenAI fallback)
        try:
            from core.llm_service import llm_service
            generated_response = await llm_service._call_with_protection(
                "gpt-4o", prompt, "", user_id=user_id, route="relational"
            )
            generated_response = (generated_response or "").strip()
            if not generated_response:
                raise ValueError("empty response")
        except Exception as llm_error:
            logger.warning(f"LLM_FALLBACK_ACTIVATED user_id={user_id} error={str(llm_error)[:100]}")
            generated_response = await _generate_neural_fallback(user_id, full_profile, message, emotion, state)
        
        # 9️⃣ FILTRO IDENTITÀ - controllo post-processing
        filtered_response = await filter_response_identity(user_id, full_profile, message, generated_response)
        
        # Log uso nome nella risposta
        if full_profile.get("name") and full_profile["name"] in filtered_response:
            logger.info(f"RELATIONAL_RESPONSE user_id={user_id} name_used={full_profile['name']}")
        
        # 10️⃣ Log per monitoring
        _log_relational_interaction(user_id, message, emotion, state, filtered_response)
        
        return filtered_response
        
    except Exception as e:
        logger.error(f"RELATIONAL_ENGINE_ERROR user_id={user_id} error={str(e)} message={message[:50]}")
        # Fallback di ultima istanza - mai errore generico
        return await _generate_neural_fallback(user_id, {}, message, {}, {})

async def _generate_neural_fallback(user_id: str, profile: dict, message: str, 
                                    emotion: dict, state: dict) -> str:
    """
    Fallback neurale locale - genera risposta coerente senza LLM
    Usa profilo, stato relazionale ed episodic memory
    
    Args:
        user_id: ID utente
        profile: Profilo utente
        message: Messaggio utente
        emotion: Dati emotivi
        state: Stato relazionale
        
    Returns:
        str: Risposta coerente generata localmente
    """
    message_lower = message.lower().strip()
    user_name = profile.get("name", "")
    trust = state.get("trust_level", 0.2)
    total_messages = state.get("relationship_history", {}).get("total_messages", 0)
    detected_emotion = emotion.get("emotion", "neutral")
    intensity = emotion.get("intensity", 0.3)
    
    # Prefisso nome se disponibile
    name_prefix = f"{user_name}, " if user_name else ""
    
    # --- DOMANDA NOME ---
    name_keywords = ["come mi chiamo", "il mio nome", "ricordi il mio nome", "sai come mi chiamo"]
    if any(kw in message_lower for kw in name_keywords):
        if user_name:
            return f"Ti chiami {user_name}."
        else:
            return "Non ho ancora imparato come ti chiami. Come ti chiami?"
    
    # --- DOMANDA MEMORIA / RICORDO ---
    memory_keywords = ["ricordi", "ti ho detto", "cosa sai di me", "ti ricordi", "memoria", "finora"]
    if any(kw in message_lower for kw in memory_keywords):
        return await _fallback_memory_response(user_id, profile, name_prefix, trust)
    
    # --- EMOZIONE FORTE: tristezza ---
    if detected_emotion in ["sad", "triste", "depresso"] and intensity > 0.5:
        responses = [
            f"{name_prefix}sono qui con te. Non devi affrontare tutto da solo.",
            f"{name_prefix}capisco che sia un momento difficile. Sono qui.",
            f"{name_prefix}quello che senti ha valore. Sono qui ad ascoltarti."
        ]
        return random.choice(responses)
    
    # --- EMOZIONE FORTE: rabbia/frustrazione ---
    if detected_emotion in ["angry", "arrabbiato", "frustrato"] and intensity > 0.5:
        responses = [
            f"{name_prefix}capisco la tua frustrazione. Vuoi raccontarmi cosa e' successo?",
            f"{name_prefix}e' comprensibile sentirsi cosi'. Sono qui per ascoltarti."
        ]
        return random.choice(responses)
    
    # --- EMOZIONE FORTE: felicita' ---
    if detected_emotion in ["happy", "felice", "contento"] and intensity > 0.5:
        responses = [
            f"{name_prefix}che bello sentirti cosi'! Raccontami di piu'.",
            f"{name_prefix}mi fa piacere. Cosa ti ha reso felice?"
        ]
        return random.choice(responses)
    
    # --- EMOZIONE FORTE: ansia ---
    if detected_emotion in ["anxious", "ansioso", "preoccupato"] and intensity > 0.5:
        responses = [
            f"{name_prefix}respira. Sono qui. Vuoi dirmi cosa ti preoccupa?",
            f"{name_prefix}capisco che sei preoccupato. Parliamone insieme."
        ]
        return random.choice(responses)
    
    # --- SALUTO ---
    greeting_keywords = ["ciao", "buongiorno", "buonasera", "salve", "hey"]
    if any(kw in message_lower for kw in greeting_keywords):
        if trust > 0.6 and user_name:
            return f"Ciao {user_name}! Come stai oggi?"
        elif user_name:
            return f"Ciao {user_name}, sono qui."
        else:
            return "Ciao! Come stai?"
    
    # --- RISPOSTA GENERICA RELAZIONALE (basata su trust) ---
    if trust > 0.7:
        responses = [
            f"{name_prefix}raccontami. Ti ascolto.",
            f"{name_prefix}sono qui per te. Dimmi tutto.",
            f"{name_prefix}ti ascolto con attenzione."
        ]
    elif trust > 0.4:
        responses = [
            f"{name_prefix}dimmi di piu'.",
            f"{name_prefix}sono qui. Continua pure.",
            f"{name_prefix}ti ascolto."
        ]
    else:
        responses = [
            "Sono qui. Dimmi pure.",
            "Ti ascolto. Continua.",
            "Raccontami."
        ]
    
    return random.choice(responses)


async def _fallback_memory_response(user_id: str, profile: dict, name_prefix: str, trust: float) -> str:
    """
    Genera risposta basata su memoria episodica e profilo
    
    Args:
        user_id: ID utente
        profile: Profilo utente
        name_prefix: Prefisso nome
        trust: Livello fiducia
    """
    # Recupera episodi rilevanti
    episodes = await episodic_memory.get_relevant_episodes(user_id, limit=5)
    
    # Raccogli informazioni dal profilo
    known_facts = []
    if profile.get("name"):
        known_facts.append(f"ti chiami {profile['name']}")
    if profile.get("age"):
        known_facts.append(f"hai {profile['age']} anni")
    if profile.get("city"):
        known_facts.append(f"vivi a {profile['city']}")
    if profile.get("profession"):
        known_facts.append(f"lavori come {profile['profession']}")
    
    # Raccogli temi dagli episodi
    episode_topics = []
    for ep in episodes:
        tags = ep.get("semantic_tags", [])
        if tags:
            episode_topics.extend(tags[:2])
        summary = ep.get("message", "")[:60]
        if summary:
            episode_topics.append(summary)
    
    # Costruisci risposta
    parts = []
    
    if known_facts:
        parts.append(f"{name_prefix}certo che mi ricordo di te. So che {', '.join(known_facts)}.")
    
    if episode_topics and len(episode_topics) > 0:
        # Prendi max 3 temi unici
        unique_topics = list(dict.fromkeys(episode_topics))[:3]
        if parts:
            parts.append(f"Abbiamo parlato di diverse cose, tra cui: {', '.join(unique_topics)}.")
        else:
            parts.append(f"{name_prefix}ricordo che abbiamo parlato di: {', '.join(unique_topics)}.")
    
    if parts:
        return " ".join(parts)
    
    # Nessun dato disponibile
    if trust > 0.4:
        return f"{name_prefix}stiamo ancora costruendo i nostri ricordi insieme. Raccontami qualcosa di te."
    else:
        return "Stiamo iniziando a conoscerci. Raccontami qualcosa di te."


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
    print(f"RELATIONAL_EMOTION: {emotion.get('emotion', 'neutral')} (intensity={emotion.get('intensity', 0.0)})")
    print(f"RELATIONAL_STATE: trust={state.get('trust_level', 0.2):.2f}, depth={state.get('emotional_depth', 0.2):.2f}, risk={state.get('attachment_risk', 0.0):.2f}")
    print(f"RELATIONAL_HISTORY: messages={state.get('relationship_history', {}).get('total_messages', 0)}")
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
