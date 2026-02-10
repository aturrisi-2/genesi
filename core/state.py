from typing import Dict, List

from core.user import User
from core.log import log
from core.user_manager import user_manager


class CognitiveState:
    """
    Stato cognitivo neutro di Genesi.
    Contiene ciò che sa, NON come risponde.
    """

    def __init__(
        self,
        user: User,
        recent_events: List = None,
        context: Dict = None,
    ):
        self.user = user
        self.recent_events = recent_events or []
        self.context = context or {}

        # 🔒 attributi derivati (mai persistiti)
        self.character = None

    @classmethod
    def build(cls, user_id: str, limit: int = 10) -> "CognitiveState":
        # 1. Utente
        user_data = user_manager.get_user(user_id)
        if user_data:
            user = User(user_id=user_id)
            log("USER_SESSION", user_id=user_id, status="existing")
        else:
            user_data = user_manager.create_user(user_id)
            user = User(user_id=user_id)
            log("USER_SESSION", user_id=user.user_id, status="created")

        # 2. Eventi rilevanti (disabilitati per ora)
        recent_events = []

        # 3. Stato cognitivo base
        state = cls(
            user=user,
            recent_events=recent_events,
            context={}
        )

        return state
