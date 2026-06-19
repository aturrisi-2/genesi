from __future__ import annotations

import pytest

from core.operational_memory.models import (
    Decision,
    Information,
    Issue,
    LifecycleHistoryEntry,
    LifecycleState,
    OperationalLifecycleSnapshot,
    OperationalQuestion,
    OperationalState,
    OperationalTask,
    SnapshotDelta,
)
from core.operational_memory.query_engine import (
    active_decisions,
    answer_query,
    attention_items,
    build_digest,
    changed_since,
    classify_query_intent,
    open_issues,
    open_tasks,
    resolved_issues,
    superseded_items,
    unanswered_questions,
)


def _lc(category, status, evidence=None, confidence="medium", reason="r"):
    return LifecycleState(
        category=category,
        current_status=status,
        confidence=confidence,
        status_reason=reason,
        evidence_event_ids=evidence or ["ev1"],
        lifecycle_history=[LifecycleHistoryEntry(status=status, changed_at="2026-06-12T08:00:00+00:00")],
    )


def _task(i, status, **kw):
    return OperationalTask(id=i, text=f"task {i}", source="m", source_event_id=f"e{i}", lifecycle=_lc("task", status, **kw))


def _issue(i, status, **kw):
    return Issue(id=i, text=f"issue {i}", source="m", source_event_id=f"e{i}", lifecycle=_lc("issue", status, **kw))


def _decision(i, status, **kw):
    return Decision(id=i, text=f"decision {i}", source="m", source_event_id=f"e{i}", lifecycle=_lc("decision", status, **kw))


def _question(i, status, **kw):
    return OperationalQuestion(id=i, text=f"question {i}", source="m", source_event_id=f"e{i}", lifecycle=_lc("question", status, **kw))


def _state():
    return OperationalState(
        project_id="p",
        tasks=[_task("t1", "open"), _task("t2", "completed"), _task("t3", "in_progress")],
        issues=[_issue("i1", "open"), _issue("i2", "resolved"), _issue("i3", "reopened", confidence="high")],
        decisions=[_decision("d1", "confirmed"), _decision("d2", "superseded")],
        open_questions=[_question("q1", "open"), _question("q2", "answered"), _question("q3", "partially_answered")],
        information=[Information(id="info1", text="info one", source="m", source_event_id="e", lifecycle=_lc("information", "superseded"))],
    )


# --------------------------------------------------------------------------- #
# Structured queries
# --------------------------------------------------------------------------- #


def test_open_tasks_excludes_completed():
    items = open_tasks(_state())
    ids = {it.item_id for it in items}
    assert ids == {"t1", "t3"}


def test_open_vs_resolved_issues():
    state = _state()
    assert {it.item_id for it in open_issues(state)} == {"i1", "i3"}
    assert {it.item_id for it in resolved_issues(state)} == {"i2"}


def test_active_decisions_excludes_superseded():
    assert {it.item_id for it in active_decisions(_state())} == {"d1"}


def test_unanswered_includes_partial_excludes_answered():
    assert {it.item_id for it in unanswered_questions(_state())} == {"q1", "q3"}


def test_superseded_items_across_categories():
    ids = {it.item_id for it in superseded_items(_state())}
    assert "d2" in ids and "info1" in ids


def test_attention_items_includes_reopened_and_high_issue():
    ids = {it.item_id for it in attention_items(_state())}
    assert "i3" in ids  # reopened + high confidence


def test_changed_since_from_snapshot_delta():
    state = _state()
    snap = OperationalLifecycleSnapshot(project_id="p", generated_at="2026-06-19T10:00:00+00:00")
    snap.snapshot_delta = SnapshotDelta(newly_resolved=["[issue] issue i2"], newly_opened=["[task] task t1"])
    state.lifecycle_snapshot = snap
    changes = changed_since(state)
    texts = {c.text for c in changes}
    assert "[issue] issue i2" in texts and "[task] task t1" in texts


def test_evidence_and_reason_present():
    items = open_tasks(_state())
    assert all(it.evidence_event_ids for it in items)
    assert all(it.reason for it in items)


def test_digest_headline_counts():
    digest = build_digest(_state())
    assert "task aperti" in digest.headline
    assert len(digest.open_tasks) == 2
    assert len(digest.resolved_issues) == 1
    assert len(digest.active_decisions) == 1


# --------------------------------------------------------------------------- #
# NL intent routing
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("text,intent", [
    ("cosa resta da fare?", "open_tasks"),
    ("what's left to do?", "open_tasks"),
    ("quali problemi sono aperti?", "open_issues"),
    ("quali problemi sono stati risolti?", "resolved_issues"),
    ("quali decisioni sono attive?", "active_decisions"),
    ("cosa è cambiato da ieri?", "changed"),
    ("cosa è stato superato?", "superseded"),
    ("quali domande sono ancora senza risposta?", "unanswered"),
    ("cosa richiede attenzione?", "attention"),
    ("fammi il digest operativo", "digest"),
    ("riassumi lo stato del progetto", "digest"),
    ("ciao tutto bene", "unknown"),
])
def test_intent_classification(text, intent):
    assert classify_query_intent(text) == intent


def test_answer_query_dispatch_and_unknown():
    state = _state()
    res = answer_query(state, "cosa resta da fare?")
    assert res.intent == "open_tasks" and res.count == 2 and res.items
    unknown = answer_query(state, "qual è il senso della vita")
    assert unknown.intent == "unknown" and unknown.items == []
    assert "Domanda non riconosciuta" in unknown.summary


def test_answer_query_digest():
    res = answer_query(_state(), "dammi un riassunto")
    assert res.intent == "digest" and "task aperti" in res.summary


# --------------------------------------------------------------------------- #
# Multi-domain + no hardcoding
# --------------------------------------------------------------------------- #


def test_multidomain_text_agnostic():
    # Queries depend on lifecycle status, not on domain words in the text.
    state = OperationalState(
        project_id="p",
        tasks=[
            OperationalTask(id="log", text="consegnare il pacco al deposito", source="m", source_event_id="e1", lifecycle=_lc("task", "open")),
            OperationalTask(id="fam", text="comprare il latte", source="m", source_event_id="e2", lifecycle=_lc("task", "completed")),
            OperationalTask(id="cs", text="rispondere al ticket cliente", source="m", source_event_id="e3", lifecycle=_lc("task", "in_progress")),
            OperationalTask(id="con", text="montare la struttura", source="m", source_event_id="e4", lifecycle=_lc("task", "blocked")),
        ],
    )
    ids = {it.item_id for it in open_tasks(state)}
    assert ids == {"log", "cs", "con"}  # completed excluded, all domains handled


def test_no_hardcoded_domain_tokens_in_query_module():
    import re as _re

    import core.operational_memory.query_engine as mod

    body = open(mod.__file__, "r", encoding="utf-8").read().upper()
    for token in ["TAB CEFLA", "TAB-CEFLA", "T6", "T7", "EWC05", "SS01", "B02", "UTA", "CANTIERE", "WHATSAPP"]:
        assert not _re.search(rf"\b{_re.escape(token)}\b", body), f"hardcoded token leaked: {token}"
