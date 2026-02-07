from typing import List

class ToneProfile:
    def __init__(self, warmth: float, empathy: float, directness: float, verbosity: float):
        self.warmth = max(0.0, min(1.0, warmth))
        self.empathy = max(0.0, min(1.0, empathy))
        self.directness = max(0.0, min(1.0, directness))
        self.verbosity = max(0.0, min(1.0, verbosity))
    
    def to_dict(self) -> dict:
        return {
            'warmth': self.warmth,
            'empathy': self.empathy,
            'directness': self.directness,
            'verbosity': self.verbosity
        }

def compute_tone(events: List) -> ToneProfile:
    warmth = 0.5
    empathy = 0.5
    directness = 0.5
    verbosity = 0.5
    
    def _to_float(val):
        if isinstance(val, dict):
            numeric_vals = [v for v in val.values() if isinstance(v, (int, float))]
            return sum(numeric_vals) / len(numeric_vals) if numeric_vals else 0.0
        return float(val) if isinstance(val, (int, float)) else 0.0

    decayed_affects = [_to_float(e.decayed_affect) for e in events if hasattr(e, 'decayed_affect')]
    avg_decayed_affect = sum(decayed_affects) / len(decayed_affects) if decayed_affects else 0.0
    
    if avg_decayed_affect > 0.2:
        warmth += 0.2
        empathy += 0.2
    elif avg_decayed_affect < -0.2:
        empathy += 0.3
        directness -= 0.2
    
    saliences = [e.salience for e in events]
    avg_salience = sum(saliences) / len(saliences) if saliences else 0.0
    
    if avg_salience > 0.5:
        directness += 0.2
        verbosity -= 0.2
    
    return ToneProfile(warmth, empathy, directness, verbosity)