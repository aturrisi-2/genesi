import json
import os
import uuid
from pathlib import Path
from typing import Optional

from core.user import User

BASE_DIR = Path("data/users")
BASE_DIR.mkdir(parents=True, exist_ok=True)

def load_user(user_id: str) -> Optional[User]:
    file_path = BASE_DIR / f"{user_id}.json"
    if not file_path.exists():
        return None
    
    with open(file_path, 'r') as f:
        return User.from_dict(json.load(f))

def save_user(user: User) -> None:
    print("DEBUG SAVE_USER user.profile:", user.profile, flush=True)
    print("DEBUG SAVE_USER to_dict:", user.to_dict(), flush=True)

    file_path = BASE_DIR / f"{user.user_id}.json"
    with open(file_path, 'w') as f:
        json.dump(user.to_dict(), f, indent=2)


def create_user() -> User:
    user_id = str(uuid.uuid4())
    user = User(user_id=user_id)
    save_user(user)
    return user