from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.operational_memory.lifecycle_engine import (
    Evidence,
    apply_cross_item_transitions,
    apply_lifecycle_transitions,
    detect_operational_contradiction,
    score_supersession_candidate,
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
T1 = "2026-06-12T08:00:00+00:00"
T2 = "2026-06-12T09:00:00+00:00"


def _event(eid: str, content: str, ts: str) -> OperationalEvent:
    return OperationalEvent(event_id=eid, project_id="lc", sender="x", timestamp=ts, content=content, processed_status="processed")


def _thread(tid: str, event_ids: list[str], macro: str | None = None) -> OperationalThread:
    return OperationalThread(
        thread_id=tid,
        project_id="lc",
        title="t",
        started_at=T1,
        last_updated_at=T2,
        project_impact_score=80,
        related_event_ids=event_ids,
        macro_thread_id=macro,
    )


_MODEL = {"task": OperationalTask, "issue": Issue, "decision": Decision, "question": OperationalQuestion, "information": Information}
_FIELD = {"task": "tasks", "issue": "issues", "decision": "decisions", "question": "open_questions", "information": "information"}


def _two_item_state(category, older_text, newer_text, sender_a="ann", sender_b="bob", ts1=T1, ts2=T2, same_thread=True):
    model = _MODEL[category]
    older = model(id="old", text=older_text, source="m", source_event_id="e1", source_timestamp=ts1)
    newer = model(id="new", text=newer_text, source="m", source_event_id="e2", source_timestamp=ts2)
    state = OperationalState(project_id="lc")
    setattr(state, _FIELD[category], [older, newer])
    events = [_event("e1", older_text, ts1), _event("e2", newer_text, ts2)]
    events[0].sender = sender_a
    events[1].sender = sender_b
    if same_thread:
        threads = [_thread("th1", ["e1", "e2"])]
    else:
        threads = [_thread("tha", ["e1"]), _thread("thb", ["e2"])]
    return state, events, threads, older, newer


# --------------------------------------------------------------------------- #
# Cross-item supersession / contradiction
# --------------------------------------------------------------------------- #


def test_decision_supersession_same_thread():
    state, events, threads, older, newer = _two_item_state(
        "decision", "domani facciamo il sopralluogo", "invece domani facciamo la consegna"
    )
    transitions = apply_cross_item_transitions(state, events, threads=threads, reference_now=NOW)
    assert older.lifecycle.current_status == "superseded"
    assert transitions and transitions[0].transition_kind == "supersession"
    assert transitions[0].evidence_event_ids and transitions[0].reason
    assert transitions[0].related_item_id == "new"


def test_information_supersession_value_update():
    state, events, threads, older, newer = _two_item_state(
        "information", "il materiale arriva venerdì", "il materiale arriva lunedì"
    )
    transitions = apply_cross_item_transitions(state, events, threads=threads, reference_now=NOW)
    assert older.lifecycle.current_status == "superseded"
    assert transitions[0].transition_kind == "contradiction"
    assert transitions[0].evidence_event_ids


def test_task_cancellation_supersession():
    state, events, threads, older, newer = _two_item_state(
        "task", "serve inviare il documento contrattuale", "il documento contrattuale non serve più, inviato altro"
    )
    transitions = apply_cross_item_transitions(state, events, threads=threads, reference_now=NOW)
    assert older.lifecycle.current_status in {"cancelled", "superseded"}
    assert transitions and transitions[0].evidence_event_ids


def test_issue_contradiction_resolves_via_single_item():
    # "non funziona" then "funziona" handled by per-item evidence path.
    issue = Issue(id="i1", text="il sistema non funziona", source="m", source_event_id="e1", source_timestamp=T1)
    state = OperationalState(project_id="lc", issues=[issue])
    events = [_event("e1", "il sistema non funziona", T1), _event("e2", "ora il sistema funziona", T2)]
    threads = [_thread("th1", ["e1", "e2"])]
    apply_lifecycle_transitions(state, events, threads=threads, reference_now=NOW)
    assert state.issues[0].lifecycle.current_status == "resolved"


def test_issue_reopen_sequence():
    issue = Issue(id="i1", text="il portale non funziona", source="m", source_event_id="e1", source_timestamp=T1)
    state = OperationalState(project_id="lc", issues=[issue])
    events = [
        _event("e1", "il portale non funziona", T1),
        _event("e2", "ora funziona", T2),
        _event("e3", "non funziona di nuovo", "2026-06-12T10:00:00+00:00"),
    ]
    threads = [_thread("th1", ["e1", "e2", "e3"])]
    apply_lifecycle_transitions(state, events, threads=threads, reference_now=NOW)
    assert state.issues[0].lifecycle.current_status == "reopened"


def test_question_partially_answered():
    q = OperationalQuestion(id="q1", text="quando arriva il materiale e chi lo porta?", source="m", source_event_id="e1", source_timestamp=T1)
    state = OperationalState(project_id="lc", open_questions=[q])
    events = [_event("e1", "quando arriva il materiale e chi lo porta?", T1), _event("e2", "arriva domani", T2)]
    threads = [_thread("th1", ["e1", "e2"])]
    apply_lifecycle_transitions(state, events, threads=threads, reference_now=NOW)
    assert state.open_questions[0].lifecycle.current_status == "partially_answered"


def test_issue_mitigated_not_resolved():
    issue = Issue(id="i1", text="il flusso è bloccato", source="m", source_event_id="e1", source_timestamp=T1)
    state = OperationalState(project_id="lc", issues=[issue])
    events = [_event("e1", "il flusso è bloccato", T1), _event("e2", "per ora abbiamo un workaround temporaneo", T2)]
    threads = [_thread("th1", ["e1", "e2"])]
    apply_lifecycle_transitions(state, events, threads=threads, reference_now=NOW)
    assert state.issues[0].lifecycle.current_status == "mitigated"


# --------------------------------------------------------------------------- #
# False-positive guards
# --------------------------------------------------------------------------- #


def test_no_supersession_for_different_objects():
    state, events, threads, older, newer = _two_item_state(
        "task", "controllare la pompa principale", "controllare il quadro elettrico"
    )
    transitions = apply_cross_item_transitions(state, events, threads=threads, reference_now=NOW)
    assert transitions == []
    assert older.lifecycle is None or older.lifecycle.current_status not in {"superseded", "cancelled"}


def test_same_author_alone_does_not_supersede():
    # Same author, different unrelated objects -> no supersession.
    state, events, threads, older, newer = _two_item_state(
        "information", "report mensile inviato al cliente", "riunione fissata in sede", sender_a="sam", sender_b="sam"
    )
    transitions = apply_cross_item_transitions(state, events, threads=threads, reference_now=NOW)
    assert transitions == []


def test_temporal_proximity_alone_does_not_supersede():
    # Different threads, no relation, close in time -> not even scanned.
    state, events, threads, older, newer = _two_item_state(
        "decision", "approvato il budget marketing", "scelto il fornitore logistico",
        ts1=T1, ts2="2026-06-12T08:01:00+00:00", same_thread=False,
    )
    metrics: dict = {}
    transitions = apply_cross_item_transitions(state, events, threads=threads, reference_now=NOW, metrics=metrics)
    assert transitions == []
    assert metrics["cross_item_pairs_scanned"] == 0


# --------------------------------------------------------------------------- #
# Incremental gating + scoring + detectors
# --------------------------------------------------------------------------- #


def test_incremental_only_dirty_pairs_scanned():
    state, events, threads, older, newer = _two_item_state(
        "decision", "usiamo il piano base", "invece usiamo il piano premium"
    )
    metrics: dict = {}
    # Neither dirty -> pair reused, not scanned, no transition.
    apply_cross_item_transitions(state, events, threads=threads, dirty_item_ids=set(), reference_now=NOW, metrics=metrics)
    assert metrics["cross_item_pairs_scanned"] == 0
    assert metrics["cross_item_pairs_reused"] >= 1
    assert older.lifecycle is None or older.lifecycle.current_status != "superseded"

    # Mark newer dirty -> scanned + applied.
    metrics2: dict = {}
    apply_cross_item_transitions(state, events, threads=threads, dirty_item_ids={"new"}, reference_now=NOW, metrics=metrics2)
    assert metrics2["cross_item_pairs_scanned"] >= 1
    assert metrics2["supersessions_detected"] == 1
    assert older.lifecycle.current_status == "superseded"


def test_detect_and_score_helpers():
    assert detect_operational_contradiction("arriva venerdì il pacco", "arriva lunedì il pacco")[0] == "contradiction"
    assert detect_operational_contradiction("usiamo A", "invece usiamo B")[0] == "supersession"
    assert detect_operational_contradiction("pompa rossa", "quadro blu") is None
    assert score_supersession_candidate(True, "", False, 2, True) >= 0.5
    assert score_supersession_candidate(False, "", False, 1, False) < 0.5


# --------------------------------------------------------------------------- #
# Multi-domain
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "category,older_text,newer_text,expected_kind",
    [
        # logistics
        ("information", "la spedizione parte martedì dal deposito", "aggiornamento: la spedizione parte giovedì dal deposito", "supersession"),
        # family
        ("decision", "sabato andiamo dai nonni", "no, sabato andiamo al mare invece", "supersession"),
        # customer_support
        ("information", "il ticket cliente è a priorità 2", "il ticket cliente ora è a priorità 4", "contradiction"),
        # construction (generico)
        ("task", "serve ordinare il cemento", "il cemento non serve più, ordinato altro materiale", "contradiction"),
    ],
)
def test_multidomain_cross_item(category, older_text, newer_text, expected_kind):
    state, events, threads, older, newer = _two_item_state(category, older_text, newer_text)
    transitions = apply_cross_item_transitions(state, events, threads=threads, reference_now=NOW)
    assert transitions, f"no transition for {category}"
    assert transitions[0].transition_kind == expected_kind
    assert older.lifecycle.current_status in {"superseded", "revoked", "cancelled", "resolved"}


def test_no_hardcoded_domain_tokens_in_lifecycle_module():
    import core.operational_memory.lifecycle_engine as mod

    body = open(mod.__file__, "r", encoding="utf-8").read().upper()
    for token in ["TAB CEFLA", "TAB-CEFLA", " T6 ", " T7 ", "EWC05", "SS01", "B02", "CANTIERE", "WHATSAPP"]:
        assert token not in body, f"hardcoded token leaked: {token}"
