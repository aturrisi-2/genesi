"""
ICLOUD INTEGRATION - Genesi Core v2
Integrazione Calendario/Promemoria Apple (iCloud CalDAV).
Non utilizza OAuth2. La connessione richiede le credenziali 
salvate nel profilo utente tramite il setup wizard (OpenClaw) o la modale dedicata.
"""

from typing import Any, Dict, Optional

from core.integrations.base_integration import BaseIntegration
from core.storage import storage
from core.log import log


class iCloudIntegration(BaseIntegration):
    platform = "icloud"
    display_name = "iCloud ID"
    icon = "☁️"

    async def is_connected(self, user_id: str) -> bool:
        # È considerato connesso se esistono icloud_user e icloud_password nel profilo
        profile = await storage.load(f"profile:{user_id}", default={})
        return bool(profile.get("icloud_user") and profile.get("icloud_password"))

    async def get_auth_url(self, user_id: str, base_url: str = "") -> Optional[str]:
        # Questa integrazione è gestita via chat (tramite setup_wizard e OpenClaw)
        # o tramite modale (processo 'pre openclaw'). Restituisce None per disabilitare il link OAuth.
        return None

    async def handle_callback(self, user_id: str, code: str, state: str = "") -> bool:
        return True

    async def get_status(self, user_id: str) -> Dict[str, Any]:
        connected = await self.is_connected(user_id)
        profile = await storage.load(f"profile:{user_id}", default={})
        return {
            "platform": self.platform,
            "display_name": self.display_name,
            "icon": self.icon,
            "connected": connected,
            "profile": {"email": profile.get("icloud_user")} if connected else {},
            "type": "oauth", # Appare come normale icona e bottone "Collega" in UI
            "note": "Gestito via chat (Setup Wizard)",
        }

    async def disconnect(self, user_id: str) -> bool:
        # Rimuovi dati iCloud dal profilo
        profile = await storage.load(f"profile:{user_id}", default={})
        if "icloud_user" in profile:
            del profile["icloud_user"]
        if "icloud_password" in profile:
            del profile["icloud_password"]
        await storage.save(f"profile:{user_id}", profile)
        log("ICLOUD_DISCONNECT", user_id=user_id)
        return True

icloud_integration = iCloudIntegration()
