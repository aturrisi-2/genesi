"""
IMAGE VISION SERVICE - Genesi Core v3
Descrizione immagini via OpenAI GPT-4o vision.
Primario: OpenRouter (quota separata). Fallback: OpenAI diretto.
Solo descrizione fedele, nessun testo inventato.
"""

import base64
import logging
import os
from openai import AsyncOpenAI
from core.log import log

logger = logging.getLogger(__name__)

# MIME types supportati per vision
_VISION_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".heic": "image/heic",
    ".heif": "image/heif",
}


def _get_mime(path: str) -> str:
    """Get MIME type from file path."""
    ext = os.path.splitext(path)[1].lower()
    return _VISION_MIME.get(ext, "image/png")


# Singleton clients — creati una sola volta al caricamento del modulo
# per evitare il leak di socket/httpx-client che si accumulano ad ogni chiamata.
_VISION_CLIENTS: list | None = None


def _get_vision_clients() -> list:
    """
    Ritorna lista di (AsyncOpenAI client, label) in ordine di priorità.
    OpenRouter primo (billing separato da OpenAI), poi OpenAI diretto.
    I client sono singleton: creati una sola volta e riutilizzati.
    """
    global _VISION_CLIENTS
    if _VISION_CLIENTS is not None:
        return _VISION_CLIENTS

    clients = []
    or_key = os.environ.get("OPENROUTER_API_KEY")
    oa_key = os.environ.get("OPENAI_API_KEY")
    if or_key:
        clients.append((
            AsyncOpenAI(
                api_key=or_key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={"HTTP-Referer": "https://genesi.app", "X-Title": "Genesi"},
            ),
            "openrouter",
        ))
    if oa_key:
        clients.append((AsyncOpenAI(api_key=oa_key), "openai"))
    if not clients:
        clients.append((AsyncOpenAI(), "openai_default"))

    _VISION_CLIENTS = clients
    return clients


