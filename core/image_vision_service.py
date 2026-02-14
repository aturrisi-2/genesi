"""
IMAGE VISION SERVICE - Genesi Core v2
Descrizione immagini via OpenAI GPT-4o vision.
Solo descrizione fedele, nessun testo inventato.
"""

import base64
import logging
import mimetypes
from openai import AsyncOpenAI
from core.log import log

logger = logging.getLogger(__name__)

_client = AsyncOpenAI()

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
}


def _get_mime(path: str) -> str:
    """Get MIME type from file path."""
    import os
    ext = os.path.splitext(path)[1].lower()
    return _VISION_MIME.get(ext, "image/png")


async def describe_image(path: str) -> str:
    """
    Describe image content using GPT-4o vision.
    Returns faithful description only — no invented text.
    
    Args:
        path: Absolute path to image file
        
    Returns:
        Description string
    """
    log("IMAGE_VISION_START", path=path)

    try:
        # Read and encode image
        with open(path, "rb") as f:
            image_data = f.read()

        mime = _get_mime(path)
        b64 = base64.b64encode(image_data).decode("utf-8")
        data_url = f"data:{mime};base64,{b64}"

        response = await _client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Sei un analizzatore di immagini. "
                        "Descrivi SOLO ciò che vedi nell'immagine, in italiano. "
                        "Sii preciso e conciso. "
                        "NON inventare dettagli che non sono visibili. "
                        "NON aggiungere interpretazioni soggettive. "
                        "Se l'immagine contiene testo, riportalo fedelmente."
                    ),
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": "Descrivi questa immagine in modo preciso e conciso.",
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": data_url, "detail": "auto"},
                        },
                    ],
                },
            ],
            max_tokens=500,
        )

        description = response.choices[0].message.content.strip()
        log("IMAGE_VISION_DONE", chars=len(description))
        return description

    except Exception as e:
        logger.error("IMAGE_VISION_ERROR error=%s", str(e), exc_info=True)
        log("IMAGE_VISION_ERROR", error=str(e))
        raise RuntimeError(f"Vision analysis failed: {str(e)}")
