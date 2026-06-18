from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.operational_memory.event_store import list_events
from core.operational_memory.models import OperationalSnapshot, OperationalState, utc_now_iso
from core.operational_memory.state_store import load_state


_BASE_DIR = Path("memory/operational_snapshots")
_SAFE_PROJECT_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def _safe_project_id(project_id: str) -> str:
    cleaned = _SAFE_PROJECT_RE.sub("_", project_id.strip())
    return cleaned.strip("._") or "default"


def _safe_snapshot_id(raw: str) -> str:
    return _SAFE_PROJECT_RE.sub("_", raw).strip("._")


def _project_dir(project_id: str) -> Path:
    return _BASE_DIR / _safe_project_id(project_id)


def _dump_model(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _counts(state: OperationalState) -> dict[str, int]:
    return {
        "decisions": len(state.decisions),
        "tasks": len(state.tasks),
        "issues": len(state.issues),
        "information": len(state.information),
        "open_questions": len(state.open_questions),
    }


async def create_snapshot(project_id: str) -> OperationalSnapshot:
    state = await load_state(project_id)
    events = await list_events(project_id)
    timestamp = utc_now_iso()
    snapshot = OperationalSnapshot(
        snapshot_id=f"snap_{_safe_snapshot_id(timestamp)}",
        project_id=project_id,
        timestamp=timestamp,
        state=state,
        counts=_counts(state),
        source_event_count=len(events),
    )
    path = _project_dir(project_id) / f"{snapshot.snapshot_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(_dump_model(snapshot), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return snapshot


async def list_snapshots(project_id: str) -> list[OperationalSnapshot]:
    directory = _project_dir(project_id)
    if not directory.exists():
        return []

    snapshots: list[OperationalSnapshot] = []
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            snapshots.append(OperationalSnapshot(**data))
    return snapshots
