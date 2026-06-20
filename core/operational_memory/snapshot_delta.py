"""FASE 4.3 — Operational Snapshot Memory.

Compare the operational lifecycle state across time (previous snapshot vs
current state) and answer: what changed since last time, what is still open,
what was closed/superseded, what re-appeared, what is old but still active, what
must no longer be reported as active.

Pure and domain-agnostic: works on generic lifecycle statuses and item ids, no
profession/site/platform vocabulary. No IO here (persistence lives in
snapshot_store)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from core.operational_memory.models import (
    LifecycleCategory,
    LifecycleItemState,
    OperationalItem,
    OperationalState,
    SnapshotDelta,
)


# Generic age buckets (days). Not tied to any domain cadence.
_AGE_BUCKETS = [
    ("fresh", 2),
    ("recent", 7),
    ("aging", 21),
    ("old", None),
]
DEFAULT_AGING_ATTENTION_DAYS = 14

_ACTIVE_BY_CATEGORY = {
    "task": {"open", "in_progress", "blocked"},
    "issue": {"open", "confirmed", "investigating", "mitigated", "reopened"},
    "decision": {"proposed", "confirmed", "active"},
    "question": {"open", "partially_answered"},
    "information": {"current", "updated"},
}
_CLOSED_STATUSES = {
    "completed", "verified", "cancelled", "superseded", "resolved",
    "revoked", "expired", "answered", "historical",
}
_SUPERSEDED_STATUSES = {"superseded", "revoked", "cancelled", "expired"}

_CATEGORY_FIELDS: list[tuple[LifecycleCategory, str]] = [
    ("task", "tasks"),
    ("issue", "issues"),
    ("decision", "decisions"),
    ("question", "open_questions"),
    ("information", "information"),
]


def _is_active(category: str, status: str) -> bool:
    return status in _ACTIVE_BY_CATEGORY.get(category, set())


def _parse_ts(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _label(category: str, text: str) -> str:
    return f"[{category}] {text}"


def item_status_index(state: OperationalState) -> list[LifecycleItemState]:
    """Snapshot the lifecycle status of every operational item (for persistence
    and later delta computation)."""
    out: list[LifecycleItemState] = []
    for category, field_name in _CATEGORY_FIELDS:
        for item in getattr(state, field_name):
            lifecycle = item.lifecycle
            status = lifecycle.current_status if lifecycle else "open"
            first_seen = None
            last_evidence = None
            if lifecycle:
                if lifecycle.lifecycle_history:
                    first_seen = lifecycle.lifecycle_history[0].changed_at
                last_evidence = lifecycle.last_evidence_at
            first_seen = first_seen or item.source_timestamp
            last_evidence = last_evidence or item.source_timestamp
            out.append(
                LifecycleItemState(
                    item_id=item.id,
                    category=category,
                    status=status,
                    text=item.text,
                    first_seen_at=first_seen,
                    last_evidence_at=last_evidence,
                )
            )
    return out


def _age_bucket(first_seen_at: str | None, reference_now: datetime) -> str:
    seen = _parse_ts(first_seen_at)
    if seen is None:
        return "unknown"
    days = (reference_now - seen).days
    for name, limit in _AGE_BUCKETS:
        if limit is None or days < limit:
            return name
    return "old"


def compute_snapshot_delta(
    previous_states: list[LifecycleItemState] | None,
    current_state: OperationalState,
    reference_now: Optional[datetime] = None,
    aging_attention_days: int = DEFAULT_AGING_ATTENTION_DAYS,
    previous_snapshot_id: Optional[str] = None,
    previous_generated_at: Optional[str] = None,
) -> SnapshotDelta:
    """Diff the previous persisted item statuses against the current state."""
    reference_now = reference_now or datetime.now(timezone.utc)
    prev_by_id = {state.item_id: state.status for state in (previous_states or [])}
    current = item_status_index(current_state)

    delta = SnapshotDelta(
        previous_snapshot_id=previous_snapshot_id,
        previous_generated_at=previous_generated_at,
    )
    buckets: dict[str, list[str]] = {name: [] for name, _ in _AGE_BUCKETS}

    for state in current:
        label = _label(state.category, state.text)
        active = _is_active(state.category, state.status)
        prev = prev_by_id.get(state.item_id)

        if prev is None:
            if active:
                delta.newly_opened.append(label)
        elif prev != state.status:
            if state.status in {"completed", "verified"}:
                delta.newly_completed.append(label)
            elif state.status == "resolved":
                delta.newly_resolved.append(label)
            elif state.status in _SUPERSEDED_STATUSES:
                delta.newly_superseded.append(label)
            elif state.status == "stale":
                delta.newly_stale.append(label)
            elif state.status == "reopened" or (prev in _CLOSED_STATUSES and active):
                delta.reopened_items.append(label)
            elif active:
                delta.newly_opened.append(label)
        elif active:
            delta.still_active.append(label)

        if state.status in _SUPERSEDED_STATUSES:
            delta.historical_superseded_items.append(label)

        if active:
            bucket = _age_bucket(state.first_seen_at, reference_now)
            buckets.setdefault(bucket, []).append(label)
            seen = _parse_ts(state.first_seen_at)
            if seen is not None and (reference_now - seen).days >= aging_attention_days:
                delta.aging_attention_items.append(label)

    delta.unresolved_items_by_age = {name: items for name, items in buckets.items() if items}
    return delta
