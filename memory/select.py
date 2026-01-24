from typing import List
from .episodic import EpisodicEvent, load_events

def select_relevant_events(user_id: str, limit: int = 10) -> List[EpisodicEvent]:
    events = load_events(user_id)
    sorted_events = sorted(
        events,
        key=lambda e: (e.salience, e.timestamp),
        reverse=True
    )
    return sorted_events[:limit]