import os
import logging
import httpx

logger = logging.getLogger(__name__)

OPENCLAW_URL = "http://127.0.0.1:18789"

class OpenClawService:
    def __init__(self):
        # We try to get the token from environment or use the known one if not set
        self.token = os.environ.get("OPENCLAW_GATEWAY_TOKEN", "92bb8a1e31bff7999729acb13b3ad866f53a7c4fe39366ff")
        self.client = httpx.AsyncClient(timeout=60.0)

    async def execute_task(self, user_id: str, prompt: str) -> str:
        """
        Invia un prompt ad OpenClaw e ritorna la risposta una volta terminato il task.
        """
        try:
            logger.info("OPENCLAW_EXECUTE_START user=%s prompt=%.50s...", user_id, prompt)
            
            # Use the /api/v1/messages/sync endpoint to wait for the completion
            # or the appropriate endpoint to trigger an agent task.
            headers = {
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            }
            payload = {
                "message": prompt,
                "agent": "main",
                "session": f"genesi_{user_id}"
            }
            
            # The API endpoint for a raw chat completion or message
            # Typically POST /api/v1/sessions/main/messages
            # As this is a CLI / API, the most standard is /api/v1/messages sent to a session.
            response = await self.client.post(
                f"{OPENCLAW_URL}/api/v1/messages",
                headers=headers,
                json=payload
            )
            
            if response.status_code == 200:
                data = response.json()
                logger.info("OPENCLAW_EXECUTE_SUCCESS user=%s payload_size=%d", user_id, len(str(data)))
                # Extract the text response
                text_response = data.get("text") or data.get("response", "Comando inviato ed eseguito correttamente con OpenClaw.")
                return text_response
            else:
                logger.error("OPENCLAW_EXECUTE_ERROR user=%s status=%d text=%s", user_id, response.status_code, response.text)
                return "Mi dispiace, ma non riesco a collegarmi al mio braccio robotico (OpenClaw) per eseguire questa operazione. Verifica i log."
                
        except Exception as e:
            logger.error("OPENCLAW_EXECUTE_EXCEPTION user=%s error=%s", user_id, str(e), exc_info=True)
            return f"Si è verificato un errore durante l'esecuzione dell'azione con OpenClaw: {str(e)}"

# Singleton instance
openclaw_service = OpenClawService()
