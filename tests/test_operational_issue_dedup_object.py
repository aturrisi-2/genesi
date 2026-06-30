"""G5: issues about the same strong technical object evolve ONE issue instead
of spawning duplicates. Synthetic only; no LLM, no network.
"""
from core.operational_memory.state_engine import (
    merge_state,
    _same_strong_object,
    _merge_issues,
)
from core.operational_memory.models import OperationalState, Issue, LifecycleState


def _state(issues):
    return OperationalState(project_id="synthetic-001", issues=list(issues))


def _iss(text, eid="e"):
    return Issue(
        text=text,
        source="msg 1",
        confidence="high",
        source_event_id=eid,
        lifecycle=LifecycleState(
            category="issue", current_status="open", evidence_event_ids=[eid]
        ),
    )


# ---- object identity --------------------------------------------------------
def test_same_object_pompa_p1():
    assert _same_strong_object("Pompa P1 non parte", "Pompa P1 installata, ma da provare")
    assert _same_strong_object("Pompa P1 non parte", "La Pompa P1 si è fermata di nuovo")
    assert _same_strong_object("Pompa P1 non parte", "Pompa P1 collaudata e consegnata")


def test_different_objects_not_merged():
    assert not _same_strong_object("Pompa P1 non parte", "Pompa P2 non parte")
    assert not _same_strong_object("Intercetti Scala 2 L4", "Intercetti Scala 2 L5")


def test_generic_without_identifier_never_merges():
    assert not _same_strong_object("Quadro elettrico guasto", "Quadro QGBT cablato")
    assert not _same_strong_object("Materiale mancante", "Materiale linea UTA non ordinato")
    assert not _same_strong_object("Problema sul cantiere", "Altro problema sul cantiere")


# ---- merge behaviour --------------------------------------------------------
def test_three_pompa_p1_messages_collapse_to_one_issue():
    existing = _state([_iss("Pompa P1 non parte, manca verifica alimentazione.", "e1")])
    incoming = [
        _iss("Pompa P1 installata, ma da provare.", "e2"),
        _iss("La Pompa P1 si è fermata di nuovo.", "e3"),
    ]
    merged = _merge_issues(existing.issues, incoming)
    assert len(merged) == 1  # one evolving issue, no duplicates
    ev = merged[0].lifecycle.evidence_event_ids
    assert "e2" in ev and "e3" in ev  # history preserved


def test_pompa_p1_and_p2_stay_separate():
    existing = _state([_iss("Pompa P1 non parte", "e1")])
    merged = _merge_issues(existing.issues, [_iss("Pompa P2 non parte", "e2")])
    assert len(merged) == 2


def test_generic_issue_not_aggressively_merged():
    existing = _state([_iss("Quadro QGBT cablato, manca collaudo", "e1")])
    merged = _merge_issues(existing.issues, [_iss("Quadro elettrico da verificare", "e2")])
    assert len(merged) == 2  # no identifier with a digit → never folds


def test_exact_duplicate_text_still_deduped():
    existing = _state([_iss("Manca BDF e da rifare", "e1")])
    merged = _merge_issues(existing.issues, [_iss("Manca BDF e da rifare", "e1")])
    assert len(merged) == 1


def test_merge_state_issues_use_object_dedup():
    existing = _state([_iss("Pompa P1 non parte", "e1")])
    incoming = _state([_iss("Pompa P1 si è fermata di nuovo", "e2")])
    out = merge_state(existing, incoming)
    pompa = [i for i in out.issues if "p1" in i.text.lower()]
    assert len(pompa) == 1
