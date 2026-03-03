"""
WHATSAPP INTEGRATION - Genesi Core v2
Wrapper su OpenClaw (già integrato): usa openclaw per inviare messaggi WhatsApp.
Non richiede setup OAuth aggiuntivo.
"""

from typing import Any, Dict, List, Optional

from core.integrations.base_integration import BaseIntegration
from core.log import log


class WhatsAppIntegration(BaseIntegration):
    platform = "whatsapp"
    display_name = "WhatsApp"
    icon = "💬"

    async def is_connected(self, user_id: str) -> bool:
        try:
            from core.openclaw_service import openclaw_service
            return openclaw_service is not None
        except Exception:
            return False

    async def get_auth_url(self, user_id: str, base_url: str = "") -> Optional[str]:
        # Nessun OAuth: delegato a OpenClaw
        return None

    async def handle_callback(self, user_id: str, code: str, state: str = "") -> bool:
        return True

    async def get_status(self, user_id: str) -> Dict[str, Any]:
        connected = await self.is_connected(user_id)
        return {
            "platform": self.platform,
            "display_name": self.display_name,
            "icon": self.icon,
            "connected": connected,
            "provider": "openclaw",
            "note": "Invio messaggi delegato a OpenClaw (PC automation)",
        }

    async def disconnect(self, user_id: str) -> bool:
        log("WHATSAPP_DISCONNECT_NOTE", note="WhatsApp usa OpenClaw — nessun token da revocare")
        return True

    async def send_message(self, user_id: str, to: str, text: str) -> bool:
        """
        Invia un messaggio WhatsApp tramite OpenClaw.
        `to` = nome contatto o numero.
        """
        try:
            from core.openclaw_service import openclaw_service
            prompt = f"Invia un messaggio WhatsApp a {to}: {text}"
            result = await openclaw_service.execute_task(user_id, prompt)
            success = bool(result) and "errore" not in result.lower()
            log("WHATSAPP_SEND", to=to, success=success, user_id=user_id)
            return success
        except Exception as e:
            log("WHATSAPP_SEND_ERROR", error=str(e), to=to)
            return False

    async def get_messages(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        # La lettura di messaggi WhatsApp richiederebbe WhatsApp Business API
        raise NotImplementedError("WhatsApp read: richiede WhatsApp Business API (non ancora implementato)")


whatsapp_integration = WhatsAppIntegration()
