from typing import Dict, List

from core.user import User
from memory.episodic import EpisodicEvent
from memory.select import select_relevant_events
from storage.users import load_user, create_user as create_storage_user

class CognitiveState:
    def __init__(self, user: User, recent_events: List[EpisodicEvent] = None, context: Dict = None):
        self.user = user
        self.recent_events = recent_events or []
        self.context = context or {}

    @classmethod
    def build(cls, user_id: str, limit: int = 10) -> 'CognitiveState':
        user = load_user(user_id) or create_storage_user()
        recent_events = select_relevant_events(user_id, limit)
        return cls(user=user, recent_events=recent_events)