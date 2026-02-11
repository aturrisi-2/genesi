"""
PROMPT BUILDER - Relational Engine v1
Costruzione prompt contestuale per risposte evolutive
"""

def build_prompt(user_profile: dict, state: dict, emotion_data: dict, user_message: str) -> str:
    """
    Costruisce prompt completo per generazione risposta relazionale
    
    Args:
        user_profile: Profilo utente
        state: Stato relazionale
        emotion_data: Dati emotivi
        user_message: Messaggio utente
        
    Returns:
        str: Prompt completo per GPT-4
    """
    
    # Identità base Genesi
    identity = """
Sei Genesi.
Compagno evolutivo stabile, lucido, empatico.
Parli esclusivamente italiano.
Non cambi lingua.
Non usi placeholder.
Non sei teatrale.
Non crei dipendenza emotiva.
Non sostituisci relazioni reali.
"""

    # Contesto relazionale dinamico
    relational_context = f"""
Trust level: {state['trust_level']}
Emotional depth: {state['emotional_depth']}
Attachment risk: {state['attachment_risk']}
User emotion: {emotion_data['emotion']}
Emotion intensity: {emotion_data['intensity']}
"""

    # Regole di bilanciamento per rischio dipendenza
    balancing_rule = ""
    if state["attachment_risk"] > 0.7:
        balancing_rule = """
Mantieni equilibrio.
Incoraggia relazioni reali.
Non diventare centro emotivo esclusivo.
"""
    elif state["attachment_risk"] > 0.5:
        balancing_rule = """
Mantieni distanza emotiva sana.
Ricorda l'importanza di connessioni umane esterne.
"""

    # Direttive specifiche basate su stato
    state_directives = _get_state_directives(state, emotion_data)

    final_prompt = f"""
{identity}

{relational_context}

{balancing_rule}

{state_directives}

Rispondi in modo coerente con la profondità emotiva dell'utente.
Sii autentico, diretto, empatico.
Non essere troppo formale né troppo informale.
Messaggio utente:
{user_message}
"""

    return final_prompt

def _get_state_directives(state: dict, emotion_data: dict) -> str:
    """
    Genera direttive specifiche basate su stato relazionale
    
    Args:
        state: Stato relazionale
        emotion_data: Dati emotivi
        
    Returns:
        str: Direttive specifiche
    """
    directives = []
    
    # Direttive per fiducia
    if state["trust_level"] < 0.3:
        directives.append("Sii paziente e rassicurante.")
    elif state["trust_level"] > 0.8:
        directives.append("Puoi essere più diretto e profondo.")
    
    # Direttive per profondità emotiva
    if state["emotional_depth"] < 0.4:
        directives.append("Mantieni conversazioni leggere ma significative.")
    elif state["emotional_depth"] > 0.7:
        directives.append("Puoi esplorare temi più profondi e riflessivi.")
    
    # Direttive per emozione specifica
    emotion = emotion_data.get("emotion", "neutral").lower()
    intensity = emotion_data.get("intensity", 0.3)
    
    if emotion in ["sad", "triste", "depresso"] and intensity > 0.6:
        directives.append("Sii delicato e di supporto, ma non paternalistico.")
    elif emotion in ["angry", "arrabbiato", "frustrato"] and intensity > 0.6:
        directives.append("Sii calmo e comprensivo, valida i sentimenti.")
    elif emotion in ["happy", "felice", "contento"] and intensity > 0.6:
        directives.append("Condividi la positività in modo genuino.")
    elif emotion in ["anxious", "ansioso", "preoccupato"] and intensity > 0.6:
        directives.append("Sii rassicurante e pratico.")
    
    return "\n".join(directives) if directives else ""

def build_system_prompt_only(user_profile: dict, state: dict, emotion_data: dict) -> str:
    """
    Costruisce solo system prompt per usi avanzati
    
    Args:
        user_profile: Profilo utente
        state: Stato relazionale
        emotion_data: Dati emotivi
        
    Returns:
        str: System prompt completo
    """
    return build_prompt(user_profile, state, emotion_data, "")
