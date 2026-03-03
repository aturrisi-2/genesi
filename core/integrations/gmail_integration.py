"""
GMAIL INTEGRATION - Genesi Core v2
Google OAuth2 per lettura e invio email via Gmail API.
Riusa google_auth_oauthlib già presente nel progetto.
"""

import os
from typing import Any, Dict, List, Optional

from core.integrations.base_integration import BaseIntegration
from core.log import log


class GmailIntegration(BaseIntegration):
    platform = "gmail"
    display_name = "Gmail"
    icon = "📧"

    SCOPES = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
    ]

    def _get_credentials_path(self) -> str:
        return os.getenv("GOOGLE_CREDENTIALS_PATH", "data/calendar/credentials.json")

    def _get_redirect_uri(self, base_url: str) -> str:
        # Riusa il redirect URI del Calendar (già registrato in Google Cloud Console)
        return f"{base_url}/api/calendar/google/callback"

    async def get_auth_url(self, user_id: str, base_url: str = "") -> Optional[str]:
        credentials_path = self._get_credentials_path()
        if not os.path.exists(credentials_path):
            log("GMAIL_OAUTH_ERROR", error="credentials_missing", path=credentials_path)
            return None

        try:
            from google_auth_oauthlib.flow import Flow
            flow = Flow.from_client_secrets_file(
                credentials_path,
                scopes=self.SCOPES,
                redirect_uri=self._get_redirect_uri(base_url),
            )
            auth_url, _ = flow.authorization_url(
                access_type="offline",
                prompt="consent",
                # Encode platform in state so calendar callback knows what to save
                state=f"{user_id}|gmail",
            )
            return auth_url
        except Exception as e:
            log("GMAIL_AUTH_URL_ERROR", error=str(e), user_id=user_id)
            return None

    async def handle_callback(self, user_id: str, code: str, state: str = "") -> bool:
        # Gestito direttamente da api/calendar_auth.py (stesso redirect URI)
        # Questo metodo non viene invocato nel flusso Gmail normale
        credentials_path = self._get_credentials_path()
        base_url = os.getenv("BASE_URL", "http://localhost:8000")
        try:
            from google_auth_oauthlib.flow import Flow

            flow = Flow.from_client_secrets_file(
                credentials_path,
                scopes=self.SCOPES,
                redirect_uri=self._get_redirect_uri(base_url),
            )
            flow.fetch_token(code=code)
            creds = flow.credentials

            await self.save_tokens(user_id, {
                "access_token": creds.token,
                "refresh_token": creds.refresh_token,
                "expires_at": creds.expiry.isoformat() if creds.expiry else None,
                "scopes": list(creds.scopes or self.SCOPES),
                "profile": {},
            })
            log("GMAIL_OAUTH_SUCCESS", user_id=user_id)
            return True
        except Exception as e:
            log("GMAIL_CALLBACK_ERROR", error=str(e), user_id=user_id)
            return False

    async def get_status(self, user_id: str) -> Dict[str, Any]:
        connected = await self.is_connected(user_id)
        tokens = await self.load_tokens(user_id) or {}
        return {
            "platform": self.platform,
            "display_name": self.display_name,
            "icon": self.icon,
            "connected": connected,
            "scopes": tokens.get("scopes", []),
            "connected_at": tokens.get("connected_at"),
            "profile": tokens.get("profile", {}),
        }

    async def disconnect(self, user_id: str) -> bool:
        await self.clear_tokens(user_id)
        return True

    async def get_messages(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        # TODO: implementare con googleapiclient.discovery build('gmail','v1')
        raise NotImplementedError("Gmail read: TODO — usa googleapiclient")

    async def send_message(self, user_id: str, to: str, text: str) -> bool:
        # TODO: implementare con gmail.users().messages().send()
        raise NotImplementedError("Gmail send: TODO — usa googleapiclient")


gmail_integration = GmailIntegration()
