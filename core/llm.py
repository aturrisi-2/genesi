def generate_response(prompt_payload: dict) -> str:
    """
    Genera una risposta basata sul prompt fornito, adattandosi al ToneProfile.
    
    Args:
        prompt_payload: Dizionario contenente:
            - user_message: str
            - base_response: str
            - tone: ToneProfile (warmth, empathy, directness, verbosity)
    
    Returns:
        str: Risposta generata
    """
    response = prompt_payload.get("base_response", "")
    tone = prompt_payload.get("tone")

    if tone is None:
        return response

    user_message = prompt_payload.get("user_message", "").lower()

    # --- EMPATIA ---
    if tone.empathy > 0.7:
        if "grazie" in user_message:
            response += " È stato un piacere aiutarti."
        elif any(word in user_message for word in [
            "triste", "preoccupato", "preoccupata", "arrabbiato", "arrabbiata"
        ]):
            response = "Mi dispiace sentirlo. " + response

    # --- DIRETTEZZA ---
    if tone.directness > 0.7:
        for prefix in ["Ho capito, ", "Capisco, ", "Vedo che ", "Sì, "]:
            if response.startswith(prefix):
                response = response[len(prefix):]
                break

    # --- STILE ---
    response = response.replace("?", ".")

    return response
