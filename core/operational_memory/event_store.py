from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from core.operational_memory.models import OperationalEvent


_BASE_DIR = Path("memory/operational_events")
_SAFE_PROJECT_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def _safe_project_id(project_id: str) -> str:
    cleaned = _SAFE_PROJECT_RE.sub("_", project_id.strip())
    return cleaned.strip("._") or "default"


def _events_path(project_id: str) -> Path:
    return _BASE_DIR / f"{_safe_project_id(project_id)}.json"


def _dump_model(model: Any) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


async def list_events(project_id: str) -> list[OperationalEvent]:
    path = _events_path(project_id)
    if not path.exists():
        return []

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        return []
    return [OperationalEvent(**item) for item in data if isinstance(item, dict)]


async def save_events(project_id: str, events: list[OperationalEvent]) -> list[OperationalEvent]:
    path = _events_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([_dump_model(event) for event in events], ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return events


async def append_event(event: OperationalEvent) -> tuple[OperationalEvent, bool]:
    events = await list_events(event.project_id)
    for existing in events:
        if existing.event_id == event.event_id:
            return existing, False

    events.append(event)
    await save_events(event.project_id, events)
    return event, True


async def mark_event_status(
    project_id: str,
    event_id: str,
    status: str,
) -> OperationalEvent | None:
    events = await list_events(project_id)
    updated: OperationalEvent | None = None
    for event in events:
        if event.event_id == event_id:
            event.processed_status = status
            updated = event
            break

    if updated is not None:
        await save_events(project_id, events)
    return updated
