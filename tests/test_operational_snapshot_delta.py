from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from core.operational_memory.models import (
    Decision,
    Information,
    Issue,
    LifecycleHistoryEntry,
    LifecycleItemState,
    LifecycleState,
    OperationalQuestion,
    OperationalState,
    OperationalTask,
    StoredLifecycleSnapshot,
)
from core.operational_memory.snapshot_delta import compute_snapshot_delta, item_status_index


NOW = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)


def _ts(days_ago: int) -> str:
    return (NOW - timedelta(days=days_ago)).isoformat()


def _lc(category: str, status: str, first_seen_days: int) -> LifecycleState:
    seen = _ts(first_seen_days)
    return LifecycleState(
        category=category,
        current_status=status,
        last_evidence_at=seen,
        lifecycle_history=[LifecycleHistoryEntry(status=status, changed_at=seen)],
    )


def _task(item_id, status, first_seen_days=1):
    return OperationalTask(id=item_id, text=f"task {item_id}", source="m", source_event_id=f"e_{item_id}",
                           source_timestamp=_ts(first_seen_days), lifecycle=_lc("task", status, first_seen_days))


def _issue(item_id, status, first_seen_days=1):
    return Issue(id=item_id, text=f"issue {item_id}", source="m", source_event_id=f"e_{item_id}",
                 source_timestamp=_ts(first_seen_days), lifecycle=_lc("issue", status, first_seen_days))


def _prev(item_id, category, status):
    return LifecycleItemState(item_id=item_id, category=category, status=status, text=f"{category} {item_id}")


# --------------------------------------------------------------------------- #


def test_newly_completed_and_resolved():
    state = OperationalState(project_id="p", tasks=[_task("t1", "completed")], issues=[_issue("i1", "resolved")])
    previous = [_prev("t1", "task", "open"), _prev("i1", "issue", "open")]
    delta = compute_snapshot_delta(previous, state, reference_now=NOW)
    assert any("task t1" in x for x in delta.newly_completed)
    assert any("issue i1" in x for x in delta.newly_resolved)


def test_newly_opened_when_absent_before():
    state = OperationalState(project_id="p", tasks=[_task("t9", "open")])
    delta = compute_snapshot_delta([], state, reference_now=NOW)
    assert any("task t9" in x for x in delta.newly_opened)


def test_reopened_detection():
    state = OperationalState(project_id="p", issues=[_issue("i2", "reopened")])
    previous = [_prev("i2", "issue", "resolved")]
    delta = compute_snapshot_delta(previous, state, reference_now=NOW)
    assert any("issue i2" in x for x in delta.reopened_items)


def test_superseded_historical_and_newly():
    state = OperationalState(project_id="p", decisions=[Decision(
        id="d1", text="decision d1", source="m", source_event_id="e", source_timestamp=_ts(1),
        lifecycle=_lc("decision", "superseded", 1))])
    previous = [_prev("d1", "decision", "confirmed")]
    delta = compute_snapshot_delta(previous, state, reference_now=NOW)
    assert any("decision d1" in x for x in delta.newly_superseded)
    assert any("decision d1" in x for x in delta.historical_superseded_items)


def test_still_active_unchanged():
    state = OperationalState(project_id="p", tasks=[_task("t3", "open")])
    previous = [_prev("t3", "task", "open")]
    delta = compute_snapshot_delta(previous, state, reference_now=NOW)
    assert any("task t3" in x for x in delta.still_active)
    assert not delta.newly_opened


def test_aging_buckets_and_attention():
    state = OperationalState(project_id="p", tasks=[
        _task("fresh", "open", first_seen_days=1),
        _task("old", "open", first_seen_days=30),
    ])
    delta = compute_snapshot_delta([], state, reference_now=NOW)
    assert "fresh" in delta.unresolved_items_by_age
    assert "old" in delta.unresolved_items_by_age
    assert any("task old" in x for x in delta.aging_attention_items)
    assert not any("task fresh" in x for x in delta.aging_attention_items)


