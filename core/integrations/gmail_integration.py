"""
GMAIL INTEGRATION - Genesi Core v2
Google OAuth2 per lettura e invio email via Gmail API.
Riusa google_auth_oauthlib già presente nel progetto.
"""

import base64
import json
import os
from email.mime.text import MIMEText
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

    def _get_client_config(self) -> Dict[str, str]:
        """Legge client_id e client_secret dal credentials.json."""
        path = self._get_credentials_path()
        if not os.path.exists(path):
            return {}
        with open(path) as f:
            data = json.load(f)
        # Supporta sia "installed" che "web"
        section = data.get("installed") or data.get("web") or {}
        return {
            "client_id": section.get("client_id", ""),
            "client_secret": section.get("client_secret", ""),
            "token_uri": section.get("token_uri", "https://oauth2.googleapis.com/token"),
        }

    async def _build_service(self, user_id: str):
        """
        Costruisce il service object Gmail API per l'utente.
        Gestisce il refresh automatico del token se scaduto.
        Ritorna (service, tokens_updated) oppure (None, False) in caso di errore.
        """
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        tokens = await self.load_tokens(user_id)
        if not tokens or not tokens.get("access_token"):
            return None, False

        cfg = self._get_client_config()
        creds = Credentials(
            token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token"),
            token_uri=cfg.get("token_uri", "https://oauth2.googleapis.com/token"),
            client_id=cfg.get("client_id", ""),
            client_secret=cfg.get("client_secret", ""),
            scopes=self.SCOPES,
        )

        tokens_updated = False
        if creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                await self.save_tokens(user_id, {
                    "access_token": creds.token,
                    "refresh_token": creds.refresh_token,
                    "expires_at": creds.expiry.isoformat() if creds.expiry else None,
                    "scopes": list(creds.scopes or self.SCOPES),
                    "profile": tokens.get("profile", {}),
                })
                tokens_updated = True
                log("GMAIL_TOKEN_REFRESHED", user_id=user_id)
            except Exception as e:
                log("GMAIL_TOKEN_REFRESH_ERROR", user_id=user_id, error=str(e))
                return None, False

        service = build("gmail", "v1", credentials=creds)
        return service, tokens_updated

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

    # ─── Gmail API ────────────────────────────────────────────────────────────

    async def get_messages(
        self,
        user_id: str,
        limit: int = 5,
        query: str = "",
    ) -> List[Dict[str, Any]]:
        """
        Legge le ultime email dall'inbox via Gmail API.
        `query` è un filtro Gmail opzionale (es. "is:unread", "is:starred").
        """
        service, _ = await self._build_service(user_id)
        if not service:
            raise ValueError("Gmail non collegato — usa 'configurare gmail' prima")

        # Lista messaggi
        list_kwargs: Dict[str, Any] = {
            "userId": "me",
            "maxResults": limit,
            "labelIds": ["INBOX"],
        }
        if query:
            list_kwargs["q"] = query

        result = service.users().messages().list(**list_kwargs).execute()
        msg_refs = result.get("messages", [])

        emails = []
        for ref in msg_refs:
            msg = service.users().messages().get(
                userId="me",
                id=ref["id"],
                format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = {
                h["name"]: h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            emails.append({
                "id": ref["id"],
                "from": headers.get("From", ""),
                "subject": headers.get("Subject", "(senza oggetto)"),
                "date": headers.get("Date", ""),
                "snippet": msg.get("snippet", "")[:200],
                "unread": "UNREAD" in msg.get("labelIds", []),
            })

        log("GMAIL_READ_OK", user_id=user_id, count=len(emails))
        return emails

    async def send_message(
        self,
        user_id: str,
        to: str,
        text: str,
        subject: str = "(nessun oggetto)",
    ) -> bool:
        """
        Invia un'email via Gmail API.
        `to` = indirizzo destinatario, `text` = corpo (plain text), `subject` = oggetto.
        """
        service, _ = await self._build_service(user_id)
        if not service:
            raise ValueError("Gmail non collegato — usa 'configurare gmail' prima")

        mime = MIMEText(text)
        mime["to"] = to
        mime["subject"] = subject
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()

        service.users().messages().send(
            userId="me",
            body={"raw": raw},
        ).execute()
        log("GMAIL_SEND_OK", user_id=user_id, to=to, subject=subject)
        return True


gmail_integration = GmailIntegration()
