def generate_response(prompt_payload: dict) -> str:
    """
    Genera una risposta basata sul prompt fornito, adattandosi al tono specificato.
    
    Args:
        prompt_payload: Dizionario contenente:
            - user_message: str - Il messaggio dell'utente
            - base_response: str - La risposta di base da modificare
            - tone: dict - Dizionario con i valori di tono (warmth, empathy, directness, verbosity)
    
    Returns:
        str: Risposta generata in base al tono specificato
    """
    response = prompt_payload.get("base_response", "")
    tone = prompt_payload.get("tone", {})
    
    # Aggiungi empatia se richiesto
    if tone("empathy", 0) > 0.7:
        if "grazie" in prompt_payload["user_message"].lower():
            response += " È stato un piacere aiutarti!"
        elif any(word in prompt_payload["user_message"].lower() 
                for word in ["triste", "preoccupato", "preoccupata", "arrabbiato"]):
            response = "Mi dispiace sentirlo. " + response
    
    # Rendi la risposta più diretta se richiesto
    if tone("directness", 0) > 0.7:
        # Rimuove prefissi comuni per rendere la risposta più diretta
        for prefix in ["Ho capito, ", "Capisco, ", "Vedo che ", "Sì, "]:
            if response.startswith(prefix):
                response = response[len(prefix):]
                break
    
    # Rimuovi punti interrogativi per evitare domande
    response = response.replace("?", ".")
    
    return response