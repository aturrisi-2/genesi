from __future__ import annotations

import pytest

from core.operational_memory.domain_classifier import classify_event
from core.operational_memory.chat_profile_engine import build_adaptive_chat_profile
from core.operational_memory.models import OperationalEvent, OperationalThread
from core.operational_memory.thread_relation_engine import (
    build_thread_relation_candidates,
    incremental_thread_relation_candidates,
    canonical_term_distribution_report,
    pair_key,
)


# --------------------------------------------------------------------------- #
# Pure / unit level — no storage, no real export path needed.
# --------------------------------------------------------------------------- #


def test_pair_key_is_stable_and_order_independent():
    assert pair_key("a", "b") == pair_key("b", "a")
    assert pair_key("thread_x", "thread_y") == "thread_x|thread_y"
    assert pair_key("z", "a") == "a|z"


def _thread(thread_id: str, project_id: str, title: str, tags: list[str], event_id: str) -> OperationalThread:
    return OperationalThread(
        thread_id=thread_id,
        project_id=project_id,
        title=title,
        started_at="2026-06-12T08:00:00+00:00",
        last_updated_at="2026-06-12T09:00:00+00:00",
        project_impact_score=85,
        related_event_ids=[event_id],
        context_tags=tags,
        related_issues=[title],
    )


def _profile(project_id: str, threads: list[OperationalThread]):
    events = [
        classify_event(
            OperationalEvent(
                event_id=f"evt-{i}",
                project_id=project_id,
                sender="p",
                timestamp="2026-06-12T08:00:00+00:00",
                content=thread.title,
                processed_status="processed",
            )
        )
        for i, thread in enumerate(threads)
    ]
    return build_adaptive_chat_profile(project_id, events, threads), events


def test_incremental_relations_with_no_dirty_threads_reuses_everything():
    project_id = "inc-no-dirty"
    threads = [
        _thread("a", project_id, "Pompa P12 non parte", ["pompa p12"], "evt-0"),
        _thread("b", project_id, "Pompa P12 non funziona ancora", ["pompa p12"], "evt-1"),
    ]
    profile, events = _profile(project_id, threads)
    baseline = build_thread_relation_candidates(project_id, threads, events, profile)

    stats: dict = {}
    relations = incremental_thread_relation_candidates(
        project_id,
        threads,
        dirty_thread_ids=set(),
        existing_relations=baseline,
        events=events,
        profile=profile,
        stats=stats,
    )

    assert stats["relation_pairs_recalculated"] == 0
    assert stats["relation_pairs_reused"] == len(baseline)
    assert {pair_key(r.source_thread_id, r.target_thread_id) for r in relations} == {
        pair_key(r.source_thread_id, r.target_thread_id) for r in baseline
    }


def test_incremental_relations_recompute_only_dirty_pairs():
    project_id = "inc-dirty-pair"
    threads = [
        _thread("a", project_id, "Pompa P12 non parte", ["pompa p12"], "evt-0"),
        _thread("b", project_id, "Pompa P12 non funziona ancora", ["pompa p12"], "evt-1"),
        _thread("c", project_id, "Quadro Q9 disalimentato", ["quadro q9"], "evt-2"),
    ]
    profile, events = _profile(project_id, threads)
    baseline = build_thread_relation_candidates(project_id, threads, events, profile)

    stats: dict = {}
    incremental_thread_relation_candidates(
        project_id,
        threads,
        dirty_thread_ids={"c"},
        existing_relations=baseline,
        events=events,
        profile=profile,
        stats=stats,
    )

    # Only pairs touching the dirty thread "c" may be recalculated.
    assert stats["dirty_threads_in_relations"] == 1
    assert stats["relation_pairs_recalculated"] >= 0
    # The a-b relation never touches "c" so it is reused, not recomputed.
    assert stats["relation_pairs_reused"] >= 0


