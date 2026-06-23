from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from core.operational_memory.models import utc_now_iso


_BASE_DIR = Path("memory/operational_indexes")
_SAFE_PROJECT_RE = re.compile(r"[^a-zA-Z0-9_.-]+")


def _safe_project_id(project_id: str) -> str:
    cleaned = _SAFE_PROJECT_RE.sub("_", (project_id or "").strip())
    return cleaned.strip("._") or "default"


def _index_path(project_id: str) -> Path:
    return _BASE_DIR / f"{_safe_project_id(project_id)}_incremental.json"


class IncrementalIndex(BaseModel):
    """Persistent, generalizable index that lets the operational pipeline
    rebuild only the dirty slice of state instead of the whole project.

    Nothing here is specific to any single chat: it stores opaque event ids,
    thread ids, normalized pair keys and timestamps only."""

    project_id: str
    # event_id -> thread_id mapping for every event already folded into a thread
    event_thread_map: dict[str, str] = Field(default_factory=dict)
    # every event id already processed into the thread layer
    known_event_ids: list[str] = Field(default_factory=list)
    # normalized relation pair keys already materialized (source|target sorted)
    relation_pair_keys: list[str] = Field(default_factory=list)
    # macro_thread_id -> sorted child thread ids snapshot (to detect macro drift)
    macro_child_map: dict[str, list[str]] = Field(default_factory=dict)
    # last canonical coverage snapshot: normalized label -> thread count
    canonical_distribution: dict[str, int] = Field(default_factory=dict)
    last_thread_rebuild_at: str | None = None
    last_relation_rebuild_at: str | None = None
    last_macro_rebuild_at: str | None = None
    last_lifecycle_update_at: str | None = None
    last_cross_item_lifecycle_update_at: str | None = None
    # item_id -> current lifecycle status (snapshot for drift detection)
    lifecycle_item_map: dict[str, str] = Field(default_factory=dict)
    # item ids touched by the most recent lifecycle update
    dirty_lifecycle_items: list[str] = Field(default_factory=list)
    # stable keys (item_id:new_status) of transitions already emitted
    lifecycle_transition_keys: list[str] = Field(default_factory=list)
    # normalized older|newer item-id pairs already resolved
    supersession_pair_keys: list[str] = Field(default_factory=list)
    contradiction_pair_keys: list[str] = Field(default_factory=list)
    dirty_cross_item_pairs: list[str] = Field(default_factory=list)
    full_rebuild_required: bool = False
    rebuild_reason: str = ""
    # diagnostics from the most recent run (not load-bearing, pure reporting)
    last_run: dict[str, Any] = Field(default_factory=dict)

    def known_set(self) -> set[str]:
        return set(self.known_event_ids)

    def pair_key_set(self) -> set[str]:
        return set(self.relation_pair_keys)


def _safe_load(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def load_index(project_id: str) -> IncrementalIndex:
    data = _safe_load(_index_path(project_id))
    data.setdefault("project_id", project_id)
    try:
        return IncrementalIndex(**data)
    except Exception:
        return IncrementalIndex(project_id=project_id)


def save_index(project_id: str, index: IncrementalIndex) -> IncrementalIndex:
    index.project_id = project_id
    path = _index_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = index.model_dump() if hasattr(index, "model_dump") else index.dict()
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return index


def reset_index(project_id: str, reason: str = "") -> IncrementalIndex:
    index = IncrementalIndex(project_id=project_id, rebuild_reason=reason)
    return save_index(project_id, index)


def touch_thread_rebuild(index: IncrementalIndex) -> None:
    index.last_thread_rebuild_at = utc_now_iso()


def touch_relation_rebuild(index: IncrementalIndex) -> None:
    index.last_relation_rebuild_at = utc_now_iso()


def touch_macro_rebuild(index: IncrementalIndex) -> None:
    index.last_macro_rebuild_at = utc_now_iso()
