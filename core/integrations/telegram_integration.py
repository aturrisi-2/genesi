"""
TELEGRAM INTEGRATION - Genesi Core v2
Bot API bidirezionale: Genesi risponde ai messaggi ricevuti sul bot Telegram.
Usa TELEGRAM_BOT_TOKEN da env (no OAuth necessario).
Webhook: POST /api/integrations/telegram/webhook (endpoint pubblico)

ISOLAMENTO UTENTI:
  Ogni utente Genesi ha il proprio chat_id Telegram collegato.
  Storage bidirezionale:
    - integration:telegram:{user_id}          → token + chat_id (forward: user → chat)
    - integration:telegram_link:{chat_id}     → {user_id}      (reverse: chat → user)
    - integration:telegram_pending:{token}    → {user_id}      (token temporaneo di linking)
  Il webhook risolve sempre chat_id → user_id prima di elaborare qualsiasi messaggio.
"""

import os
import secrets
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import httpx

from core.integrations.base_integration import BaseIntegration
from core.log import log
from core.storage import storage


TELEGRAM_API = "https://api.telegram.org"


class TelegramIntegration(BaseIntegration):
    platform = "telegram"
    display_name = "Telegram"
    icon = "✈️"

    def _bot_token(self) -> Optional[str]:
        return os.getenv("TELEGRAM_BOT_TOKEN")

    def _api_url(self, method: str) -> str:
        return f"{TELEGRAM_API}/bot{self._bot_token()}/{method}"

    async def is_connected(self, user_id: str) -> bool:
        return bool(self._bot_token())

    async def get_auth_url(self, user_id: str, base_url: str = "") -> Optional[str]:
        # Telegram non usa OAuth: si configura tramite TELEGRAM_BOT_TOKEN
        return None

    async def handle_callback(self, user_id: str, code: str, state: str = "") -> bool:
        # Nessun callback OAuth per Telegram
        return bool(self._bot_token())

    async def get_status(self, user_id: str) -> Dict[str, Any]:
        token = self._bot_token()
        if not token:
            return {
                "platform": self.platform,
                "display_name": self.display_name,
                "icon": self.icon,
                "connected": False,
                "linked": False,
                "note": "Imposta TELEGRAM_BOT_TOKEN nel file .env",
            }
        chat_id = await self.get_chat_id_for_user(user_id)
        linked = bool(chat_id)
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(self._api_url("getMe"))
                data = resp.json()
                bot_info = data.get("result", {})
            return {
                "platform": self.platform,
                "display_name": self.display_name,
                "icon": self.icon,
                "connected": True,
                "linked": linked,
                "chat_id": chat_id,
                "bot_username": bot_info.get("username"),
                "bot_name": bot_info.get("first_name"),
            }
        except Exception as e:
            log("TELEGRAM_STATUS_ERROR", error=str(e))
            return {
                "platform": self.platform,
                "connected": True,
                "linked": linked,
                "chat_id": chat_id,
            }

    async def disconnect(self, user_id: str) -> bool:
        await self.unlink_user(user_id)
        return True

    # ─── Linking bidirezionale user_id ↔ chat_id ────────────────────────────

    async def generate_link_token(self, user_id: str) -> str:
        """
        Genera un token temporaneo per collegare l'account Genesi al bot Telegram.
        L'utente deve inviare al bot: /start {token}
        Il token scade automaticamente quando viene usato (one-shot).
        """
        token = secrets.token_hex(16)
        await storage.save(f"integration:telegram_pending:{token}", {
            "user_id": user_id,
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        log("TELEGRAM_LINK_TOKEN_CREATED", user_id=user_id)
        return token

    async def resolve_link_token(self, token: str) -> Optional[str]:
        """
        Risolve il token di linking → ritorna lo user_id Genesi.
        Il token viene cancellato dopo l'uso (one-shot, anti-replay).
        """
        data = await storage.load(f"integration:telegram_pending:{token}", default=None)
        if data:
            await storage.delete(f"integration:telegram_pending:{token}")
            return data.get("user_id")
        return None

    async def save_chat_binding(self, user_id: str, chat_id: str) -> None:
        """
        Salva il binding bidirezionale user_id ↔ chat_id.
        Garantisce che ogni utente Genesi sia collegato a un solo chat_id Telegram
        e che ogni chat_id sia collegato a un solo utente Genesi.
        """
        # Se questo chat_id era già associato a un altro utente, rimuovi il vecchio binding
        existing_user = await self.get_user_id_for_chat(chat_id)
        if existing_user and existing_user != user_id:
            old_tokens = await self.load_tokens(existing_user) or {}
            old_tokens.pop("chat_id", None)
            await storage.save(f"integration:{self.platform}:{existing_user}", old_tokens)
            log("TELEGRAM_BINDING_REPLACED", old_user=existing_user, new_user=user_id, chat_id=chat_id)

        # Forward: user_id → chat_id (nel token dell'utente)
        tokens = await self.load_tokens(user_id) or {}
        tokens["chat_id"] = chat_id
        tokens["connected_at"] = datetime.now(timezone.utc).isoformat()
        await storage.save(f"integration:{self.platform}:{user_id}", tokens)

        # Reverse: chat_id → user_id (lookup veloce nel webhook)
        await storage.save(f"integration:telegram_link:{chat_id}", {
            "user_id": user_id,
            "linked_at": datetime.now(timezone.utc).isoformat(),
        })
        log("TELEGRAM_CHAT_BOUND", user_id=user_id, chat_id=chat_id)

    async def get_user_id_for_chat(self, chat_id: str) -> Optional[str]:
        """Ritorna lo user_id Genesi dato un chat_id Telegram (reverse lookup)."""
        data = await storage.load(f"integration:telegram_link:{chat_id}", default=None)
        return data.get("user_id") if data else None

    async def get_chat_id_for_user(self, user_id: str) -> Optional[str]:
        """Ritorna il chat_id Telegram dato uno user_id Genesi (forward lookup)."""
        tokens = await self.load_tokens(user_id)
        return tokens.get("chat_id") if tokens else None

    async def unlink_user(self, user_id: str) -> None:
        """Rimuove il binding bidirezionale per un utente."""
        chat_id = await self.get_chat_id_for_user(user_id)
        if chat_id:
            await storage.delete(f"integration:telegram_link:{chat_id}")
        await self.clear_tokens(user_id)
        log("TELEGRAM_UNLINKED", user_id=user_id)

    # ─── Bot API ─────────────────────────────────────────────────────────────

    async def set_webhook(self, webhook_url: str) -> bool:
        """Registra il webhook presso Telegram. Chiama una volta all'avvio."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    self._api_url("setWebhook"),
                    json={"url": webhook_url, "drop_pending_updates": True},
                )
                result = resp.json()
                ok = result.get("ok", False)
                log("TELEGRAM_WEBHOOK_SET", ok=ok, url=webhook_url)
                return ok
        except Exception as e:
            log("TELEGRAM_WEBHOOK_ERROR", error=str(e))
            return False

    async def send_message(self, user_id: str, to: str, text: str) -> bool:
        """
        Invia un messaggio a un chat_id Telegram.
        `to` = chat_id (stringa numerica o username @nome).
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    self._api_url("sendMessage"),
                    json={"chat_id": to, "text": text, "parse_mode": "Markdown"},
                )
                ok = resp.json().get("ok", False)
                log("TELEGRAM_SEND", to=to, ok=ok)
                return ok
        except Exception as e:
            log("TELEGRAM_SEND_ERROR", error=str(e), to=to)
            return False

    def handle_update(self, update: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Parsa un update dal webhook Telegram.
        Ritorna {"chat_id": str, "text": str, "from": {...}} oppure None.
        """
        try:
            message = update.get("message") or update.get("edited_message")
            if not message:
                return None
            chat_id = str(message["chat"]["id"])
            text = message.get("text", "")
            from_user = message.get("from", {})
            return {"chat_id": chat_id, "text": text, "from": from_user}
        except Exception as e:
            log("TELEGRAM_PARSE_UPDATE_ERROR", error=str(e))
            return None

    async def get_messages(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        # I messaggi arrivano via webhook — non c'è polling implementato
        raise NotImplementedError("Telegram: usa il webhook per ricevere messaggi in tempo reale")


telegram_integration = TelegramIntegration()
