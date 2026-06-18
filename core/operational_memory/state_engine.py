from __future__ import annotations

from typing import TypeVar

from core.log import log
from core.operational_memory.extractor import extract_state
from core.operational_memory.models import OperationalEvent, OperationalItem, OperationalState, utc_now_iso
from core.operational_memory.state_store import load_state, save_state


T = TypeVar("T", bound=OperationalItem)


def _item_key(item: OperationalItem) -> tuple[str, str]:
    return (item.text.strip().lower(), item.source.strip().lower())


def _merge_items(existing: list[T], incoming: list[T]) -> list[T]:
    merged = list(existing)
    seen = {_item_key(item): item for item in merged}
    for item in incoming:
        key = _item_key(item)
        if key in seen:
            current = seen[key]
            if getattr(item, "status", None) == "completed" and hasattr(current, "status"):
                current.status = "completed"
            continue
        merged.append(item)
        seen[key] = item
    return merged


def merge_state(existing: OperationalState, incoming: OperationalState) -> OperationalState:
    return OperationalState(
        project_id=existing.project_id,
        updated_at=utc_now_iso(),
        decisions=_merge_items(existing.decisions, incoming.decisions),
        tasks=_merge_items(existing.tasks, incoming.tasks),
        issues=_merge_items(existing.issues, incoming.issues),
        information=_merge_items(existing.information, incoming.information),
        open_questions=_merge_items(existing.open_questions, incoming.open_questions),
        threads=list(existing.threads),
        domain_stats=dict(existing.domain_stats),
    )


async def get_project_state(project_id: str) -> OperationalState:
    return await load_state(project_id)


async def ingest_messages(
    project_id: str,
    messages: list[str],
    source_event: OperationalEvent | None = None,
    nearby_messages: list[str] | None = None,
) -> OperationalState:
    existing = await load_state(project_id)
    incoming = await extract_state(messages, source_event=source_event, nearby_messages=nearby_messages)
    merged = merge_state(existing, incoming)
    saved = await save_state(project_id, merged)
    log(
        "OPERATIONAL_MEMORY_STATE_UPDATED",
        project_id=project_id,
        decisions=len(saved.decisions),
        tasks=len(saved.tasks),
        issues=len(saved.issues),
        information=len(saved.information),
        open_questions=len(saved.open_questions),
    )
    return saved