def test_superseded_not_reported_as_active():
    state = OperationalState(project_id="p", tasks=[_task("t4", "superseded", first_seen_days=40)])
    delta = compute_snapshot_delta([_prev("t4", "task", "open")], state, reference_now=NOW)
    # superseded task must not show up in any active bucket nor aging attention
    flat = [x for items in delta.unresolved_items_by_age.values() for x in items]
    assert not any("task t4" in x for x in flat)
    assert not any("task t4" in x for x in delta.aging_attention_items)


def test_delta_is_pure_no_threads_needed():
    # No threads, no events — delta works purely on lifecycle state.
    state = OperationalState(project_id="p", tasks=[_task("t5", "completed")])
    delta = compute_snapshot_delta([_prev("t5", "task", "open")], state, reference_now=NOW)
    assert delta.newly_completed


@pytest.mark.parametrize("category,model,status,prev,bucket_field", [
    ("task", OperationalTask, "completed", "open", "newly_completed"),
    ("issue", Issue, "resolved", "open", "newly_resolved"),
    ("decision", Decision, "superseded", "confirmed", "newly_superseded"),
    ("question", OperationalQuestion, "answered", "open", None),
    ("information", Information, "superseded", "current", "newly_superseded"),
])
def test_multidomain_categories(category, model, status, prev, bucket_field):
    item = model(id="x", text=f"{category} item", source="m", source_event_id="e", source_timestamp=_ts(1),
                 lifecycle=_lc(category, status, 1))
    state = OperationalState(project_id="p")
    field = {"task": "tasks", "issue": "issues", "decision": "decisions", "question": "open_questions", "information": "information"}[category]
    setattr(state, field, [item])
    delta = compute_snapshot_delta([_prev("x", category, prev)], state, reference_now=NOW)
    if bucket_field:
        assert getattr(delta, bucket_field), f"{category} missing in {bucket_field}"


def test_item_status_index_roundtrip():
    state = OperationalState(project_id="p", tasks=[_task("t6", "open")])
    idx = item_status_index(state)
    assert idx and idx[0].item_id == "t6" and idx[0].status == "open" and idx[0].category == "task"


@pytest.mark.asyncio
async def test_lifecycle_snapshot_store_roundtrip(monkeypatch, tmp_path):
    from core.operational_memory import snapshot_store

    monkeypatch.setattr(snapshot_store, "_LIFECYCLE_BASE_DIR", tmp_path / "lc")
    rec1 = StoredLifecycleSnapshot(snapshot_id="lcsnap_1", project_id="p", generated_at="2026-06-18T10:00:00+00:00",
                                   item_states=[_prev("t1", "task", "open")])
    rec2 = StoredLifecycleSnapshot(snapshot_id="lcsnap_2", project_id="p", generated_at="2026-06-19T10:00:00+00:00",
                                   item_states=[_prev("t1", "task", "completed")])
    snapshot_store.save_lifecycle_snapshot("p", rec1)
    snapshot_store.save_lifecycle_snapshot("p", rec2)
    latest = snapshot_store.load_latest_lifecycle_snapshot("p")
    assert latest is not None and latest.snapshot_id == "lcsnap_2"
    assert latest.item_states[0].status == "completed"
    assert len(snapshot_store.list_lifecycle_snapshots("p")) == 2


@pytest.mark.asyncio
async def test_lifecycle_snapshot_retention(monkeypatch, tmp_path):
    from core.operational_memory import snapshot_store

    monkeypatch.setattr(snapshot_store, "_LIFECYCLE_BASE_DIR", tmp_path / "lc")
    for i in range(5):
        snapshot_store.save_lifecycle_snapshot(
            "p",
            StoredLifecycleSnapshot(snapshot_id=f"lcsnap_{i}", project_id="p", generated_at=f"2026-06-1{i}T10:00:00+00:00"),
            retention=3,
        )
    assert len(snapshot_store.list_lifecycle_snapshots("p")) == 3
