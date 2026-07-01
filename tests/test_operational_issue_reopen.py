"""G4a: a resolved issue reopens on a later regression event ("si è fermata di
nuovo") for the same strong object, with full evidence linking. Synthetic only.
"""
from core.operational_memory.lifecycle_engine import apply_resolution_links
from core.operational_memory.models import OperationalState, Issue, OperationalEvent, LifecycleState

T0 = "2026-06-30T10:00:00+00:00"


def _ev(eid, mm, text):
    return OperationalEvent(event_id=eid, project_id="p",
                            timestamp=f"2026-06-30T10:{mm:02d}:00+00:00", content=text)


def _issue(text, eid="e1"):
    return Issue(text=text, source="msg 1", source_event_id=eid, source_timestamp=T0,
                 lifecycle=LifecycleState(category="issue", current_status="open",
                                          evidence_event_ids=[eid]))


def _run(issue_text, events):
    s = OperationalState(project_id="p", issues=[_issue(issue_text)])
    apply_resolution_links(s, events)
    return s.issues


def test_full_cycle_open_partial_resolved_reopened():
    events = [
        _ev("e1", 0, "Pompa PX10 non parte, manca verifica alimentazione"),
        _ev("e2", 1, "Pompa PX10 installata, ma da provare"),       # partial, no close
        _ev("e3", 2, "Pompa PX10 collaudata e consegnata al cliente"),  # strong close
        _ev("e4", 3, "In realtà la Pompa PX10 si è fermata di nuovo"),   # reopen
    ]
    iss = _run("Pompa PX10 non parte, manca verifica alimentazione", events)
    assert len(iss) == 1
    lc = iss[0].lifecycle
    assert lc.current_status == "reopened"
    assert lc.reopened_by == "e4"
    # evidence linking: initial + resolved + reopen
    assert {"e1", "e3", "e4"} <= set(lc.evidence_event_ids)


def test_reopen_variants_after_resolved():
    for reopen_text in ("Pompa PX10 problema ripresentato",
                        "Pompa PX10 ancora non parte",
                        "di nuovo non parte la Pompa PX10"):
        events = [
            _ev("e1", 0, "Pompa PX10 non parte"),
            _ev("e3", 2, "Pompa PX10 collaudata e consegnata"),
            _ev("e4", 3, reopen_text),
        ]
        iss = _run("Pompa PX10 non parte", events)
        assert iss[0].lifecycle.current_status == "reopened", reopen_text


def test_partial_does_not_resolve():
    events = [_ev("e1", 0, "Pompa PX10 non parte"),
              _ev("e2", 1, "Pompa PX10 installata, ma da provare")]
    iss = _run("Pompa PX10 non parte", events)
    assert iss[0].lifecycle.current_status != "resolved"


def test_strong_close_resolves():
    events = [_ev("e1", 0, "Pompa PX10 non parte"),
              _ev("e3", 2, "Pompa PX10 collaudata e consegnata al cliente")]
    iss = _run("Pompa PX10 non parte", events)
    assert iss[0].lifecycle.current_status == "resolved"


def test_different_object_does_not_reopen():
    # PX8 regression must NOT reopen a resolved PX10 issue.
    events = [_ev("e1", 0, "Pompa PX10 non parte"),
              _ev("e3", 2, "Pompa PX10 collaudata e consegnata"),
              _ev("e4", 3, "Pompa PX8 si è fermata di nuovo")]
    iss = _run("Pompa PX10 non parte", events)
    assert iss[0].lifecycle.current_status == "resolved"  # PX10 stays closed


def test_generic_di_nuovo_without_object_does_not_reopen():
    # bare "di nuovo" with no shared strong object → no reopen
    events = [_ev("e1", 0, "Pompa PX10 non parte"),
              _ev("e3", 2, "Pompa PX10 collaudata e consegnata"),
              _ev("e4", 3, "di nuovo problemi sul cantiere")]
    iss = _run("Pompa PX10 non parte", events)
    assert iss[0].lifecycle.current_status == "resolved"


# ---------------------------------------------------------------------------
# B4 — Idempotency: lifecycle_history must not grow on repeated rebuild calls
# ---------------------------------------------------------------------------

def _make_state_reopened():
    """Return a fresh state with one PX11 issue already in 'reopened' state
    (simulating what the DB holds after the first successful rebuild)."""
    from core.operational_memory.models import LifecycleHistoryEntry
    issue = _issue("Pompa PX11 non funziona", eid="e0")
    issue.lifecycle.current_status = "reopened"
    issue.lifecycle.previous_status = "resolved"
    issue.lifecycle.evidence_event_ids = ["e0", "e_close", "e_reopen"]
    issue.lifecycle.lifecycle_history = [
        LifecycleHistoryEntry(status="open",     changed_at=T0, reason="init",          evidence_event_ids=["e0"]),
        LifecycleHistoryEntry(status="resolved", changed_at=T0, reason="chiusura",      evidence_event_ids=["e_close"]),
        LifecycleHistoryEntry(status="reopened", changed_at=T0, reason="regressione",   evidence_event_ids=["e_reopen"]),
    ]
    return OperationalState(project_id="p", issues=[issue])


def _events_px11():
    return [
        _ev("e0",      0, "Pompa PX11 non funziona"),
        _ev("e_close", 2, "Pompa PX11 collaudata e consegnata"),
        _ev("e_reopen",3, "Pompa PX11 si è fermata di nuovo"),
    ]


def test_repeated_rebuild_does_not_grow_history():
    """apply_resolution_links called 5 times on same state → history stays at 3."""
    s = _make_state_reopened()
    events = _events_px11()
    for _ in range(5):
        apply_resolution_links(s, events)
    lc = s.issues[0].lifecycle
    assert lc.current_status == "reopened"
    assert len(lc.lifecycle_history) == 3, (
        f"Expected 3 history entries, got {len(lc.lifecycle_history)}: "
        + str([h.status for h in lc.lifecycle_history])
    )


def test_repeated_rebuild_status_stable():
    """Final status must remain 'reopened' regardless of rebuild count."""
    s = _make_state_reopened()
    events = _events_px11()
    for _ in range(10):
        apply_resolution_links(s, events)
    assert s.issues[0].lifecycle.current_status == "reopened"


def test_first_rebuild_builds_correct_history():
    """First time through: open→resolved→reopened in correct order."""
    s = OperationalState(project_id="p", issues=[_issue("Pompa PX11 non funziona", eid="e0")])
    events = _events_px11()
    apply_resolution_links(s, events)
    lc = s.issues[0].lifecycle
    assert lc.current_status == "reopened"
    statuses = [h.status for h in lc.lifecycle_history]
    assert "resolved" in statuses
    assert "reopened" in statuses
    assert len(lc.lifecycle_history) == 2  # resolved + reopened appended (open was pre-existing)
