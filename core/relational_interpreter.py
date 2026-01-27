# core/relational_interpreter.py

from pathlib import Path
from datetime import datetime
import json

RELATIONAL_DIR = Path("data/relational")
RELATIONAL_DIR.mkdir(parents=True, exist_ok=True)


class RelationalInterpreter:
    """
    Interpreta segnali relazionali nel tempo.
    NON decide risposte.
    NON modifica il tono.
    OSSERVA e, se necessario, registra.
    """

    def interpret(self, event: dict) -> dict:
        """
        Valuta se un evento contiene un segnale relazionale.
        """

        content = event.get("content", {})
        affect = event.get("affect", {})
        text = content.get("text", "").lower()

        score = 0.0
        reasons = []

        # ===============================
        # SEGNALI BASE (GLOBALI)
        # ===============================

        if any(k in text for k in ["mi sento", "sono stanco", "sono sotto pressione"]):
            score += 0.3
            reasons.append("emotional_disclosure")

        if any(k in text for k in ["non mi fido", "non mi fido facilmente"]):
            score += 0.4
            reasons.append("trust_difficulty")

        if isinstance(affect, dict):
            if any(v > 0.6 for v in affect.values()):
                score += 0.3
                reasons.append("strong_affect")

        candidate = score >= 0.6

        result = {
            "relational_score": round(score, 2),
            "reasons": reasons,
            "candidate": candidate
        }

        if candidate:
            self._persist(event["user_id"], result)

        return result

    # ===============================
    # PERSISTENZA GREZZA
    # ===============================
    def _persist(self, user_id: str, data: dict):
        file_path = RELATIONAL_DIR / f"{user_id}.json"

        payload = {
            "timestamp": datetime.utcnow().isoformat(),
            "signal": data
        }

        if file_path.exists():
            with open(file_path, "r") as f:
                history = json.load(f)
        else:
            history = []

        history.append(payload)

        with open(file_path, "w") as f:
            json.dump(history, f, indent=2)
