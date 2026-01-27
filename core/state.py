from typing import Dict, List

from core.user import User
from memory.episodic import EpisodicEvent
from memory.select import select_relevant_events
from storage.users import load_user, create_user as create_storage_user

from core.relational.accumulator import relational_accumulator
from core.relational.character_state import CharacterState


class CognitiveState:
    """
    Stato cognitivo neutro di Genesi.
    Contiene ciò che sa, NON come risponde.
    """

    def __init__(
        self,
        user: User,
        recent_events: List[EpisodicEvent] = None,
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
        user = load_user(user_id) or create_storage_user()

        # 2. Eventi rilevanti
        recent_events = select_relevant_events(user_id, limit)

        # 3. Stato cognitivo base
        state = cls(
            user=user,
            recent_events=recent_events,
            context={}
        )

        # 4. Stato relazionale persistente
        relational_state = relational_accumulator.load(user_id)

        # 5. Carattere DERIVATO (non salvato)
        state.character = CharacterState().compute(relational_state)
        print("🧬 CHARACTER STATE:", state.character, flush=True)

        return state
