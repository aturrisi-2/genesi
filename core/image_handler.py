import os
import base64
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

_client = None

def _get_client():
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.getenv("OPENAI_API_KEY", ""))
    return _client


def _encode_image_base64(file_path: str) -> str:
    """Codifica immagine in base64 per GPT-4o Vision."""
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _get_mime_for_image(file_path: str) -> str:
    """Determina MIME type per data URI."""
    ext = os.path.splitext(file_path)[1].lower()
    mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp"}
    return mime_map.get(ext, "image/jpeg")


async def handle_image(
    image_context: dict,
    user_message: str,
    user_id: str,
    file_path: str = ""
) -> str:
    """
    Gestore dedicato per le immagini.
    Usa GPT-4o Vision per analisi visiva reale quando il file è disponibile.
    Fallback a OCR + testo se Vision non disponibile.
    """
    ocr_text = image_context.get("content", "")
    has_text = image_context.get("has_clear_text", False)
    filename = image_context.get("filename", "sconosciuto")

    # STRATEGIA 1: GPT-4o Vision (immagine reale)
    if file_path and os.path.exists(file_path):
        try:
            b64 = _encode_image_base64(file_path)
            mime = _get_mime_for_image(file_path)
            data_uri = f"data:{mime};base64,{b64}"

            system_prompt = """Sei un analista visivo. Analizza l'immagine in modo dettagliato e preciso.

REGOLE:
- Descrivi TUTTO ciò che vedi: soggetti, ambiente, colori, testo, dettagli rilevanti
- Se l'immagine contiene testo: trascrivilo integralmente
- Se è uno screenshot: descrivi l'interfaccia, i contenuti visibili, il contesto
- Se è una foto: descrivi soggetti, sfondo, illuminazione, composizione
- Sii specifico e minuzioso, non vago
- Rispondi in italiano
- Massimo 300 parole"""

            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": [
                    {"type": "text", "text": user_message or "Analizza questa immagine in dettaglio."},
                    {"type": "image_url", "image_url": {"url": data_uri, "detail": "high"}}
                ]}
            ]

            response = _get_client().chat.completions.create(
                model="gpt-4o",
                messages=messages,
                max_tokens=800
            )
            result = response.choices[0].message.content.strip()
            logger.info(f"[IMAGE_HANDLER] Vision OK for {filename}: {len(result)} chars")
            return result

        except Exception as e:
            logger.error(f"[IMAGE_HANDLER] Vision failed for {filename}: {e}")

    # STRATEGIA 2: Fallback OCR
    if has_text and ocr_text.strip():
        return f"Ho analizzato l'immagine '{filename}'. Contiene del testo:\n\n{ocr_text.strip()}"

    # STRATEGIA 3: Fallback generico (mai vuoto)
    return f"Ho ricevuto l'immagine '{filename}'. Non sono riuscito ad analizzarla visivamente in questo momento, ma il file è stato caricato correttamente."
