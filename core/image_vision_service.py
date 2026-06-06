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
        "'description': una descrizione ESTREMAMENTE CONCISA e DISCORSIVA (massimo 1 o 2 frasi brevi). VIETATO fare lunghi 'spiegoni', VIETATO descrivere vestiti o sfondi sterili. "
        "'unknown_faces_detected': booleano (true/false). Questo deve essere RIGOROSAMENTE 'true' se nell'immagine ci sono PERSONE e tu non sai chi siano. Nota bene: se non ti viene fornito nessun 'Riferimento volto noto', allora QUALSIASI persona nell'immagine è per te sconosciuta, quindi DEVI restituire 'true'. Se ti vengono forniti riferimenti, restituisci 'true' se c'è qualcuno che non corrisponde a quei riferimenti."
    )

    try:
        from core.face_memory_service import get_known_faces
        known_faces = await get_known_faces()
    except Exception as e:
        logger.error("Error loading face memory: %s", e)
        known_faces = []

    content_array = []
    # Aggiungi i riferimenti visivi
    for face in known_faces:
        try:
            face_name = face.get("name")
            face_img_path = face.get("image_path")
            face_desc = face.get("description_in_image", "")
            if face_img_path and os.path.exists(face_img_path):
                with open(face_img_path, "rb") as ref_f:
                    ref_data = ref_f.read()
                ref_mime = _get_mime(face_img_path)
                ref_b64 = base64.b64encode(ref_data).decode("utf-8")
                ref_url = f"data:{ref_mime};base64,{ref_b64}"
                content_array.append({"type": "text", "text": f"Riferimento volto noto: {face_name}. {face_desc}"})
                content_array.append({"type": "image_url", "image_url": {"url": ref_url, "detail": "low"}})
        except Exception as e:
            logger.warning("Failed to load reference face %s: %s", face.get("name"), e)

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
            response = await client.chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=1000,
                response_format={"type": "json_object"}
            )
            if not response.choices or not response.choices[0].message.content:
                raise ValueError("Empty content from vision model")
            
            content_str = response.choices[0].message.content.strip()
            logger.info("VISION_JSON_OUTPUT: %s", content_str)
            
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
                    "unknown_faces_detected": "unknown_faces_detected" in content_str.lower() and "true" in content_str.lower()
                }

            description = parsed.get("description", "")
            
            # Se rileva volti sconosciuti (o se il booleano è true, o stringa 'true')
            is_unknown = parsed.get("unknown_faces_detected")
            if is_unknown and str(is_unknown).lower() in ("true", "1", "yes", "si", "sì"):
                description += " [UNKNOWN_FACES_DETECTED]"
            
            log("IMAGE_VISION_OK", provider=provider, chars=len(description))
            return description
        except Exception as e:
            logger.warning("IMAGE_VISION_PROVIDER_FAILED provider=%s error=%s", provider, str(e))
            log("IMAGE_VISION_PROVIDER_FAILED", provider=provider, error=str(e)[:120])
            last_error = e
            continue

    # Tutti i provider hanno fallito
    logger.error("IMAGE_VISION_ERROR error=%s", str(last_error), exc_info=True)
    log("IMAGE_VISION_ERROR", error=str(last_error))
    raise RuntimeError(f"Vision analysis failed: {str(last_error)}")