async def describe_image(path: str) -> str:
    """
    Describe image content using GPT-4o vision.
    Tries OpenRouter first, falls back to OpenAI direct.
    Returns rich, faithful description — no invented details.

    Args:
        path: Absolute path to image file

    Returns:
        Description string
    """
    log("IMAGE_VISION_START", path=path)

    # Read and encode image once
    with open(path, "rb") as f:
        image_data = f.read()

    mime = _get_mime(path)
    b64 = base64.b64encode(image_data).decode("utf-8")
    data_url = f"data:{mime};base64,{b64}"

    system_prompt = (
        "Sei l'occhio di un'AI conversazionale. Analizza l'immagine e restituisci un JSON rigoroso con le seguenti chiavi: "
        "'description': una descrizione ESTREMAMENTE CONCISA e DISCORSIVA (massimo 1 o 2 frasi brevi). VIETATO fare lunghi 'spiegoni'. "
        "'gender_hints': array di oggetti con 'position' (es. 'sinistra', 'centro', 'destra' o posizioni numeriche 0,1,2...) e 'gender' (M o F dedotto dall'aspetto visivo) per ogni persona umana riconoscibile. Es: [{\"position\": \"sinistra\", \"gender\": \"M\"}, {\"position\": \"centro\", \"gender\": \"F\"}]. "
        "Formato richiesto: {\"description\": \"...\", \"gender_hints\": [...], \"unknown_faces_detected\": false, \"unknown_pets_detected\": false}. Nessun altro testo."
        "ATTENZIONE: Se ricevi dei riferimenti sui volti/animali noti, DEVI TASSATIVAMENTE elencare TUTTI i nomi forniti citando esattamente la loro POSIZIONE nella descrizione (es. 'Vedo Rita a sinistra e il cane Fido al centro'). "
        "'unknown_faces_detected': booleano (true/false). Regola assoluta: se nell'immagine è presente ALMENO UNA figura umana o volto che non corrisponde ESATTAMENTE a uno dei 'Riferimenti volto noto' forniti, imposta a 'true'. "
        "'unknown_pets_detected': booleano (true/false). Regola assoluta: se nell'immagine è presente un animale domestico (cane, gatto, uccello, ecc.) di cui NON è stato fornito il nome, imposta a 'true'. "
    )

    content_array = []
    
    try:
        from core.biometric_service import analyze_faces_biometric
        bio_result = await analyze_faces_biometric(path)
        recognized_names = bio_result.get("recognized_names", [])
        recognized_faces_list = bio_result.get("recognized_faces_with_positions", [])
        unknown_faces_detected = bio_result.get("unknown_faces_detected", False)
        unknown_faces_positions = bio_result.get("unknown_faces_positions", [])
        
        # Aggiunta Pet Recognition
        try:
            from core.biometric_pets_service import analyze_pets_biometric
            pet_result = await analyze_pets_biometric(path)
            recognized_names.extend(pet_result.get("recognized_names", []))
            recognized_faces_list.extend(pet_result.get("recognized_faces_with_positions", []))
            unknown_pets_detected = pet_result.get("unknown_faces_detected", False)
            unknown_pets_positions = pet_result.get("unknown_faces_positions", [])
        except Exception as e:
            logger.error("Error running biometric pets service: %s", e)
            unknown_pets_detected = False
            unknown_pets_positions = []
        
        if recognized_faces_list:
            names_str = " | ".join(recognized_faces_list)
            content_array.append({"type": "text", "text": f"Mappa esatta dei volti noti rilevati: {names_str}. REGOLA SPECIALE: Ignora l'istruzione di essere 'estremamente conciso'. Devi TASSATIVAMENTE includere nel campo 'description' l'elenco completo di questi nomi e la loro esatta posizione, senza riassumere o saltare nessuno."})
        
        if unknown_faces_detected:
            if unknown_faces_positions:
                pos_str = ", ".join(unknown_faces_positions)
                content_array.append({"type": "text", "text": f"ATTENZIONE: Ci sono persone nell'immagine di cui non è stato fornito il nome. Posizioni rilevate dal sistema biometrico: {pos_str}. DEVI impostare 'unknown_faces_detected' a true nel JSON. Nella tua 'description', limitati a descrivere visivamente la scena senza fare domande all'utente."})
            else:
                content_array.append({"type": "text", "text": "ATTENZIONE: Ci sono persone nell'immagine di cui non è stato fornito il nome. DEVI impostare 'unknown_faces_detected' a true nel JSON."})
        elif bio_result.get("total_faces", 0) > 0 and not unknown_faces_detected:
            content_array.append({"type": "text", "text": "Tutte le persone presenti hanno un nome fornito. DEVI impostare 'unknown_faces_detected' a false nel JSON."})
            
        if unknown_pets_detected:
            if unknown_pets_positions:
                pos_str = ", ".join(unknown_pets_positions)
                content_array.append({"type": "text", "text": f"ATTENZIONE: Ci sono animali domestici nell'immagine di cui non è stato fornito il nome. Posizioni rilevate: {pos_str}. DEVI impostare 'unknown_pets_detected' a true nel JSON. Nella tua 'description', limitati a descrivere visivamente la scena senza fare domande all'utente."})
            else:
                content_array.append({"type": "text", "text": "ATTENZIONE: Ci sono animali domestici nell'immagine di cui non è stato fornito il nome. DEVI impostare 'unknown_pets_detected' a true nel JSON."})
            
        log("VISION_PROMPT_INJECTED", names=str(recognized_names), unknown=unknown_faces_detected, unknown_pets=unknown_pets_detected)
    except Exception as e:
        logger.error("Error running biometric service: %s", e)

    content_array.append({"type": "text", "text": "Questa è l'immagine principale da analizzare. Rispondi SOLO in formato JSON valido:"})
    content_array.append({"type": "image_url", "image_url": {"url": data_url, "detail": "high"}})

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": content_array},
    ]

    clients = _get_vision_clients()
    last_error = None

    for client, provider in clients:
        try:
            log("IMAGE_VISION_TRY", provider=provider)
            model_name = "openai/gpt-4o" if provider == "openrouter" else "gpt-4o"
            response = await client.chat.completions.create(
                model=model_name,
                messages=messages,
                max_tokens=1000,
            )
            if not response.choices or not response.choices[0].message.content:
                raise ValueError("Empty content from vision model")
            
            content_str = response.choices[0].message.content.strip()
            log("VISION_RAW_OUTPUT", provider=provider, content=content_str)
            
            # Pulisci eventuali backtick markdown che il modello potrebbe aver aggiunto
            clean_json_str = content_str
            if clean_json_str.startswith("```json"):
                clean_json_str = clean_json_str[7:]
            if clean_json_str.startswith("```"):
                clean_json_str = clean_json_str[3:]
            if clean_json_str.endswith("```"):
                clean_json_str = clean_json_str[:-3]
            clean_json_str = clean_json_str.strip()

            import json
            try:
                parsed = json.loads(clean_json_str)
            except json.JSONDecodeError:
                # Se non è JSON valido, cerchiamo le keyword grezze
                parsed = {
                    "description": content_str, 
                    "unknown_faces_detected": "unknown_faces_detected" in content_str.lower() and "true" in content_str.lower(),
                    "unknown_pets_detected": "unknown_pets_detected" in content_str.lower() and "true" in content_str.lower()
                }

            description = parsed.get("description", "")
            
            # Se rileva volti sconosciuti (o se il booleano è true, o stringa 'true')
            is_unknown_faces = parsed.get("unknown_faces_detected")
            if is_unknown_faces and str(is_unknown_faces).lower() in ("true", "1", "yes", "si", "sì"):
                description += " [UNKNOWN_FACES_DETECTED]"
                
            is_unknown_pets = parsed.get("unknown_pets_detected")
            if is_unknown_pets and str(is_unknown_pets).lower() in ("true", "1", "yes", "si", "sì"):
                description += " [UNKNOWN_PETS_DETECTED]"
            
            # Estrai gender_hints se presenti
            gender_hints = parsed.get("gender_hints", [])
            if not isinstance(gender_hints, list):
                gender_hints = []
            
            log("IMAGE_VISION_OK", provider=provider, chars=len(description), gender_hints_count=len(gender_hints))
            return {
                "description": description,
                "gender_hints": gender_hints,
                "unknown_faces": is_unknown_faces and str(is_unknown_faces).lower() in ("true", "1", "yes", "si", "sì"),
                "unknown_pets": is_unknown_pets and str(is_unknown_pets).lower() in ("true", "1", "yes", "si", "sì"),
            }
        except Exception as e:
            logger.warning("IMAGE_VISION_PROVIDER_FAILED provider=%s error=%s", provider, str(e))
            log("IMAGE_VISION_PROVIDER_FAILED", provider=provider, error=str(e)[:120])
            last_error = e
            continue

    # Tutti i provider hanno fallito
    logger.error("IMAGE_VISION_ERROR error=%s", str(last_error), exc_info=True)
    log("IMAGE_VISION_ERROR", error=str(last_error))
    raise RuntimeError(f"Vision analysis failed: {str(last_error)}")
