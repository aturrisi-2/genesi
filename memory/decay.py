from datetime import datetime

DECAY_PER_DAY = 0.05

def apply_affect_decay(event, now):
    event_time = datetime.fromisoformat(event.timestamp)
    days_elapsed = (now - event_time).total_seconds() / 86400
    decay_factor = max(0.0, 1.0 - days_elapsed * DECAY_PER_DAY)

    affect = getattr(event, 'affect', None)

    if affect is None:
        # No affect field -> neutral
        return 0.0

    if isinstance(affect, (int, float)):
        # Float decay
        decayed = affect * decay_factor
        return max(-1.0, min(1.0, decayed))

    if isinstance(affect, dict):
        # Dict decay: apply to each numeric value, preserve structure
        decayed_dict = {}
        for k, v in affect.items():
            if isinstance(v, (int, float)):
                decayed_val = v * decay_factor
                decayed_dict[k] = max(-1.0, min(1.0, decayed_val))
            else:
                # Non-numeric values preserved as-is
                decayed_dict[k] = v
        # Return the dict; downstream must handle it
        return decayed_dict

    # Fallback for unexpected types
    return 0.0
