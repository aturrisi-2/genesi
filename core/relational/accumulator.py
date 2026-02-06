import json
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List

# Path: usa /opt/genesi su VPS, altrimenti directory locale
_vps_path = Path("/opt/genesi")
if _vps_path.exists():
    BASE_DIR = _vps_path
else:
    BASE_DIR = Path(__file__).resolve().parent.parent.parent
RELATIONAL_DIR = BASE_DIR / "data" / "relational"
RELATIONAL_DIR.mkdir(parents=True, exist_ok=True)


class RelationalAccumulator:
    def __init__(self):
        pass

    def _get_path(self, user_id: str) -> Path:
        return RELATIONAL_DIR / f"{user_id}.json"

    def load(self, user_id: str) -> Dict[str, Any]:
        path = self._get_path(user_id)
        if not path.exists():
            return {
                "score": 0.0,
                "signals": [],
                "last_update": None
            }

        try:
            return json.loads(path.read_text())
        except Exception:
            # 🔒 fallback di sicurezza
            return {
                "score": 0.0,
                "signals": [],
                "last_update": None
            }

    def save(self, user_id: str, state: Dict[str, Any]):
        path = self._get_path(user_id)
        path.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    def update(self, user_id: str, relational_eval: Dict[str, Any]) -> Dict[str, Any]:
        state = self.load(user_id)

        # --- stato precedente ---
        score = float(state.get("score", 0.0))
        signals = set(
            s for s in state.get("signals", [])
            if isinstance(s, str)
        )

        # --- input interprete ---
        delta = float(relational_eval.get("relational_score", 0.0))
        reasons = relational_eval.get("reasons", [])

        # 🔒 NORMALIZZAZIONE DIFENSIVA (QUI STAVA IL BUG)
        if isinstance(reasons, dict):
            reasons = list(reasons.keys())
        elif not isinstance(reasons, list):
            reasons = []

        # --- aggiorna score ---
        score = min(1.0, max(0.0, score + delta))

        # --- aggiorna segnali ---
        for r in reasons:
            if isinstance(r, str) and r.strip():
                signals.add(r.strip())

        new_state = {
            "score": round(score, 2),
            "signals": sorted(signals),
            "last_update": datetime.now().isoformat()
        }

        self.save(user_id, new_state)
        return new_state


# ✅ SINGLETON CONDIVISO (FONDAMENTALE)
relational_accumulator = RelationalAccumulator()