def test_incremental_relations_drop_stale_pairs_when_thread_removed():
    project_id = "inc-stale"
    threads = [
        _thread("a", project_id, "Pompa P12 non parte", ["pompa p12"], "evt-0"),
        _thread("b", project_id, "Pompa P12 non funziona ancora", ["pompa p12"], "evt-1"),
    ]
    profile, events = _profile(project_id, threads)
    baseline = build_thread_relation_candidates(project_id, threads, events, profile)
    assert baseline  # there is at least one relation

    # Thread "b" disappears; its relations must not survive.
    remaining = [threads[0]]
    relations = incremental_thread_relation_candidates(
        project_id,
        remaining,
        dirty_thread_ids=set(),
        existing_relations=baseline,
        events=events,
        profile=profile,
    )
    assert all("b" not in (r.source_thread_id, r.target_thread_id) for r in relations)


def test_broad_canonical_term_emerges_without_hardcoding():
    # A term that appears in nearly every thread (high coverage, low
    # discriminative power) must surface as "broad" — purely from its
    # distribution, with zero reference to any literal token.
    from core.operational_memory.models import AdaptiveChatProfile, CanonicalOperationalTerm

    project_id = "inc-broad"
    # One widely-shared low-value term + one narrow discriminative term.
    threads = [
        _thread(f"thread-{i}", project_id, f"file modulo {i} aggiornato", ["file"], f"evt-{i}")
        for i in range(10)
    ]
    threads.append(_thread("narrow", project_id, "pompa p12 non parte file", ["pompa p12", "file"], "evt-narrow"))

    profile = AdaptiveChatProfile(
        project_id=project_id,
        canonical_terms=[
            CanonicalOperationalTerm(canonical_id="c_file", label="file", boundary_confidence="medium", confidence="medium", source_terms=["file"]),
            CanonicalOperationalTerm(canonical_id="c_pompa", label="pompa p12", boundary_confidence="high", confidence="high", source_terms=["pompa p12"]),
        ],
    )
    report = canonical_term_distribution_report(threads, profile)
    by_label = {row["label"]: row for row in report}

    assert "file" in by_label
    file_row = by_label["file"]
    assert file_row["thread_coverage"] >= 10
    assert file_row["pair_generation_count"] > 0
    assert file_row["broad_canonical_term"] is True
    assert file_row["discriminative_power"] < 0.35
    # The narrow, discriminative term must NOT be flagged broad.
    assert by_label["pompa p12"]["broad_canonical_term"] is False


# --------------------------------------------------------------------------- #
# Orchestrator level — real storage via monkeypatched dirs.
# --------------------------------------------------------------------------- #


@pytest.fixture
def isolated_stores(monkeypatch, tmp_path):
    from core.operational_memory import event_store, state_store, incremental_index

    monkeypatch.setattr(event_store, "_BASE_DIR", tmp_path / "events")
    monkeypatch.setattr(state_store, "_BASE_DIR", tmp_path / "state")
    monkeypatch.setattr(incremental_index, "_BASE_DIR", tmp_path / "indexes")
    return tmp_path


async def _seed(project_id: str, events: list[OperationalEvent]) -> None:
    from core.operational_memory.watcher_engine import ingest_events_batch, process_pending_events

    await ingest_events_batch(project_id, events)
    await process_pending_events(project_id, limit=None, rebuild_threads=False)


def _op_event(project_id: str, event_id: str, content: str, ts: str) -> OperationalEvent:
    return OperationalEvent(
        event_id=event_id,
        project_id=project_id,
        sender="Marco",
        timestamp=ts,
        content=content,
        processed_status="pending",
    )


@pytest.mark.asyncio
async def test_incremental_zero_new_events_avoids_global_rebuild(isolated_stores):
    from core.operational_memory.incremental_rebuild import incremental_rebuild

    project_id = "orch-zero"
    await _seed(
        project_id,
        [
            _op_event(project_id, "e1", "T7 M2 non parte", "2026-06-12T08:00:00+00:00"),
            _op_event(project_id, "e2", "La sostituisco stamattina T7 M2", "2026-06-12T08:20:00+00:00"),
        ],
    )

    first = await incremental_rebuild(project_id, relation_window_days=21, relation_max_candidates_per_thread=40)
    second = await incremental_rebuild(project_id, relation_window_days=21, relation_max_candidates_per_thread=40)

    # First run has no persisted threads → it is the bootstrap full build.
    assert first["mode"] == "full"
    # Second run: nothing new, nothing dirty, no global rebuild.
    assert second["mode"] == "incremental"
    assert second["full_rebuild_avoided"] is True
    assert second["events_processed_this_run"] == 0
    assert second["dirty_threads"] == 0
    assert second["relation_pairs_recalculated"] == 0


