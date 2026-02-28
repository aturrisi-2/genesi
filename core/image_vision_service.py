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


def _get_vision_clients() -> list:
    """
    Ritorna lista di (AsyncOpenAI client, label) in ordine di priorità.
    OpenRouter primo (billing separato da OpenAI), poi OpenAI diretto.
    """
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
        # Nessuna chiave configurata — prova con variabile d'ambiente default
        clients.append((AsyncOpenAI(), "openai_default"))
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
        "Sei un analizzatore di immagini esperto. "
        "Descrivi ciò che vedi nell'immagine in italiano, in modo dettagliato e preciso. "
        "Includi: composizione, oggetti principali, persone (se presenti), colori dominanti, "
        "ambiente/sfondo, illuminazione, stile visivo. "
        "Se l'immagine contiene testo, riportalo fedelmente. "
        "NON inventare dettagli che non sono visibili. "
        "NON aggiungere interpretazioni soggettive non supportate dalla visione."
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Descrivi questa immagine in dettaglio."},
                {"type": "image_url", "image_url": {"url": data_url, "detail": "high"}},
            ],
        },
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
            )
            description = response.choices[0].message.content.strip()
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
