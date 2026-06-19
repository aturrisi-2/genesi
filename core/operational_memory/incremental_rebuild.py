from __future__ import annotations

import time
from datetime import datetime, timezone

from core.log import log
from core.operational_memory.chat_profile_engine import build_adaptive_chat_profile
from core.operational_memory.event_store import list_events, save_events
from core.operational_memory.incremental_index import (
    IncrementalIndex,
    load_index,
    save_index,
    touch_macro_rebuild,
    touch_relation_rebuild,
    touch_thread_rebuild,
)
from core.operational_memory.macro_thread_engine import (
    build_macro_threads,
    incremental_build_macro_threads,
)
from core.operational_memory.models import OperationalThread, utc_now_iso
from core.operational_memory.state_store import load_state, save_state
from core.operational_memory.thread_engine import incremental_update_threads
from core.operational_memory.thread_relation_engine import (
    _canonical_terms,
    build_thread_relation_candidates,
    canonical_term_distribution_report,
    incremental_thread_relation_candidates,
)


def _dirty_canonical_terms(
    threads: list[OperationalThread],
    dirty_thread_ids: set[str],
    profile,
) -> set[str]:
    terms: set[str] = set()
    for thread in threads:
        if thread.thread_id in dirty_thread_ids:
            terms |= _canonical_terms(thread, profile)
    return terms