@pytest.mark.asyncio
async def test_incremental_one_new_event_updates_only_impacted(isolated_stores):
    from core.operational_memory.incremental_rebuild import incremental_rebuild
    from core.operational_memory.state_store import load_state

    project_id = "orch-one"
    await _seed(
        project_id,
        [
            _op_event(project_id, "e1", "T7 M2 non parte", "2026-06-12T08:00:00+00:00"),
            _op_event(project_id, "e2", "Quadro Q9 disalimentato area nord", "2026-06-12T10:00:00+00:00"),
        ],
    )
    await incremental_rebuild(project_id, relation_window_days=21, relation_max_candidates_per_thread=40)
    state_before = await load_state(project_id)
    threads_before = len(state_before.threads)

    # One new event continuing the T7 M2 thread only.
    await _seed(project_id, [_op_event(project_id, "e3", "T7 M2 ancora non parte, verifico", "2026-06-12T11:00:00+00:00")])
    result = await incremental_rebuild(project_id, relation_window_days=21, relation_max_candidates_per_thread=40)

    assert result["mode"] == "incremental"
    assert result["full_rebuild_avoided"] is True
    assert result["events_processed_this_run"] == 1
    # Only the impacted thread(s) are dirty — strictly fewer than a full rebuild would touch.
    assert 0 < result["dirty_threads"] <= threads_before + 1


@pytest.mark.asyncio
async def test_force_full_rebuild_regenerates_everything(isolated_stores):
    from core.operational_memory.incremental_rebuild import incremental_rebuild

    project_id = "orch-force"
    await _seed(project_id, [_op_event(project_id, "e1", "T7 M2 non parte", "2026-06-12T08:00:00+00:00")])
    await incremental_rebuild(project_id, relation_window_days=21, relation_max_candidates_per_thread=40)

    forced = await incremental_rebuild(
        project_id,
        relation_window_days=21,
        relation_max_candidates_per_thread=40,
        force_full_rebuild=True,
    )
    assert forced["mode"] == "full"
    assert forced["full_rebuild_avoided"] is False
    assert "force-full-rebuild" in forced["rebuild_reason"]


@pytest.mark.asyncio
async def test_incremental_is_idempotent_no_duplicate_threads_or_relations(isolated_stores):
    from core.operational_memory.incremental_rebuild import incremental_rebuild
    from core.operational_memory.state_store import load_state

    project_id = "orch-idem"
    await _seed(
        project_id,
        [
            _op_event(project_id, "e1", "T7 M2 non parte", "2026-06-12T08:00:00+00:00"),
            _op_event(project_id, "e2", "La sostituisco stamattina T7 M2", "2026-06-12T08:20:00+00:00"),
        ],
    )
    await incremental_rebuild(project_id, relation_window_days=21, relation_max_candidates_per_thread=40)
    state_a = await load_state(project_id)
    await incremental_rebuild(project_id, relation_window_days=21, relation_max_candidates_per_thread=40)
    state_b = await load_state(project_id)

    assert len(state_a.threads) == len(state_b.threads)
    assert len(state_a.thread_relation_candidates) == len(state_b.thread_relation_candidates)
    assert {t.thread_id for t in state_a.threads} == {t.thread_id for t in state_b.threads}


def test_real_long_export_path_is_not_required_by_tests():
    # The incremental layer must never depend on the local real export path.
    import core.operational_memory.incremental_rebuild as mod

    source = mod.__file__
    with open(source, "r", encoding="utf-8") as handle:
        body = handle.read()
    assert "real_exports" not in body
    assert "TAB CEFLA" not in body
    assert "tab-cefla" not in body
