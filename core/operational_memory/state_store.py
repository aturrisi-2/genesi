from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.operational_memory.models import OperationalState


_BASE_DIR = Path("memory/operational_state")
_SAFE_PROJECT_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def _safe_project_id(project_id: str) -> str:
    cleaned = _SAFE_PROJECT_RE.sub("_", project_id.strip())
    return cleaned.strip("._") or "default"


def _state_path(project_id: str) -> Path:
    return _BASE_DIR / f"{_safe_project_id(project_id)}.json"


def _dump_model(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


async def load_state(project_id: str) -> OperationalState:
    path = _state_path(project_id)
    if not path.exists():
        return OperationalState(project_id=project_id)

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return OperationalState(project_id=project_id)
    data.setdefault("project_id", project_id)
    return OperationalState(**data)


async def save_state(project_id: str, state: OperationalState) -> OperationalState:
    path = _state_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    state.project_id = project_id
    path.write_text(
        json.dumps(_dump_model(state), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return state
