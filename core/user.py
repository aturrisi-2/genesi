from datetime import datetime
from typing import Dict, Any

class User:
    def __init__(self, user_id: str, created_at: str = None, last_seen: str = None, profile: Dict[str, Any] = None):
        self.user_id = user_id
        self.created_at = created_at or datetime.utcnow().isoformat()
        self.last_seen = last_seen or self.created_at
        self.profile = profile or {}

    def touch(self) -> None:
        self.last_seen = datetime.utcnow().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        return {
            'user_id': self.user_id,
            'created_at': self.created_at,
            'last_seen': self.last_seen,
            'profile': self.profile
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'User':
        return cls(
            user_id=data['user_id'],
            created_at=data.get('created_at'),
            last_seen=data.get('last_seen'),
            profile=data.get('profile', {})
        )