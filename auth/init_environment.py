from pathlib import Path
from datetime import datetime
import json

from core.log import log as _log
from memory.episodic import store_event
from core.psychological_detector import PSY_DETECTOR_DIR


def initialize_user_environment(user_id: str, preferences: dict = None):
    """
    Inizializza l'ambiente Genesi per un utente appena verificato.
    - Crea memoria episodica vuota (primo evento)
    - Crea stato detector psicologico default
    - Crea directory memoria psicologica
    """
    _log("ENV_INIT", user_id=user_id, status="starting")

    # 1. Evento iniziale in memoria episodica
    try:
        store_event(
            user_id=user_id,
            type="system_event",
            content={"text": "Utente appena registrato, ambiente inizializzato"},
            salience=0.5,
            affect={"valence": 0.0, "arousal": 0.0}
        )
        _log("ENV_INIT", user_id=user_id, step="episodic_memory", status="ok")
    except Exception as e:
        _log("ENV_INIT", user_id=user_id, step="episodic_memory", error=str(e))

    # 2. Stato detector psicologico default
    try:
        PSY_DETECTOR_DIR.mkdir(parents=True, exist_ok=True)
        psy_state_path = PSY_DETECTOR_DIR / f"{user_id}.json"
        if not psy_state_path.exists():
            default_state = {
                "user_id": user_id,
                "last_update": datetime.utcnow().isoformat(),
                "state": {
                    "active": False,
                    "neutral_count": 0,
                    "consecutive_distress": 0,
                }
            }
            with open(psy_state_path, "w") as f:
                json.dump(default_state, f, indent=2)
        _log("ENV_INIT", user_id=user_id, step="psy_detector", status="ok")
    except Exception as e:
        _log("ENV_INIT", user_id=user_id, step="psy_detector", error=str(e))

    # 3. Directory memoria psicologica
    try:
        psy_mem_dir = Path("data/psychological/memory")
        psy_mem_dir.mkdir(parents=True, exist_ok=True)
        _log("ENV_INIT", user_id=user_id, step="psy_memory_dir", status="ok")
    except Exception as e:
        _log("ENV_INIT", user_id=user_id, step="psy_memory_dir", error=str(e))

    # 4. Directory utente standard (data/users)
    try:
        user_dir = Path("data/users")
        user_dir.mkdir(parents=True, exist_ok=True)
        _log("ENV_INIT", user_id=user_id, step="user_dir", status="ok")
    except Exception as e:
        _log("ENV_INIT", user_id=user_id, step="user_dir", error=str(e))

    _log("ENV_INIT", user_id=user_id, status="completed")
