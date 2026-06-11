"""
GOOGLE CALENDAR INTEGRATION - Genesi Core v2
Adapter che riusa i token OAuth già salvati da api/calendar_auth.py
(chiave: profile:{user_id} → google_token).
NON duplica il flusso OAuth — punta alla route esistente /api/calendar/google/login.
"""

from typing import Any, Dict, List, Optional

from core.integrations.base_integration import BaseIntegration
from core.log import log
from core.storage import storage


class GoogleCalendarIntegration(BaseIntegration):
    platform = "google_calendar"
    display_name = "Google Calendar"
    icon = "📅"

    async def is_connected(self, user_id: str) -> bool:
        profile = await storage.load(f"profile:{user_id}", default={})
        return bool(profile.get("google_token"))

    async def get_auth_url(self, user_id: str, base_url: str = "") -> Optional[str]:
        # OAuth già gestito da /api/calendar/google/login
        return f"{base_url}/api/calendar/google/login"

    async def handle_callback(self, user_id: str, code: str, state: str = "") -> bool:
        # Callback già gestito da /api/calendar/google/callback
        return True

    async def get_status(self, user_id: str) -> Dict[str, Any]:
        profile = await storage.load(f"profile:{user_id}", default={})
        token = profile.get("google_token")
        connected = bool(token)
        return {
            "platform": self.platform,
            "display_name": self.display_name,
            "icon": self.icon,
            "connected": connected,
            "auth_route": "/api/calendar/google/login",
            "note": "OAuth gestito da /api/calendar/google/login",
        }

    async def disconnect(self, user_id: str) -> bool:
        profile = await storage.load(f"profile:{user_id}", default={})
        if "google_token" in profile:
            del profile["google_token"]
            await storage.save(f"profile:{user_id}", profile)
            log("GOOGLE_CALENDAR_DISCONNECTED", user_id=user_id)
        return True

    async def get_events(self, user_id: str, days_ahead: int = 7) -> List[Dict[str, Any]]:
        # TODO: implementare con googleapiclient.discovery build('calendar','v3')
        raise NotImplementedError("Google Calendar read: TODO — usa googleapiclient")


google_calendar_integration = GoogleCalendarIntegration()
