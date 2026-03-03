"""
TIKTOK INTEGRATION - Genesi Core v2
TikTok Login Kit + Content API OAuth2.
Richiede: TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET nel .env
App Dashboard: https://developers.tiktok.com/
"""

import os
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx

from core.integrations.base_integration import BaseIntegration
from core.log import log


TIKTOK_AUTH_URL = "https://www.tiktok.com/v2/auth/authorize/"
TIKTOK_TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
TIKTOK_API = "https://open.tiktokapis.com/v2"


class TikTokIntegration(BaseIntegration):
    platform = "tiktok"
    display_name = "TikTok"
    icon = "🎵"

    SCOPES = ["user.info.basic", "video.list"]

    def _client_key(self) -> Optional[str]:
        return os.getenv("TIKTOK_CLIENT_KEY")

    def _client_secret(self) -> Optional[str]:
        return os.getenv("TIKTOK_CLIENT_SECRET")

    def _redirect_uri(self, base_url: str) -> str:
        return f"{base_url}/api/integrations/tiktok/callback"

    async def get_auth_url(self, user_id: str, base_url: str = "") -> Optional[str]:
        client_key = self._client_key()
        if not client_key or client_key == "IL_TUO_CLIENT_KEY" or client_key == "your_client_key":
            log("TIKTOK_OAUTH_ERROR", error="TIKTOK_CLIENT_KEY mancante o fittizio")
            return None
        import secrets
        csrf_state = f"{user_id}:{secrets.token_hex(8)}"
        params = {
            "client_key": client_key,
            "scope": ",".join(self.SCOPES),
            "response_type": "code",
            "redirect_uri": self._redirect_uri(base_url),
            "state": csrf_state,
        }
        return f"{TIKTOK_AUTH_URL}?{urlencode(params)}"

    async def handle_callback(self, user_id: str, code: str, state: str = "") -> bool:
        base_url = os.getenv("BASE_URL", "http://localhost:8000")
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(TIKTOK_TOKEN_URL, data={
                    "client_key": self._client_key(),
                    "client_secret": self._client_secret(),
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": self._redirect_uri(base_url),
                })
                data = resp.json()
                access_token = data.get("access_token")
                if not access_token:
                    log("TIKTOK_TOKEN_ERROR", error=data, user_id=user_id)
                    return False

            await self.save_tokens(user_id, {
                "access_token": access_token,
                "refresh_token": data.get("refresh_token"),
                "expires_in": data.get("expires_in"),
                "open_id": data.get("open_id"),
                "scopes": self.SCOPES,
                "profile": {"open_id": data.get("open_id")},
            })
            log("TIKTOK_OAUTH_SUCCESS", user_id=user_id, open_id=data.get("open_id"))
            return True
        except Exception as e:
            log("TIKTOK_CALLBACK_ERROR", error=str(e), user_id=user_id)
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
        # TODO: revoca token tramite TikTok API se necessario
        await self.clear_tokens(user_id)
        return True

    async def get_messages(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        # TODO: TikTok non ha API messaggi pubbliche — solo video list
        raise NotImplementedError("TikTok: solo video list disponibile, no messaggi privati")


tiktok_integration = TikTokIntegration()
