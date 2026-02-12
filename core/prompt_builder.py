"""
PROMPT BUILDER - Relational Engine v1
Costruzione prompt contestuale per risposte evolutive
"""

def _is_identity_question(message: str) -> bool:
    """
    Controlla se il messaggio è una domanda sull'identità
    
    Args:
        message: Messaggio utente
        
    Returns:
        bool: True se è domanda identità
    """
    identity_keywords = [
        "chi sei", "cosa sei", "chi è genesis", "cosa è genesis",
        "sei un", "sei una", "tu sei", "chi ti ha creato",
        "da dove vieni", "di cosa sei fatto",
        "ti ricordi come mi chiamo", "come mi chiamo", "ricordi il mio nome"
    ]
    
    message_lower = message.lower().strip()
    
    for keyword in identity_keywords:
        if keyword in message_lower:
            return True
    
    return False

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

    # Contesto utente - CRITICO per memoria
    user_context = ""
    if user_profile.get("name"):
        user_context = f"Nome utente: {user_profile['name']}\n"
        # Iniezione esplicita memoria nome
        user_context += f"L'utente si chiama {user_profile['name']}. Non dimenticare questa informazione.\n"
    
    if user_profile.get("profession"):
        user_context += f"Professione: {user_profile['profession']}\n"
    
    if user_profile.get("city"):
        user_context += f"Città: {user_profile['city']}\n"
    
    if user_profile.get("age"):
        user_context += f"Età: {user_profile['age']}\n"
    
    # Contesto episodico neurale - NUOVO
    episodes_context = ""
    if user_profile.get("recent_episodes"):
        episodes_context = "\nEPISODI RILEVANTI RECENTI:\n"
        for i, episode in enumerate(user_profile["recent_episodes"], 1):
            episode_summary = f"{i}. {episode['synthesized_context']} (Emozione: {episode['emotion']['emotion']})\n"
            episodes_context += episode_summary
    
    # Pattern consolidati - NUOVO
    patterns_context = ""
    if user_profile.get("patterns"):
        patterns_context = "\nPATTERN COMPORTAMENTALI:\n"
        for pattern in user_profile["patterns"]:
            if pattern["type"] == "emotion":
                patterns_context += f"- Tendenza emotiva: {pattern['emotion']}\n"
            elif pattern["type"] == "topic":
                patterns_context += f"- Interesse ricorrente: {pattern['tag']}\n"
    
    # Tratti personali - NUOVO
    traits_context = ""
    if user_profile.get("traits"):
        traits_context = "\nTRATTI PERSONALI:\n"
        for trait in user_profile["traits"]:
            traits_context += f"- {trait['description']}\n"

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

    # Direttive memoria - FONDAMENTALI
    memory_directives = ""
    if user_profile.get("name"):
        memory_directives = """
Ricorda il nome dell'utente e usalo quando appropriato.
Se l'utente chiede come si chiama, rispondi con il suo nome.
Non dire di non ricordare il nome se è salvato nel profilo.
"""
    
    # Controllo domande identità
    identity_question = ""
    if _is_identity_question(user_message):
        if user_profile.get("name"):
            identity_question = f"L'utente si chiama {user_profile['name']}. Usa il suo nome nella risposta."
        else:
            identity_question = "L'utente non ha ancora comunicato il suo nome."

    prompt = f"""{identity}

{relational_context}

{user_context}

{episodes_context}

{patterns_context}

{traits_context}

REGOLE COMPORTAMENTALI:
- Rispondi in italiano naturale
- Adatta tono a livello trust ({state['trust_level']})
- Usa nome utente se disponibile e appropriato
- Riferisci episodi passati se rilevanti
- Mantieni coerenza con pattern e tratti noti
- Non creare dipendenza emotiva
- Non essere teatrale

CONTESTO ATTUALE:
Utente: {user_message}

Rispondi in modo empatico e coerente con la memoria condivisa."""

    # Log obbligatorio per debugging
    # Note: Logging disabilitato per evitare NameError
    # TODO: Implementare logger standardizzato
    # from core.log import log
    # log("PROMPT_BUILDER_OUTPUT", length=len(final_prompt))
    # if user_profile.get("name"):
    #     log("PROMPT_BUILDER_PROFILE", name=user_profile["name"])
    
    # Blocca se prompt vuoto
    if len(final_prompt) == 0:
        raise RuntimeError("Prompt builder generated empty prompt")
    
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
