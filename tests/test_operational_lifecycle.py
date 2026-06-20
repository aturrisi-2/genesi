from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.operational_memory.lifecycle_engine import (
    Evidence,
    apply_lifecycle_transitions,
    build_operational_snapshot,
    detect_reopen_signal,
    detect_resolution_signal,
    detect_supersession,
    infer_decision_transition,
    infer_information_transition,
    infer_issue_transition,
    infer_question_transition,
    infer_task_transition,
)
from core.operational_memory.models import (
    Decision,
    Information,
    Issue,
    OperationalEvent,
    OperationalQuestion,
    OperationalState,
    OperationalTask,
    OperationalThread,
)


NOW = datetime(2026, 6, 12, 18, 0, tzinfo=timezone.utc)


def _ev(eid: str, text: str, ts: str) -> Evidence:
    return Evidence(event_id=eid, text=text, timestamp=ts)


# --------------------------------------------------------------------------- #
# Signal detectors — generic, multilingual
# --------------------------------------------------------------------------- #


def test_resolution_signal_excludes_negation():
    assert detect_resolution_signal("ora funziona") is True
    assert detect_resolution_signal("done, fixed") is True
    assert detect_resolution_signal("non funziona") is False
    assert detect_resolution_signal("still not working") is False


def test_reopen_and_supersession_signals():
    assert detect_reopen_signal("non funziona ancora") is True
    assert detect_reopen_signal("il problema è tornato") is True
    assert detect_supersession("invece usiamo il nuovo valore") is True
    assert detect_supersession("update: replaced with B") is True


# --------------------------------------------------------------------------- #
# Per-category transitions
# --------------------------------------------------------------------------- #


def test_task_completion():
    t = infer_task_transition("open", [_ev("e2", "fatto, completato", "2026-06-12T09:00:00+00:00")], NOW)
    assert t is not None and t.new_status == "completed"
    assert t.evidence_event_ids == ["e2"]


def test_issue_resolution():
    t = infer_issue_transition("open", [_ev("e2", "ora funziona tutto", "2026-06-12T09:00:00+00:00")], NOW)
    assert t is not None and t.new_status == "resolved"


def test_issue_remains_open_without_resolution():
    # No resolution evidence -> stays open, never resolved.
    t = infer_issue_transition("open", [_ev("e2", "non funziona ancora", "2026-06-12T09:00:00+00:00")], NOW)
    assert t is None or t.new_status != "resolved"


def test_issue_reopen_after_resolution():
    t = infer_issue_transition("resolved", [_ev("e2", "non funziona di nuovo", "2026-06-12T10:00:00+00:00")], NOW)
    assert t is not None and t.new_status == "reopened"
    assert t.reopened_by == "e2"


def test_decision_supersession():
    t = infer_decision_transition("confirmed", [_ev("e2", "aggiornamento: invece usiamo B", "2026-06-12T10:00:00+00:00")], NOW)
    assert t is not None and t.new_status == "superseded"
    assert t.superseded_by == "e2"


def test_information_supersession():
    t = infer_information_transition("current", [_ev("e2", "nuovo valore, sostituito", "2026-06-12T10:00:00+00:00")], NOW)
    assert t is not None and t.new_status == "superseded"


def test_question_answered():
    t = infer_question_transition("open", [_ev("e2", "la risposta e' lunedì alle 9", "2026-06-12T10:00:00+00:00")], NOW)
    assert t is not None and t.new_status == "answered"


def test_stale_not_confused_with_resolved():
    # A neutral later message (no closure/supersession/reopen signal) must let the
    # item decay to stale, not be mistaken for resolution. ("ricevuto"/"confermato"
    # are now genuine closure signals and are covered separately.)
    old = [_ev("e2", "ci sentiamo", "2026-05-01T09:00:00+00:00")]
    reference = datetime(2026, 6, 1, 9, 0, tzinfo=timezone.utc)
    t = infer_task_transition("open", old, reference, stale_after_days=14)
    assert t is not None and t.new_status == "stale"
    assert t.new_status != "resolved" and t.new_status != "completed"


# --------------------------------------------------------------------------- #
# State-level apply, evidence explanation, incremental
# --------------------------------------------------------------------------- #


def _event(eid: str, content: str, ts: str) -> OperationalEvent:
    return OperationalEvent(event_id=eid, project_id="lc", sender="x", timestamp=ts, content=content, processed_status="processed")


def _thread(tid: str, event_ids: list[str]) -> OperationalThread:
    return OperationalThread(
        thread_id=tid,
        project_id="lc",
        title="t",
        started_at="2026-06-12T08:00:00+00:00",
        last_updated_at="2026-06-12T10:00:00+00:00",
        project_impact_score=80,
        related_event_ids=event_ids,
    )


