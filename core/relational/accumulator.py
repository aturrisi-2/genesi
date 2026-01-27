from collections import defaultdict
from typing import Dict, List
from datetime import datetime


class RelationalAccumulator:
    """
    Accumula segnali relazionali nel tempo.
    NON scrive su disco.
    Simula la sedimentazione umana della relazione.
    """

    def __init__(self):
        # user_id -> stato relazionale
        self.state: Dict[str, Dict] = defaultdict(self._initial_state)

    def _initial_state(self) -> Dict:
        return {
            "score": 0.0,
            "signals": [],
            "last_update": None
        }

    def update(self, user_id: str, relational_eval: Dict) -> Dict:
        """
        Aggiorna lo stato relazionale dell'utente.
        """
        state = self.state[user_id]

        increment = relational_eval.get("relational_score", 0.0)
        reasons = relational_eval.get("reasons", [])

        # accumulo lento
        state["score"] += increment
        state["signals"].extend(reasons)
        state["last_update"] = datetime.utcnow().isoformat()

        return state

    def get_state(self, user_id: str) -> Dict:
        return self.state[user_id]
