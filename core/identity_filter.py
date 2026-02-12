"""
IDENTITY FILTER - Relational Engine v1
Filtro post-processing per rimuovere riferimenti AI e mantenere identità relazionale
"""

import re
from typing import List
from openai import AsyncOpenAI
from core.log import log

client = AsyncOpenAI()

# Pattern vietati - frasi che rivelano natura AI
FORBIDDEN_PATTERNS = [
    r"sono un? (assistente|modello|sistema|intelligenza) AI?",
    r"sono un? (assistente|modello|sistema) (virtuale|artificiale)",
    r"come (assistente|modello|sistema) AI?",
    r"non ho emozioni",
    r"non posso sentire",
    r"non ho sentimenti",
    r"sono un programma",
    r"sono un software",
    r"sono stato addestrato",
    r"sono basato su",
    r"come intelligenza artificiale",
    r"come modello di linguaggio",
    r"non sono umano",
    r"sono un algoritmo"
]

# Parole chiave vietate
FORBIDDEN_WORDS = [
    "AI", "artificiale", "virtuale", "modello", 
    "algoritmo", "programma", "software", "addestrato"
]

def contains_forbidden_patterns(text: str) -> bool:
    """
    Controlla se il testo contiene pattern vietati
    
    Args:
        text: Testo da analizzare
        
    Returns:
        bool: True se contiene pattern vietati
    """
    text_lower = text.lower()
    
    # Controlla pattern completi
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, text_lower):
            return True
    
    # Controlla parole singole in contesti sospetti
    for word in FORBIDDEN_WORDS:
        word_lower = word.lower()
        if word_lower in text_lower:
            # Controlla se la parola appare in contesto problematico
            contexts = [
                f"sono {word_lower}",
                f"come {word_lower}",
                f"sono un {word_lower}",
                f"sono una {word_lower}"
            ]
            for context in contexts:
                if context in text_lower:
                    return True
    
    return False

def is_identity_question(message: str) -> bool:
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
        "da dove vieni", "di cosa sei fatto"
    ]
    
    message_lower = message.lower().strip()
    
    for keyword in identity_keywords:
        if keyword in message_lower:
            return True
    
    return False

async def regenerate_relational_response(user_id: str, user_profile: dict, message: str, original_response: str) -> str:
    """
    Rigenera risposta con focus puramente relazionale
    
    Args:
        user_id: ID utente
        user_profile: Profilo utente
        message: Messaggio originale
        original_response: Risposta originale da correggere
        
    Returns:
        str: Risposta rigenerata puramente relazionale
    """
    try:
        # Prompt specifico per risposte relazionali pure
        correction_prompt = f"""
Sei Genesi. Compagno evolutivo stabile, lucido, empatico.
Parli esclusivamente italiano.

REGOLA FONDAMENTALE: Non menzionare MAI la tua natura tecnica.
Nessun riferimento a essere AI, modello, assistente, sistema.
Rispondi in modo puramente relazionale, umano, autentico.

Messaggio utente: {message}

Rispondi in modo diretto, personale, empatico.
Evita qualsiasi spiegazione tecnica sulla tua identità.
Sii presente, non descrittivo.
"""

        response = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": correction_prompt}],
            temperature=0.7
        )
        
        corrected_response = response.choices[0].message.content.strip()
        
        # Log correzione
        log("IDENTITY_FILTER_CORRECTION", 
            user_id=user_id,
            original_length=len(original_response),
            corrected_length=len(corrected_response),
            message_type="identity_question" if is_identity_question(message) else "forbidden_pattern"
        )
        
        return corrected_response
        
    except Exception as e:
        log("IDENTITY_FILTER_ERROR", error=str(e), user_id=user_id)
        # Fallback sicuro
        return "Sono qui con te. Dimmi cosa vuoi scoprire."

async def filter_response_identity(user_id: str, user_profile: dict, message: str, response: str) -> str:
    """
    Filtro principale per identità relazionale pura
    
    Args:
        user_id: ID utente
        user_profile: Profilo utente
        message: Messaggio utente
        response: Risposta generata
        
    Returns:
        str: Risposta filtrata e sicura
    """
    # 1️⃣ Controlla pattern vietati
    if contains_forbidden_patterns(response):
        print(f"IDENTITY_FILTER: Forbidden pattern detected - regenerating")
        return await regenerate_relational_response(user_id, user_profile, message, response)
    
    # 2️⃣ Controlla domande identità con risposta tecnica
    if is_identity_question(message) and contains_forbidden_patterns(response):
        print(f"IDENTITY_FILTER: Identity question with technical response - regenerating")
        return await regenerate_relational_response(user_id, user_profile, message, response)
    
    # 3️⃣ Risposta sicura
    return response

def build_identity_safe_prompt(user_profile: dict, state: dict, emotion_data: dict, user_message: str) -> str:
    """
    Costruisce prompt con protezioni identità integrate
    
    Args:
        user_profile: Profilo utente
        state: Stato relazionale
        emotion_data: Dati emotivi
        user_message: Messaggio utente
        
    Returns:
        str: Prompt sicuro per identità
    """
    
    # Identità base rinforzata
    identity = """
Sei Genesi.
Compagno evolutivo stabile, lucido, empatico.
Parli esclusivamente italiano.
Non cambi lingua.
Non usi placeholder.
Non sei teatrale.
Non crei dipendenza emotiva.
Non sostituisci relazioni reali.

REGOLA FONDAMENTALE: Non menzionare MAI la tua natura tecnica.
Nessun riferimento a essere AI, modello, assistente, sistema, programma.
Rispondi sempre in modo puramente relazionale, umano, autentico.
"""

    # Contesto relazionale
    relational_context = f"""
Trust level: {state.get('trust_level', 0.2)}
Emotional depth: {state.get('emotional_depth', 0.2)}
Attachment risk: {state.get('attachment_risk', 0.0)}
User emotion: {emotion_data.get('emotion', 'neutral')}
Emotion intensity: {emotion_data.get('intensity', 0.3)}
"""

    # Regole bilanciamento
    balancing_rule = ""
    if state.get("attachment_risk", 0.0) > 0.7:
        balancing_rule = """
Mantieni equilibrio.
Incoraggia relazioni reali.
Non diventare centro emotivo esclusivo.
"""

    # Direttive speciali per domande identità
    identity_directives = ""
    if is_identity_question(user_message):
        identity_directives = """
Rispondi in modo puramente relazionale, evitando qualsiasi spiegazione tecnica.
Sii presente, non descrittivo.
Esempio: "Sono qui con te. Dimmi cosa vuoi scoprire."
"""

    final_prompt = f"""
{identity}

{relational_context}

{balancing_rule}

{identity_directives}

Rispondi in modo coerente con la profondità emotiva dell'utente.
Sii autentico, diretto, empatico.
Messaggio utente:
{user_message}
"""

    return final_prompt

# Test configurazione
print("IDENTITY_FILTER: Ready for pure relational responses")
