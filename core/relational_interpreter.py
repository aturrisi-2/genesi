# core/relational_interpreter.py

from pathlib import Path
from datetime import datetime
import json

RELATIONAL_DIR = Path("data/relational")
RELATIONAL_DIR.mkdir(parents=True, exist_ok=True)

# Soglie umane (non rigide)
ACCUMULATION_THRESHOLD = 1.0
DECAY = 0.9  # dimenticanza naturale


class RelationalInterpreter:
    """
    Osserva segnali relazionali nel tempo.
    NON parla.
    NON influenza la risposta.
    Accumula lentamente come un essere umano.
    """

    def interpret(self, event: dict) -> dict:
        user_id = event["user_id"]
        text = event.get("content", {}).get("text", "").lower()
        affect = event.get("affect", {})

        signals = {}

        # ===============================
        # ESTRAZIONE SEGNALI GREZZI
        # ===============================

        if any(k in text for k in ["mi sento", "stanco", "sotto pressione"]):
            signals["emotional_load"] = 0.3

        if any(k in text for k in ["non mi fido", "non mi fido facilmente"]):
            signals["trust_difficulty"] = 0.4

        if isinstance(affect, dict):
            if any(v > 0.6 for v in affect.values()):
                signals["strong_affect"] = 0.3

        if not signals:
            return {
                "relational_score": 0.0,
                "reasons": [],
                "candidate": False
            }

        state = self._load_state(user_id)

        reasons = []
        for key, value in signals.items():
            previous = state.get(key, 0.0)
            updated = previous * DECAY + value
            state[key] = round(updated, 3)

            if updated >= ACCUMULATION_THRESHOLD:
                reasons.append(key)

        self._save_state(user_id, state)

        return {
            "relational_score": round(sum(signals.values()), 2),
            "reasons": list(signals.keys()),
            "candidate": bool(reasons)
        }

    # ===============================
    # STATO RELAZIONALE PERSISTENTE
    # ===============================

    def _load_state(self, user_id: str) -> dict:
        file_path = RELATIONAL_DIR / f"{user_id}.json"
        if not file_path.exists():
            return {}

        with open(file_path, "r") as f:
            return json.load(f)

    def _save_state(self, user_id: str, state: dict):
        file_path = RELATIONAL_DIR / f"{user_id}.json"
        payload = {
            "last_update": datetime.utcnow().isoformat(),
            "signals": state
        }

        with open(file_path, "w") as f:
            json.dump(payload, f, indent=2)
