from core.llm import generate_response as llm_generate


async def handle_image(
    image_context: dict,
    user_message: str,
    user_id: str
) -> str:
    """
    Gestore dedicato per le immagini.
    Separa completamente il flusso immagini da quello documentale testuale.
    """
    
    # Estrai metadati dall'immagine
    document_mode = image_context.get('document_mode', 'image')
    ocr_reliability = image_context.get('ocr_reliability', 'none')
    content = image_context.get('content', '')
    description = image_context.get('description', 'Immagine caricata')
    filename = image_context.get('filename', 'sconosciuto')
    
    # Costruisci prompt base per immagini
    prompt = f"""
FILE IMMAGINE CARICATO:
- Nome file: {filename}
- Tipo: {document_mode}
- Affidabilità OCR: {ocr_reliability}
- Descrizione: {description}

REGOLE NON NEGOZIABILI:
- È VIETATO dire "non posso vedere l'immagine"
- È VIETATO chiedere descrizioni all'utente
- È VIETATO inventare dettagli visivi
- L'OCR NON è visione: usalo solo se l'utente chiede trascrizione
- La descrizione deve riguardare il file e il contesto generale, non i pixel

COMPORTAMENTO RICHIESTO:
- Se l'utente chiede "descrivimi l'immagine" o "cosa contiene": descrivi tipo file, contesto generale, limiti
- Se l'utente chiede "trascrivi" o "cosa c'è scritto": usa il testo OCR se disponibile
- Sii onesto sui limiti dell'OCR se affidabilità è bassa

"""
    
    # Aggiungi contenuto OCR solo se richiesto esplicitamente
    if any(keyword in user_message.lower() for keyword in ["trascrivi", "cosa c'è scritto", "leggi", "testo"]):
        if content.strip():
            if ocr_reliability == "low":
                prompt += f"\nTESTO OCR RILEVATO (AFFIDABILITÀ BASSA):\n{content}\n"
            else:
                prompt += f"\nTESTO OCR RILEVATO:\n{content}\n"
        else:
            prompt += "\nNESSUN TESTO OCR RILEVATO.\n"
    
    prompt += f"\nRichiesta utente: {user_message}\n\nRispondi solo con il testo della risposta:"
    
    # Chiama LLM con GPT-4o per immagini
    response = llm_generate({
        "prompt": prompt,
        "model": "gpt-4o"
    })
    
    return response.strip()