async def incremental_rebuild(
    project_id: str,
    relation_window_days: int,
    relation_max_candidates_per_thread: int,
    force_full_rebuild: bool = False,
    stale_days: int = 7,
) -> dict:
    """Update threads, macros and relation candidates incrementally.

    Only the events not yet folded into the thread layer drive the work. When
    nothing is dirty (e.g. a resume run with zero new events) no global rebuild
    runs at all. ``force_full_rebuild`` falls back to the exhaustive path.

    Returns a metrics dict including timings, dirty counts and reuse counters."""
    index = load_index(project_id)
    events = await list_events(project_id)
    state = await load_state(project_id)
    existing_threads = list(state.threads)
    existing_macros = list(state.macro_threads)
    existing_relations = list(state.thread_relation_candidates)
    # Seed the known-set from events already folded into existing threads. This
    # makes the first incremental run on a project that was previously built by
    # the full pipeline (empty index, populated state) idempotent instead of
    # re-attaching every event.
    known_event_ids = index.known_set() | {
        event_id for thread in existing_threads for event_id in thread.related_event_ids
    }

    processed_event_ids = {
        event.event_id for event in events if event.processed_status == "processed"
    }
    new_event_ids_present = processed_event_ids - known_event_ids

    rebuild_reason = ""
    full_rebuild = force_full_rebuild
    if not full_rebuild:
        if not existing_threads and processed_event_ids:
            full_rebuild = True
            rebuild_reason = "nessun thread index persistito: primo rebuild"
        elif index.full_rebuild_required:
            full_rebuild = True
            rebuild_reason = index.rebuild_reason or "full_rebuild_required flag attivo"
    elif force_full_rebuild:
        rebuild_reason = "richiesto esplicitamente con --force-full-rebuild"

    timings: dict[str, float] = {}
    metrics: dict = {
        "mode": "full" if full_rebuild else "incremental",
        "full_rebuild": full_rebuild,
        "full_rebuild_avoided": not full_rebuild,
        "rebuild_reason": rebuild_reason,
        "events_processed_this_run": 0,
        "dirty_threads": 0,
        "dirty_canonical_terms": 0,
        "dirty_relation_pairs": 0,
        "relation_pairs_recalculated": 0,
        "relation_pairs_reused": 0,
        "macros_rebuilt": 0,
        "macros_reused": 0,
    }

    if full_rebuild:
        from core.operational_memory.thread_engine import build_threads_from_events

        started = time.perf_counter()
        threads, updated_events = build_threads_from_events(project_id, events, state, stale_days=stale_days)
        timings["thread_engine_seconds"] = time.perf_counter() - started

        started = time.perf_counter()
        profile = build_adaptive_chat_profile(project_id, updated_events, threads)
        timings["profile_seconds"] = time.perf_counter() - started

        started = time.perf_counter()
        macros = build_macro_threads(project_id, threads, updated_events, profile)
        timings["macro_engine_seconds"] = time.perf_counter() - started

        started = time.perf_counter()
        relation_stats: dict = {}
        relations = build_thread_relation_candidates(
            project_id,
            threads,
            updated_events,
            profile,
            relation_window_days=relation_window_days,
            relation_max_candidates_per_thread=relation_max_candidates_per_thread,
            stats=relation_stats,
        )
        timings["relation_engine_seconds"] = time.perf_counter() - started
        dirty_thread_ids = {thread.thread_id for thread in threads}
        new_event_ids = list(new_event_ids_present)
        metrics["relation_pairs_recalculated"] = relation_stats.get("kept_pairs", len(relations))
    else:
        started = time.perf_counter()
        threads, updated_events, dirty_thread_ids, new_event_ids = incremental_update_threads(
            project_id,
            events,
            state,
            existing_threads,
            known_event_ids,
            stale_days=stale_days,
        )
        timings["thread_engine_seconds"] = time.perf_counter() - started

        started = time.perf_counter()
        profile = build_adaptive_chat_profile(project_id, updated_events, threads)
        timings["profile_seconds"] = time.perf_counter() - started

        dirty_terms = _dirty_canonical_terms(threads, dirty_thread_ids, profile)

        started = time.perf_counter()
        macro_stats: dict = {}
        macros = incremental_build_macro_threads(
            project_id,
            threads,
            dirty_thread_ids,
            dirty_terms,
            existing_macros,
            updated_events,
            profile,
            stats=macro_stats,
        )
        timings["macro_engine_seconds"] = time.perf_counter() - started

        started = time.perf_counter()
        relation_stats = {}
        relations = incremental_thread_relation_candidates(
            project_id,
            threads,
            dirty_thread_ids,
            existing_relations,
            updated_events,
            profile,
            relation_window_days=relation_window_days,
            relation_max_candidates_per_thread=relation_max_candidates_per_thread,
            stats=relation_stats,
        )
        timings["relation_engine_seconds"] = time.perf_counter() - started

        metrics["dirty_canonical_terms"] = len(dirty_terms)
        metrics["dirty_relation_pairs"] = relation_stats.get("raw_pairs", 0)
        metrics["relation_pairs_recalculated"] = relation_stats.get("relation_pairs_recalculated", 0)
        metrics["relation_pairs_reused"] = relation_stats.get("relation_pairs_reused", 0)
        metrics["macros_rebuilt"] = macro_stats.get("macros_rebuilt", 0)
        metrics["macros_reused"] = macro_stats.get("macros_reused", 0)

    metrics["events_processed_this_run"] = len(new_event_ids)
    metrics["dirty_threads"] = len(dirty_thread_ids)

    # Persist state.
    state.threads = threads
    state.adaptive_chat_profile = profile
    state.macro_threads = macros
    state.thread_relation_candidates = relations
    await save_events(project_id, updated_events)
    await save_state(project_id, state)

    # Persist index.
    index.event_thread_map = {
        event.event_id: event.thread_id
        for event in updated_events
        if event.thread_id
    }
    index.known_event_ids = sorted(processed_event_ids)
    index.relation_pair_keys = sorted(
        "|".join(sorted([relation.source_thread_id, relation.target_thread_id]))
        for relation in relations
    )
    index.macro_child_map = {
        macro.macro_thread_id: sorted(macro.child_thread_ids) for macro in macros
    }
    index.canonical_distribution = {
        row["label"]: row["thread_coverage"]
        for row in canonical_term_distribution_report(threads, profile)
    }
    touch_thread_rebuild(index)
    touch_relation_rebuild(index)
    touch_macro_rebuild(index)
    index.full_rebuild_required = False
    index.rebuild_reason = rebuild_reason
    index.last_run = {**metrics, "timings": timings, "at": utc_now_iso()}
    save_index(project_id, index)

    canonical_report = canonical_term_distribution_report(threads, profile)
    metrics["timings"] = timings
    metrics["relation_stats"] = relation_stats
    metrics["canonical_distribution"] = canonical_report
    metrics["broad_canonical_terms"] = [row for row in canonical_report if row["broad_canonical_term"]]
    metrics["weak_context_terms"] = [row for row in canonical_report if row["weak_context_term"]]
    log(
        "OPERATIONAL_INCREMENTAL_REBUILD",
        project_id=project_id,
        mode=metrics["mode"],
        events_processed=metrics["events_processed_this_run"],
        dirty_threads=metrics["dirty_threads"],
        full_rebuild_avoided=metrics["full_rebuild_avoided"],
    )
    return metrics
