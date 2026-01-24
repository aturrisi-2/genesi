import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

class EpisodicEvent:
    def __init__(self, event_id: str, user_id: str, timestamp: str, 
                 type: str, content: Dict[str, Any], salience: float):
        self.event_id = event_id
        self.user_id = user_id
        self.timestamp = timestamp
        self.type = type
        self.content = content
        self.salience = salience

    def to_dict(self) -> Dict[str, Any]:
        return {
            'event_id': self.event_id,
            'user_id': self.user_id,
            'timestamp': self.timestamp,
            'type': self.type,
            'content': self.content,
            'salience': self.salience
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EpisodicEvent':
        return cls(
            event_id=data['event_id'],
            user_id=data['user_id'],
            timestamp=data['timestamp'],
            type=data['type'],
            content=data['content'],
            salience=data['salience']
        )

def _get_user_events_path(user_id: str) -> Path:
    base_dir = Path('data/memory/episodic')
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / f'{user_id}.json'

def store_event(user_id: str, type: str, content: Dict[str, Any], salience: float) -> EpisodicEvent:
    event = EpisodicEvent(
        event_id=str(uuid.uuid4()),
        user_id=user_id,
        timestamp=datetime.utcnow().isoformat(),
        type=type,
        content=content,
        salience=salience
    )
    
    file_path = _get_user_events_path(user_id)
    events = []
    
    if file_path.exists():
        with open(file_path, 'r') as f:
            events = json.load(f)
    
    events.append(event.to_dict())
    
    with open(file_path, 'w') as f:
        json.dump(events, f, indent=2)
    
    return event

def load_events(user_id: str) -> List[EpisodicEvent]:
    file_path = _get_user_events_path(user_id)
    
    if not file_path.exists():
        return []
    
    with open(file_path, 'r') as f:
        events_data = json.load(f)
    
    return [EpisodicEvent.from_dict(event_data) for event_data in events_data]