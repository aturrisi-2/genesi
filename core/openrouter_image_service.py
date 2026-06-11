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

_IMAGE_TIMEOUT = 28.0  # secondi massimi per generazione immagine (sync client timeout)

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

    def _generate_sync(self, prompt: str, user_id: Optional[str] = None, input_image_data_url: Optional[str] = None) -> Optional[str]:
        """
        Versione SINCRONA — eseguita in asyncio.to_thread() per non corrompere
        l'event loop asyncio in caso di cancellazione/timeout.
        Usa il client OpenAI sync con timeout integrato.
        """
        from openai import OpenAI

        client = OpenAI(
            api_key=self._key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://genesi.app",
                "X-Title": "Genesi",
            },
            timeout=_IMAGE_TIMEOUT,
        )

        logger.info(
            "OPENROUTER_IMAGE_REQUEST user=%s prompt_len=%d model=%s has_input_image=%s",
            user_id, len(prompt), MODEL_ID, bool(input_image_data_url),
        )

        # Composizione messaggio: con o senza immagine sorgente (image editing vs text-to-image)
        if input_image_data_url:
            message_content = [
                {"type": "image_url", "image_url": {"url": input_image_data_url}},
                {"type": "text", "text": prompt},
            ]
        else:
            message_content = prompt

        response = client.chat.completions.create(
            model=MODEL_ID,
            messages=[{"role": "user", "content": message_content}],
            extra_body={"modalities": ["image", "text"]},
        )

        message = response.choices[0].message

        # Caso 1: campo .images nella risposta
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

    async def generate_image(self, prompt: str, user_id: Optional[str] = None, input_image_data_url: Optional[str] = None) -> Optional[str]:
        """
        Genera un'immagine via OpenRouter (Gemini 3.1 Flash Image Preview).

        Esegue la chiamata in un thread separato (asyncio.to_thread) per garantire
        che un timeout non corrompa l'event loop asyncio.

        Returns:
            str: base64 data URL oppure None se fallisce/timeout
        """
        if not self.enabled:
            return None

        if not prompt or not prompt.strip():
            return None

        try:
            return await asyncio.wait_for(
                asyncio.to_thread(self._generate_sync, prompt, user_id, input_image_data_url),
                timeout=_IMAGE_TIMEOUT + 2.0,  # margine extra sopra il timeout sync
            )
        except Exception as e:
            logger.error(
                "OPENROUTER_IMAGE_ERROR user=%s model=%s error=%s",
                user_id, MODEL_ID, str(e)[:300],
            )
            return None


# Singleton
openrouter_image_service = OpenRouterImageService()
