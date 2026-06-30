"""G4b: a later answer for the same strong object closes an open question and
binds the responsible to a co-object task. Synthetic only; no LLM, no network.
"""
from core.operational_memory.lifecycle_engine import apply_resolution_links, _PERSON_ANSWER_RE
from core.operational_memory.models import (
    OperationalState, OperationalQuestion, OperationalTask, OperationalEvent, LifecycleState,
)


def _ev(eid, mm, text):
    return OperationalEvent(event_id=eid, project_id="p",
                            timestamp=f"2026-06-30T10:{mm:02d}:00+00:00", content=text)


def _q(text, eid="q1"):
    return OperationalQuestion(text=text, source="msg 1", source_event_id=eid,
                               source_timestamp="2026-06-30T10:00:00+00:00",
                               lifecycle=LifecycleState(category="question", current_status="open",
                                                        evidence_event_ids=[eid]))


def _task(text):
    return OperationalTask(text=text, source="msg 1", source_timestamp="2026-06-30T10:00:30+00:00")


def _run(questions, tasks, events):
    s = OperationalState(project_id="p", open_questions=list(questions), tasks=list(tasks))
    apply_resolution_links(s, events)
    return s


# ---- person extraction ------------------------------------------------------
def test_person_extraction():
    def name(t):
        m = _PERSON_ANSWER_RE.search(t)
        return next((g for g in m.groups() if g), None) if m else None
    assert name("Il cavo FG16 lo porta Mario domani mattina") == "Mario"
    assert name("Mario porta il cavo FG16 domani") == "Mario"
    assert name("se ne occupa Luca") == "Luca"
    assert name("lo porta domani") is None  # temporal, not a person


# ---- closing the question ---------------------------------------------------
def test_answer_closes_question_and_sets_owner():
    s = _run([_q("Chi porta il cavo FG16?")], [_task("Portare il cavo FG16")],
             [_ev("q1", 0, "Chi porta il cavo FG16?"),
              _ev("a1", 1, "Il cavo FG16 lo porta Mario domani mattina")])
    q = s.open_questions[0]
    assert q.lifecycle.current_status == "answered"
    assert "a1" in q.lifecycle.evidence_event_ids and "q1" in q.lifecycle.evidence_event_ids
    assert s.tasks[0].owner == "Mario"


def test_answer_variant_subject_first():
    s = _run([_q("Chi porta il cavo FG16?")], [],
             [_ev("q1", 0, "Chi porta il cavo FG16?"),
              _ev("a1", 1, "Mario porta il cavo FG16 domani")])
    assert s.open_questions[0].lifecycle.current_status == "answered"


def test_quadro_qgbt_when_question_closed():
    s = _run([_q("Quando arriva il quadro QGBT2?")], [],
             [_ev("q1", 0, "Quando arriva il quadro QGBT2?"),
              _ev("a1", 1, "Il quadro QGBT2 arriva venerdì")])
    assert s.open_questions[0].lifecycle.current_status == "answered"


# ---- fail-safe --------------------------------------------------------------
def test_different_object_does_not_close():
    s = _run([_q("Chi porta il cavo FG16?")], [],
             [_ev("q1", 0, "Chi porta il cavo FG16?"),
              _ev("a1", 1, "Il cavo FG17 lo porta Mario")])
    assert s.open_questions[0].lifecycle.current_status == "open"


def test_ambiguous_two_questions_same_object_not_closed():
    s = _run([_q("Chi porta il cavo FG16?", "q1"), _q("Quando arriva il cavo FG16?", "q2")], [],
             [_ev("q1", 0, "Chi porta il cavo FG16?"),
              _ev("q2", 0, "Quando arriva il cavo FG16?"),
              _ev("a1", 1, "Il cavo FG16 lo porta Mario")])
    assert all(q.lifecycle.current_status == "open" for q in s.open_questions)


def test_generic_ok_does_not_close():
    s = _run([_q("Chi porta il cavo FG16?")], [],
             [_ev("q1", 0, "Chi porta il cavo FG16?"), _ev("a1", 1, "Ok")])
    assert s.open_questions[0].lifecycle.current_status == "open"


def test_no_owner_invented_when_no_person():
    s = _run([_q("Chi porta il cavo FG16?")], [_task("Portare il cavo FG16")],
             [_ev("q1", 0, "Chi porta il cavo FG16?"),
              _ev("a1", 1, "Il cavo FG16 arriva domani")])  # no person named
    # question may close on object+answer, but owner must NOT be invented
    assert s.tasks[0].owner is None
