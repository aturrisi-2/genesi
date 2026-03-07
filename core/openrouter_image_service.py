"""
OPENROUTER IMAGE SERVICE - Genesi Core
Generazione immagini via OpenRouter: Google Gemini 3.1 Flash Image Preview
(soprannome: "Nano Banana 2").

Provider primario per generazione immagini; AWS Bedrock resta come fallback.
Risposta: base64 data URL ("data:image/png;base64,...") usabile direttamente
come <img src="..."> nel browser senza dipendenze S3/hosting.
"""

import asyncio
import os
import re
import logging
from typing import Optional

_IMAGE_TIMEOUT = 30.0  # secondi massimi per generazione immagine

logger = logging.getLogger(__name__)

MODEL_ID = "google/gemini-3.1-flash-image-preview"


class OpenRouterImageService:
    def __init__(self):
        self._key = os.environ.get("OPENROUTER_API_KEY")
        self.enabled = bool(self._key)
        if self.enabled:
            logger.info("OPENROUTER_IMAGE_SERVICE_READY model=%s", MODEL_ID)
        else:
            logger.warning("OPENROUTER_IMAGE_SERVICE_DISABLED no OPENROUTER_API_KEY")

    async def generate_image(self, prompt: str, user_id: Optional[str] = None) -> Optional[str]:
        """
        Genera un'immagine via OpenRouter (Gemini 3.1 Flash Image Preview).

        Args:
            prompt: Descrizione testuale dell'immagine da generare
            user_id: ID utente (solo per logging)

        Returns:
            str: base64 data URL ("data:image/png;base64,...") oppure None se fallisce
        """
        if not self.enabled:
            return None

        if not prompt or not prompt.strip():
            return None

        try:
            from openai import AsyncOpenAI

            client = AsyncOpenAI(
                api_key=self._key,
                base_url="https://openrouter.ai/api/v1",
                default_headers={
                    "HTTP-Referer": "https://genesi.app",
                    "X-Title": "Genesi",
                },
            )

            logger.info(
                "OPENROUTER_IMAGE_REQUEST user=%s prompt_len=%d model=%s",
                user_id, len(prompt), MODEL_ID,
            )

            response = await asyncio.wait_for(
                client.chat.completions.create(
                    model=MODEL_ID,
                    messages=[{"role": "user", "content": prompt}],
                    extra_body={"modalities": ["image", "text"]},
                ),
                timeout=_IMAGE_TIMEOUT,
            )

            message = response.choices[0].message

            # Caso 1: campo .images nella risposta (formato OpenRouter image generation)
            images = getattr(message, "images", None)
            if images:
                for img in images:
                    if isinstance(img, dict):
                        data_url = img.get("image_url", {}).get("url", "")
                    else:
                        data_url = getattr(getattr(img, "image_url", None), "url", "") or ""
                    if data_url and data_url.startswith("data:image"):
                        logger.info(
                            "OPENROUTER_IMAGE_OK user=%s source=images_field data_url_len=%d",
                            user_id, len(data_url),
                        )
                        return data_url

            # Caso 2: data URL embedded nel campo content
            content = getattr(message, "content", "") or ""
            if content:
                match = re.search(r"data:image/[^;]+;base64,[A-Za-z0-9+/=]+", content)
                if match:
                    data_url = match.group(0)
                    logger.info(
                        "OPENROUTER_IMAGE_OK user=%s source=content_embedded data_url_len=%d",
                        user_id, len(data_url),
                    )
                    return data_url

            logger.warning(
                "OPENROUTER_IMAGE_NO_IMAGE_IN_RESPONSE user=%s content_len=%d",
                user_id, len(content),
            )
            return None

        except Exception as e:
            logger.error(
                "OPENROUTER_IMAGE_ERROR user=%s model=%s error=%s",
                user_id, MODEL_ID, str(e)[:300],
            )
            return None


# Singleton
openrouter_image_service = OpenRouterImageService()
