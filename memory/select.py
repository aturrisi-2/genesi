from datetime import datetime
from typing import List
from .episodic import EpisodicEvent, load_events
from .decay import apply_affect_decay

def select_relevant_events(user_id: str, limit: int = 10) -> List[EpisodicEvent]:
    events = load_events(user_id)
    now = datetime.utcnow()

    for event in events:
        try:
            decayed = apply_affect_decay(event, now)
            if isinstance(decayed, dict):
                # Convert dict to float (mean of numeric values) for downstream compatibility
                numeric_vals = [v for v in decayed.values() if isinstance(v, (int, float))]
                event.decayed_affect = sum(numeric_vals) / len(numeric_vals) if numeric_vals else 0.0
            else:
                event.decayed_affect = decayed
        except Exception:
            # Fallback: neutral decayed affect to avoid crashes
            event.decayed_affect = 0.0

    sorted_events = sorted(
        events,
        key=lambda e: (e.salience, e.timestamp),
        reverse=True
    )
    return sorted_events[:limit]
