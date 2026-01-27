import json
from pathlib import Path
from datetime import datetime

RELATIONAL_DIR = Path("data/relational")
RELATIONAL_DIR.mkdir(parents=True, exist_ok=True)


class RelationalAccumulator:
    def __init__(self):
        pass

    def _get_path(self, user_id: str) -> Path:
        return RELATIONAL_DIR / f"{user_id}.json"

    def load(self, user_id: str) -> dict:
        path = self._get_path(user_id)
        if not path.exists():
            return {
                "score": 0.0,
                "signals": [],
                "last_update": None
            }
        return json.loads(path.read_text())

    def save(self, user_id: str, state: dict):
        path = self._get_path(user_id)
        path.write_text(json.dumps(state, indent=2))

    def update(self, user_id: str, relational_eval: dict) -> dict:
        state = self.load(user_id)

        score = float(state.get("score", 0.0))
        signals = set(state.get("signals", []))

        delta = float(relational_eval.get("relational_score", 0.0))
        reasons = relational_eval.get("reasons", [])

        # clamp score
        score = min(1.0, max(0.0, score + delta))

        # add ONLY valid relational reasons
        for r in reasons:
            if isinstance(r, str) and r.strip():
                signals.add(r)

        new_state = {
            "score": round(score, 2),
            "signals": sorted(signals),
            "last_update": datetime.now().isoformat()
        }

        self.save(user_id, new_state)
        return new_state


# ✅ SINGLETON CONDIVISO (FONDAMENTALE)
relational_accumulator = RelationalAccumulator()
