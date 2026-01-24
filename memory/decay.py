from datetime import datetime

DECAY_PER_DAY = 0.05

def apply_affect_decay(event, now):
    event_time = datetime.fromisoformat(event.timestamp)
    days_elapsed = (now - event_time).total_seconds() / 86400
    decayed = event.affect * max(0.0, 1.0 - days_elapsed * DECAY_PER_DAY)
    return max(-1.0, min(1.0, decayed))
