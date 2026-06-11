"""
FACEBOOK INTEGRATION - Genesi Core v2
Meta OAuth2 via Facebook Graph API.
Richiede: FACEBOOK_APP_ID, FACEBOOK_APP_SECRET nel .env
App Dashboard: https://developers.facebook.com/apps/
"""

import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx

from core.integrations.base_integration import BaseIntegration
from core.log import log


GRAPH_API = "https://graph.facebook.com/v19.0"
OAUTH_DIALOG = "https://www.facebook.com/v19.0/dialog/oauth"
TOKEN_URL = f"{GRAPH_API}/oauth/access_token"


class FacebookIntegration(BaseIntegration):
    platform = "facebook"
    display_name = "Facebook"
    icon = "📘"

    SCOPES = ["email", "public_profile", "pages_read_engagement"]

    def _app_id(self) -> Optional[str]:
        return os.getenv("FACEBOOK_APP_ID")

    def _app_secret(self) -> Optional[str]:
        return os.getenv("FACEBOOK_APP_SECRET")

    def _redirect_uri(self, base_url: str) -> str:
        return f"{base_url}/api/integrations/facebook/callback"

    async def get_auth_url(self, user_id: str, base_url: str = "") -> Optional[str]:
        app_id = self._app_id()
        # Facebook App IDs are strictly numeric (usually 15-16 digits).
        # Any text like "your_app_id" will fail this check and trigger OpenClaw.
        if not app_id or not app_id.strip().isdigit() or len(app_id.strip()) < 12 or app_id.strip() == "123456789":
            log("FACEBOOK_OAUTH_ERROR", error=f"FACEBOOK_APP_ID mancante o fittizio: {app_id}")
            return None
        params = {
            "client_id": app_id,
            "redirect_uri": self._redirect_uri(base_url),
            "scope": ",".join(self.SCOPES),
            "state": user_id,
            "response_type": "code",
        }
        return f"{OAUTH_DIALOG}?{urlencode(params)}"

    async def handle_callback(self, user_id: str, code: str, state: str = "") -> bool:
        base_url = os.getenv("BASE_URL", "http://localhost:8000")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(TOKEN_URL, params={
                    "client_id": self._app_id(),
                    "client_secret": self._app_secret(),
                    "redirect_uri": self._redirect_uri(base_url),
                    "code": code,
                })
                data = resp.json()
                access_token = data.get("access_token")
                if not access_token:
                    log("FACEBOOK_TOKEN_ERROR", error=data, user_id=user_id)
                    return False

                # Fetch profile info
                profile_resp = await client.get(f"{GRAPH_API}/me", params={
                    "fields": "id,name,email",
                    "access_token": access_token,
                })
                profile = profile_resp.json()

            await self.save_tokens(user_id, {
                "access_token": access_token,
                "expires_in": data.get("expires_in"),
                "scopes": self.SCOPES,
                "profile": profile,
            })
            log("FACEBOOK_OAUTH_SUCCESS", user_id=user_id, name=profile.get("name"))
            return True
        except Exception as e:
            log("FACEBOOK_CALLBACK_ERROR", error=str(e), user_id=user_id)
            return False

    async def get_status(self, user_id: str) -> Dict[str, Any]:
        connected = await self.is_connected(user_id)
        tokens = await self.load_tokens(user_id) or {}
        return {
            "platform": self.platform,
            "display_name": self.display_name,
            "icon": self.icon,
            "connected": connected,
            "profile": tokens.get("profile", {}),
            "connected_at": tokens.get("connected_at"),
        }

    async def disconnect(self, user_id: str) -> bool:
        tokens = await self.load_tokens(user_id)
        if tokens:
            try:
                access_token = tokens.get("access_token")
                user_fb_id = tokens.get("profile", {}).get("id")
                if access_token and user_fb_id:
                    async with httpx.AsyncClient(timeout=5) as client:
                        await client.delete(
                            f"{GRAPH_API}/{user_fb_id}/permissions",
                            params={"access_token": access_token},
                        )
            except Exception as e:
                log("FACEBOOK_REVOKE_ERROR", error=str(e), user_id=user_id)
        await self.clear_tokens(user_id)
        return True

    async def get_messages(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        # TODO: implementare lettura feed/messaggi via Graph API
        raise NotImplementedError("Facebook read: TODO — usa Graph API pages/feed")


facebook_integration = FacebookIntegration()
