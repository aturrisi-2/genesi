# core/user.py

from datetime import datetime
from typing import Dict


class User:
    def __init__(
        self,
        user_id: str,
        created_at: str | None = None,
        last_seen: str | None = None,
        profile: Dict | None = None
    ):
        self.user_id = user_id
        self.created_at = created_at or datetime.utcnow().isoformat()
        self.last_seen = last_seen or self.created_at

        # 🔒 UNICA FONTE DI IDENTITÀ
        self.profile: Dict = profile if profile is not None else {}

    def touch(self):
        """Aggiorna l'ultima interazione."""
        self.last_seen = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict:
        """Serializzazione COMPLETA (usata da storage)."""
        return {
            "user_id": self.user_id,
            "created_at": self.created_at,
            "last_seen": self.last_seen,
            "profile": self.profile
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "User":
        """Ricostruzione sicura da storage."""
        return cls(
            user_id=data["user_id"],
            created_at=data.get("created_at"),
            last_seen=data.get("last_seen"),
            profile=data.get("profile", {})
        )
