from pathlib import Path
from datetime import datetime
import json

from core.log import log as _log


def initialize_user_environment(user_id: str, email: str, preferences: dict = None):
    """
    Inizializza l'ambiente Genesi per un utente appena verificato.
    - Crea directory utente
    - Crea profilo iniziale vuoto
    - Sincronizza user_manager per evitare USER_NOT_FOUND ciclici
    """
    _log("ENV_INIT", user_id=user_id, status="starting")

    # 1. Directory utente standard (data/users)
    try:
        user_dir = Path("data/users")
        user_dir.mkdir(parents=True, exist_ok=True)
        _log("ENV_INIT", user_id=user_id, step="user_dir", status="ok")
    except Exception as e:
        _log("ENV_INIT", user_id=user_id, step="user_dir", error=str(e))

    # 2. Profilo iniziale (memory/)
    try:
        memory_dir = Path("memory")
        memory_dir.mkdir(parents=True, exist_ok=True)
        profile_path = memory_dir / f"profile_{user_id}.json"
        if not profile_path.exists():
            default_profile = {
                "user_id": user_id,
                "email": email,
                "created_at": datetime.utcnow().isoformat(),
                "preferences": preferences or {},
            }
            with open(profile_path, "w") as f:
                json.dump(default_profile, f, indent=2)
        _log("ENV_INIT", user_id=user_id, step="profile", status="ok")
    except Exception as e:
        _log("ENV_INIT", user_id=user_id, step="profile", error=str(e))

    # 3. Sincronizza user_manager per evitare USER_NOT_FOUND ciclici
    try:
        from core.user_manager import user_manager
        if not user_manager.get_user(user_id):
            user_manager.create_user(user_id)
            _log("ENV_INIT", user_id=user_id, step="user_manager_sync", status="created")
        else:
            _log("ENV_INIT", user_id=user_id, step="user_manager_sync", status="exists")
    except Exception as e:
        _log("ENV_INIT", user_id=user_id, step="user_manager_sync", error=str(e))

    _log("ENV_INIT", user_id=user_id, status="completed")
