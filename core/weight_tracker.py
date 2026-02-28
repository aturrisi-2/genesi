"""WeightTracker — Sinapsi di apprendimento per route Proactor.

Traccia success/failure per ogni route per utente.
Pesi bounded [0.10, 0.95], default 0.50.
Decay: 5% verso 0.5 ogni 30 giorni.
Fire-and-forget async methods per uso in Proactor senza bloccare.
"""

import json
import os
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Any

logger = logging.getLogger(__name__)

_DEFAULT_WEIGHT = 0.50
_MIN_WEIGHT = 0.10
_MAX_WEIGHT = 0.95
_DELTA_SUCCESS = 0.02
_DELTA_FAILURE = -0.08
_DECAY_RATE = 0.05          # 5% verso centro ogni 30 giorni
_DECAY_DAYS = 30
_WEIGHTS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "weights")


def _ensure_dir():
    os.makedirs(_WEIGHTS_DIR, exist_ok=True)


def _weights_path(user_id: str) -> str:
    safe_id = user_id.replace("/", "_").replace("\\", "_")
    return os.path.join(_WEIGHTS_DIR, f"{safe_id}.json")


def _load_weights(user_id: str) -> Dict[str, Any]:
    """Carica i pesi da file. Ritorna dict vuoto se non esiste."""
    path = _weights_path(user_id)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning("WEIGHT_TRACKER load error user=%s: %s", user_id, e)
        return {}


def _save_weights(user_id: str, data: Dict[str, Any]) -> None:
    """Salva i pesi su file atomicamente (write + rename)."""
    _ensure_dir()
    path = _weights_path(user_id)
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_path, path)
    except Exception as e:
        logger.warning("WEIGHT_TRACKER save error user=%s: %s", user_id, e)
        try:
            os.remove(tmp_path)
        except OSError:
            pass


def _apply_decay(weight: float, last_updated: str) -> float:
    """Applica decay esponenziale verso 0.5 in base ai giorni trascorsi."""
    try:
        last_dt = datetime.fromisoformat(last_updated)
        now = datetime.now(timezone.utc)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
        days = (now - last_dt).total_seconds() / 86400.0
        if days < 1:
            return weight
        periods = days / _DECAY_DAYS
        # Ogni periodo: sposta del 5% verso 0.5
        decayed = weight + (_DEFAULT_WEIGHT - weight) * (1 - (1 - _DECAY_RATE) ** periods)
        return max(_MIN_WEIGHT, min(_MAX_WEIGHT, decayed))
    except Exception:
        return weight


class WeightTracker:
    """Traccia i pesi delle sinapsi route per ogni utente."""

    def get_weight(self, user_id: str, route: str) -> float:
        """Ritorna il peso corrente (con decay applicato) per la route."""
        data = _load_weights(user_id)
        entry = data.get(route)
        if entry is None:
            return _DEFAULT_WEIGHT
        weight = entry.get("weight", _DEFAULT_WEIGHT)
        last_updated = entry.get("last_updated", datetime.now(timezone.utc).isoformat())
        return _apply_decay(weight, last_updated)

    def record_outcome(self, user_id: str, route: str, success: bool) -> float:
        """
        Aggiorna il peso per la route dopo un outcome.
        Ritorna il nuovo peso.
        """
        data = _load_weights(user_id)
        entry = data.get(route, {})

        # Applica decay prima di aggiornare
        old_weight = entry.get("weight", _DEFAULT_WEIGHT)
        last_updated = entry.get("last_updated", datetime.now(timezone.utc).isoformat())
        decayed = _apply_decay(old_weight, last_updated)

        # Applica delta
        delta = _DELTA_SUCCESS if success else _DELTA_FAILURE
        new_weight = max(_MIN_WEIGHT, min(_MAX_WEIGHT, decayed + delta))

        data[route] = {
            "weight": round(new_weight, 4),
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "total_success": entry.get("total_success", 0) + (1 if success else 0),
            "total_failure": entry.get("total_failure", 0) + (0 if success else 1),
        }
        _save_weights(user_id, data)

        logger.debug(
            "SYNAPSE_UPDATE user=%s route=%s success=%s weight=%.3f→%.3f",
            user_id, route, success, old_weight, new_weight
        )
        return new_weight

    async def record_success_async(self, user_id: str, route: str) -> None:
        """Fire-and-forget: registra successo senza bloccare il caller."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.record_outcome, user_id, route, True)

    async def record_failure_async(self, user_id: str, route: str) -> None:
        """Fire-and-forget: registra fallimento senza bloccare il caller."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.record_outcome, user_id, route, False)


weight_tracker = WeightTracker()
