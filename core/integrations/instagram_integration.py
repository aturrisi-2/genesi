"""
INSTAGRAM INTEGRATION - Genesi Core v2
Adapter su Facebook: Instagram Basic Display API o Business via Facebook Pages.
Stessa app Meta, stesso flusso OAuth — riusa i token di facebook_integration.
Richiede scope aggiuntivo: instagram_basic, instagram_content_publish
"""

from typing import Any, Dict, List, Optional

from core.integrations.base_integration import BaseIntegration
from core.integrations.facebook_integration import facebook_integration
from core.log import log


class InstagramIntegration(BaseIntegration):
    platform = "instagram"
    display_name = "Instagram"
    icon = "📸"

    async def is_connected(self, user_id: str) -> bool:
        # Connesso se abbiamo i token Facebook (stesso flow)
        return await facebook_integration.is_connected(user_id)

    async def get_auth_url(self, user_id: str, base_url: str = "") -> Optional[str]:
        # Riusa il flusso OAuth Facebook con scope Instagram aggiuntivi
        # TODO: aggiungere "instagram_basic" agli scope Facebook quando si attiva IG
        return await facebook_integration.get_auth_url(user_id, base_url)

    async def handle_callback(self, user_id: str, code: str, state: str = "") -> bool:
        return await facebook_integration.handle_callback(user_id, code, state)

    async def get_status(self, user_id: str) -> Dict[str, Any]:
        fb_status = await facebook_integration.get_status(user_id)
        return {
            "platform": self.platform,
            "display_name": self.display_name,
            "icon": self.icon,
            "connected": fb_status.get("connected", False),
            "note": "Usa le credenziali Facebook (stessa app Meta)",
            "facebook_profile": fb_status.get("profile", {}),
        }

    async def disconnect(self, user_id: str) -> bool:
        # Non disconnette Facebook — solo nota
        log("INSTAGRAM_DISCONNECT_NOTE", note="Instagram condivide i token con Facebook")
        return True

    async def get_messages(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        # TODO: Graph API /me/media per lettura post/media
        raise NotImplementedError("Instagram read: TODO — usa Graph API /me/media")

    async def send_message(self, user_id: str, to: str, text: str) -> bool:
        # TODO: Instagram Messaging API (richiede Instagram Business + Review)
        raise NotImplementedError("Instagram send: TODO — Instagram Messaging API")


instagram_integration = InstagramIntegration()
