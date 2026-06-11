"""
BASE INTEGRATION - Genesi Core v2
Classe astratta per tutte le integrazioni esterne (Gmail, Telegram, Facebook, ecc.)
Pattern: ogni integrazione implementa auth, status, get_messages, send_message.
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from core.log import log
from core.storage import storage


class BaseIntegration(ABC):
    """
    Classe base per le integrazioni esterne.
    Storage key: integration:{platform}:{user_id}
    """

    platform: str = ""
    display_name: str = ""
    icon: str = ""

    # ─── Token storage ──────────────────────────────────────────────────────

    async def save_tokens(self, user_id: str, tokens: Dict[str, Any]) -> None:
        tokens["connected_at"] = datetime.now(timezone.utc).isoformat()
        await storage.save(f"integration:{self.platform}:{user_id}", tokens)
        log("INTEGRATION_TOKENS_SAVED", platform=self.platform, user_id=user_id)

    async def load_tokens(self, user_id: str) -> Optional[Dict[str, Any]]:
        return await storage.load(f"integration:{self.platform}:{user_id}", default=None)

    async def clear_tokens(self, user_id: str) -> None:
        await storage.delete(f"integration:{self.platform}:{user_id}")
        log("INTEGRATION_TOKENS_CLEARED", platform=self.platform, user_id=user_id)

    async def is_connected(self, user_id: str) -> bool:
        tokens = await self.load_tokens(user_id)
        return tokens is not None

    # ─── Metodi astratti (obbligatori) ──────────────────────────────────────

    @abstractmethod
    async def get_auth_url(self, user_id: str, base_url: str = "") -> Optional[str]:
        """
        Ritorna l'URL OAuth per avviare il flusso di autenticazione.
        Ritorna None se la piattaforma non usa OAuth (es. Telegram bot token).
        """

    @abstractmethod
    async def handle_callback(self, user_id: str, code: str, state: str = "") -> bool:
        """
        Gestisce il callback OAuth: scambia il codice per i token e li salva.
        Ritorna True se il collegamento è andato a buon fine.
        """

    @abstractmethod
    async def get_status(self, user_id: str) -> Dict[str, Any]:
        """
        Ritorna lo stato della connessione e le informazioni sul profilo collegato.
        Formato: {"connected": bool, "platform": str, "profile": {...}, ...}
        """

    @abstractmethod
    async def disconnect(self, user_id: str) -> bool:
        """
        Revoca i token e pulisce lo storage. Ritorna True se l'operazione è riuscita.
        """

    # ─── Metodi opzionali (override nelle sottoclassi) ──────────────────────

    async def get_messages(self, user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        raise NotImplementedError(f"{self.display_name}: lettura messaggi non ancora implementata")

    async def send_message(self, user_id: str, to: str, text: str) -> bool:
        raise NotImplementedError(f"{self.display_name}: invio messaggi non ancora implementato")

    async def get_events(self, user_id: str, days_ahead: int = 7) -> List[Dict[str, Any]]:
        raise NotImplementedError(f"{self.display_name}: lettura eventi non ancora implementata")

    # ─── Helper di risposta standard ────────────────────────────────────────

    def _not_connected_msg(self) -> str:
        return (
            f"{self.icon} {self.display_name} non è ancora collegato. "
            f"Vai in Impostazioni → Integrazioni → {self.display_name} per collegare il tuo account."
        )