def _state_with_task(item_text: str, e1: str, e2_text: str) -> tuple[OperationalState, list[OperationalEvent], list[OperationalThread]]:
    task = OperationalTask(id="task_1", text=item_text, source="msg", source_event_id=e1, source_timestamp="2026-06-12T08:00:00+00:00")
    state = OperationalState(project_id="lc", tasks=[task])
    events = [_event(e1, item_text, "2026-06-12T08:00:00+00:00"), _event("e2", e2_text, "2026-06-12T09:00:00+00:00")]
    threads = [_thread("th1", [e1, "e2"])]
    return state, events, threads


def test_apply_records_evidence_and_reason():
    state, events, threads = _state_with_task("montare il pannello", "e1", "pannello montato, fatto")
    transitions = apply_lifecycle_transitions(state, events, threads=threads, reference_now=NOW)
    assert len(transitions) == 1
    lc = state.tasks[0].lifecycle
    assert lc is not None
    assert lc.current_status == "completed"
    assert lc.previous_status == "open"
    assert lc.evidence_event_ids == ["e2"]
    assert lc.status_reason
    assert lc.lifecycle_history[-1].status == "completed"


def test_incremental_only_dirty_item_updates():
    # Two independent tasks/threads. First apply seeds both.
    t1 = OperationalTask(id="t1", text="task uno da fare", source="m", source_event_id="a1", source_timestamp="2026-06-12T08:00:00+00:00")
    t2 = OperationalTask(id="t2", text="task due da fare", source="m", source_event_id="b1", source_timestamp="2026-06-12T08:00:00+00:00")
    state = OperationalState(project_id="lc", tasks=[t1, t2])
    events = [_event("a1", "task uno da fare", "2026-06-12T08:00:00+00:00"), _event("b1", "task due da fare", "2026-06-12T08:00:00+00:00")]
    threads = [_thread("tha", ["a1"]), _thread("thb", ["b1"])]
    apply_lifecycle_transitions(state, events, threads=threads, reference_now=NOW)
    assert state.tasks[0].lifecycle.current_status == "open"
    assert state.tasks[1].lifecycle.current_status == "open"

    # New evidence completing only task uno; mark only t1 dirty.
    events.append(_event("a2", "task uno fatto e verificato", "2026-06-12T09:00:00+00:00"))
    threads[0].related_event_ids = ["a1", "a2"]
    transitions = apply_lifecycle_transitions(
        state, events, threads=threads, dirty_item_ids={"t1"}, reference_now=NOW
    )
    assert {r.item_id for r in transitions} == {"t1"}
    assert state.tasks[0].lifecycle.current_status == "verified"
    assert state.tasks[1].lifecycle.current_status == "open"  # untouched


def test_snapshot_separates_active_from_resolved():
    state, events, threads = _state_with_task("riparare la pompa", "e1", "pompa riparata, funziona")
    transitions = apply_lifecycle_transitions(state, events, threads=threads, reference_now=NOW)
    snapshot = build_operational_snapshot(state, transitions)
    assert "riparare la pompa" in snapshot.completed_tasks
    assert "riparare la pompa" not in snapshot.active_tasks
    assert snapshot.delta.newly_completed


# --------------------------------------------------------------------------- #
# Multi-domain — generic transitions, no construction-only fixtures
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "category,item_text,evidence_text,expected",
    [
        # logistics
        ("task", "serve materiale in cantiere", "materiale consegnato", "completed"),
        ("issue", "spedizione bloccata al deposito", "spedizione sbloccata, ora funziona", "resolved"),
        # family
        ("task", "comprare il latte", "latte comprato, fatto", "completed"),
        ("question", "a che ora è la cena?", "la cena è alle 20", "answered"),
        # customer_support
        ("issue", "il login non funziona per il cliente", "login ripristinato, funziona", "resolved"),
        ("decision", "usiamo il piano base", "invece passiamo al piano premium", "superseded"),
        # construction (generico)
        ("task", "montare la struttura", "struttura montata e verificata", "verified"),
        ("issue", "infiltrazione al piano terra", "infiltrazione risolta", "resolved"),
    ],
)
def test_multidomain_transitions(category, item_text, evidence_text, expected):
    infer = {
        "task": infer_task_transition,
        "issue": infer_issue_transition,
        "decision": infer_decision_transition,
        "question": infer_question_transition,
        "information": infer_information_transition,
    }[category]
    from core.operational_memory.lifecycle_engine import initial_status

    start = initial_status(category, item_text)
    t = infer(start, [_ev("e2", evidence_text, "2026-06-12T10:00:00+00:00")], NOW)
    assert t is not None and t.new_status == expected


def test_no_hardcoded_domain_tokens():
    import core.operational_memory.lifecycle_engine as mod

    body = open(mod.__file__, "r", encoding="utf-8").read().upper()
    for token in ["TAB CEFLA", "TAB-CEFLA", " T6 ", " T7 ", "UTA", "EWC05", "SS01", "B02", "CANTIERE", "WHATSAPP"]:
        assert token not in body, f"hardcoded token leaked: {token}"
