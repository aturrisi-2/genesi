"""Operational focus & lifecycle behaviour — generic, domain-agnostic.

Reproduces (without any domain hardcoding) the real Telegram Test-Tab session
that exposed the operational-layer bugs:
  * "cosa resta aperto?" returned the aggregate briefing instead of specific items;
  * conditional decisions were not recognised as active;
  * supply/access/documentation updates did not close the linked items;
  * non-operational notes leaked in as operational tasks;
  * briefing counts included resolved/superseded items.

All scenarios use generic vocabulary (supply / access / documentation /
conditional decision) — never the original chat's tokens.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from core.operational_memory.lifecycle_engine import (
    Evidence,
    infer_issue_transition,
    infer_task_transition,
    initial_status,
    is_conditional_decision,
)
from core.operational_memory.models import (
    Decision,
    Issue,
    LifecycleHistoryEntry,
    LifecycleState,
    OperationalQuestion,
    OperationalState,
    OperationalTask,
)
from core.operational_memory.quality import is_non_operational_note
from core.operational_memory.query_engine import (
    active_decisions,
    answer_query,
    build_briefing,
    classify_query_intent,
    open_issues,
    open_tasks,
    remaining_open,
)
from core.operational_memory.chat_presence import build_chat_reply


NOW = datetime.now(timezone.utc)
TS = "2026-06-12T09:00:00+00:00"


def _lc(category: str, status: str) -> LifecycleState:
    return LifecycleState(
        category=category,
        current_status=status,
        status_reason="r",
        evidence_event_ids=["ev1"],
        lifecycle_history=[LifecycleHistoryEntry(status=status, changed_at=TS)],
    )


def _task(i: str, text: str, status: str) -> OperationalTask:
    return OperationalTask(id=i, text=text, source="m", source_event_id=f"e{i}", lifecycle=_lc("task", status))


def _issue(i: str, text: str, status: str) -> Issue:
    return Issue(id=i, text=text, source="m", source_event_id=f"e{i}", lifecycle=_lc("issue", status))


def _decision(i: str, text: str, status: str) -> Decision:
    return Decision(id=i, text=text, source="m", source_event_id=f"e{i}", lifecycle=_lc("decision", status))


def _question(i: str, text: str, status: str) -> OperationalQuestion:
    return OperationalQuestion(id=i, text=text, source="m", source_event_id=f"e{i}", lifecycle=_lc("question", status))


# --------------------------------------------------------------------------- #
# D — non-operational notes
# --------------------------------------------------------------------------- #


def test_non_operational_note_is_ignored():
    # An explicitly non-operational personal note must not count as an open task.
    assert is_non_operational_note("Nota non operativa: comprare il pane") is True
    assert is_non_operational_note("installare il sensore di linea") is False

    state = OperationalState(
        project_id="p",
        tasks=[
            _task("real", "installare il sensore di linea", "open"),
            _task("note", "Nota non operativa: comprare il pane", "open"),
        ],
    )
    ids = {it.item_id for it in open_tasks(state)}
    assert ids == {"real"}  # non-operational note excluded


# --------------------------------------------------------------------------- #
# B — conditional decisions
# --------------------------------------------------------------------------- #


def test_conditional_decision_is_active():
    text = "se l'area non è libera entro le 10, si ripianifica a lunedì"
    assert is_conditional_decision(text) is True
    assert is_conditional_decision("si procede solo se l'area è libera") is True
    assert is_conditional_decision("if the area is not ready, reschedule to monday") is True
    # A plain factual statement is not a conditional decision.
    assert is_conditional_decision("l'area è libera") is False

    state = OperationalState(project_id="p", decisions=[_decision("c1", text, "confirmed")])
    assert {it.item_id for it in active_decisions(state)} == {"c1"}


# --------------------------------------------------------------------------- #
# C — closure linking (supply / access / documentation)
# --------------------------------------------------------------------------- #


def test_supply_confirmation_resolves_material_task():
    assert initial_status("task", "ordinare la fornitura") == "open"  # infinitive ≠ done
    ev = [Evidence("e2", "la fornitura è arrivata ed è confermata", TS)]
    t = infer_task_transition("open", ev, NOW, item_text="ordinare la fornitura")
    assert t is not None and t.new_status == "completed"


def test_access_cleared_resolves_access_issue():
    ev = [Evidence("e2", "l'area di accesso è stata liberata", TS)]
    t = infer_issue_transition("open", ev, NOW, item_text="area di accesso non libera")
    assert t is not None and t.new_status == "resolved"


def test_documentation_sent_resolves_photo_task():
    assert initial_status("task", "inviare la documentazione") == "open"
    ev = [Evidence("e2", "la documentazione è stata inviata al cliente", TS)]
    t = infer_task_transition("open", ev, NOW, item_text="inviare la documentazione")
    assert t is not None and t.new_status == "completed"


# --------------------------------------------------------------------------- #
# A — "cosa resta aperto?" returns specific items
# --------------------------------------------------------------------------- #


def _mixed_state() -> OperationalState:
    return OperationalState(
        project_id="p",
        tasks=[
            _task("t_open", "preparare la documentazione", "open"),
            _task("t_done", "inviare il preventivo", "completed"),
            _task("t_note", "Nota non operativa: comprare il pane", "open"),
        ],
        issues=[
            _issue("i_open", "accesso area non verificato", "open"),
            _issue("i_res", "fornitura mancante", "resolved"),
        ],
        decisions=[
            _decision("d_act", "se l'area non è libera entro le 10, si rimanda a lunedì", "confirmed"),
            _decision("d_sup", "scelta vecchia", "superseded"),
        ],
        open_questions=[
            _question("q_open", "la fornitura è confermata?", "open"),
            _question("q_ans", "orario consegna?", "answered"),
        ],
    )


def test_what_remains_open_returns_specific_items():
    state = _mixed_state()
    assert classify_query_intent("cosa resta aperto?") == "remaining_open"

    res = answer_query(state, "cosa resta aperto?")
    assert res.intent == "remaining_open"
    texts = {it.text for it in res.items}
    # specific open items present
    assert "preparare la documentazione" in texts
    assert "accesso area non verificato" in texts
    assert "la fornitura è confermata?" in texts
    # closed / non-operational excluded
    assert "inviare il preventivo" not in texts
    assert "fornitura mancante" not in texts
    assert all("comprare il pane" not in t for t in texts)

    reply = build_chat_reply(state, "cosa resta aperto?", report_url="/x")
    assert reply.intent == "remaining_open"
    # grouped, specific list — not just an aggregate number
    assert "Problemi aperti:" in reply.reply_markdown
    assert "Task aperti:" in reply.reply_markdown
    assert "accesso area non verificato" in reply.reply_markdown


def test_what_remains_open_empty_says_no_items():
    state = OperationalState(project_id="p", tasks=[_task("t", "x", "completed")])
    res = answer_query(state, "cosa resta aperto?")
    assert res.count == 0
    assert "Non risultano punti aperti" in res.summary


# --------------------------------------------------------------------------- #
# E — update picture excludes resolved + counts match active only
# --------------------------------------------------------------------------- #


def test_update_operational_picture_excludes_resolved_items():
    state = _mixed_state()
    assert classify_query_intent("aggiorna il quadro operativo") == "briefing"
    briefing = build_briefing(state)
    by_key = {r.key: r for r in briefing.rows}
    open_issue_texts = {it.text for it in by_key["open_issues"].items}
    resolved_issue_texts = {it.text for it in by_key["resolved_issues"].items}
    assert "fornitura mancante" not in open_issue_texts
    assert "fornitura mancante" in resolved_issue_texts


def test_counts_match_active_items_only():
    state = _mixed_state()
    by_key = {r.key: r for r in build_briefing(state).rows}
    # 1 open task (completed + non-operational note excluded)
    assert by_key["open_tasks"].count == 1
    # 1 open issue (resolved excluded)
    assert by_key["open_issues"].count == 1
    # 1 active decision (superseded excluded)
    assert by_key["active_decisions"].count == 1
    # 1 open question (answered excluded)
    assert by_key["open_questions"].count == 1
    # active rows never count closed states
    assert by_key["resolved_issues"].active is False
    assert by_key["superseded_decisions"].active is False


# --------------------------------------------------------------------------- #
# No domain hardcoding in the touched modules
# --------------------------------------------------------------------------- #


# --------------------------------------------------------------------------- #
# Rendering: focused intents must NOT append the general briefing card
# --------------------------------------------------------------------------- #


def _render_state() -> OperationalState:
    return OperationalState(
        project_id="p",
        tasks=[_task("t_open", "inviare la documentazione al cliente", "open")],
        issues=[_issue("i_open", "passaggio cavi non verificato", "open")],
        decisions=[_decision("d_cond", "se l'area non è libera entro le 10, si ripianifica a lunedì", "confirmed")],
        open_questions=[_question("q_open", "disponibilità confermata?", "open")],
    )


def test_briefing_still_returns_card():
    reply = build_chat_reply(_render_state(), "fammi il punto", report_url="/r")
    assert reply.intent == "briefing"
    assert "📌 Quadro operativo" in reply.reply_markdown
    assert "🧭 Sintesi operativa" in reply.reply_markdown


def test_remaining_open_does_not_append_briefing_card():
    reply = build_chat_reply(_render_state(), "cosa resta aperto?", report_url="/r")
    assert reply.intent == "remaining_open"
    assert "📌 Quadro operativo" not in reply.reply_markdown


def test_remaining_open_lists_specific_items():
    md = build_chat_reply(_render_state(), "cosa resta aperto?").reply_markdown
    assert ("Problemi aperti:" in md) or ("Non risultano punti aperti" in md)
    assert "passaggio cavi non verificato" in md


def test_active_decisions_does_not_append_briefing_card():
    reply = build_chat_reply(_render_state(), "quali decisioni sono attive?")
    assert reply.intent == "active_decisions"
    assert "📌 Quadro operativo" not in reply.reply_markdown


def test_active_decisions_lists_conditional_decision():
    md = build_chat_reply(_render_state(), "quali decisioni sono attive?").reply_markdown
    assert "Decisioni attive" in md
    assert "si ripianifica a lunedì" in md


def test_unknown_does_not_return_card():
    state = OperationalState(
        project_id="p",
        tasks=[_task("n", "Nota non operativa: comprare il pane", "open")],
    )
    reply = build_chat_reply(state, "dimmi solo cosa comprare stasera")
    assert reply.intent == "unknown"
    assert "📌 Quadro operativo" not in reply.reply_markdown


# --------------------------------------------------------------------------- #
# Conditional decisions must survive the live extraction path
# --------------------------------------------------------------------------- #

import json as _json
from unittest.mock import AsyncMock

from core.operational_memory.extractor import extract_state
from core.operational_memory.models import OperationalEvent

_EMPTY_LLM = _json.dumps(
    {"decisions": [], "tasks": [], "issues": [], "information": [], "open_questions": []}
)


def _mock_llm(monkeypatch):
    # LLM returns nothing → only the deterministic safety-net can create the decision.
    monkeypatch.setattr(
        "core.operational_memory.extractor.llm_service._call_model",
        AsyncMock(return_value=_EMPTY_LLM),
    )


def _evt(content: str, project: str = "p") -> OperationalEvent:
    return OperationalEvent(event_id="ev1", project_id=project, source="telegram", sender="Ann", content=content)


@pytest.mark.asyncio
async def test_live_phrase_conditional_decision_is_extracted(monkeypatch):
    _mock_llm(monkeypatch)
    phrase = "Se il corridoio non è libero entro le 10:00, si rimanda tutto a lunedì."
    state = await extract_state([phrase], source_event=_evt(phrase))
    assert len(state.decisions) == 1
    assert len(active_decisions(state)) == 1


@pytest.mark.asyncio
async def test_generic_conditional_decision_with_only_if(monkeypatch):
    _mock_llm(monkeypatch)
    phrase = "Si procede venerdì solo se il materiale è confermato."
    assert is_conditional_decision(phrase)
    state = await extract_state([phrase], source_event=_evt(phrase))
    assert len(active_decisions(state)) == 1


@pytest.mark.asyncio
async def test_generic_conditional_decision_in_case_otherwise(monkeypatch):
    _mock_llm(monkeypatch)
    phrase = "In caso contrario si ripianifica a lunedì."
    assert is_conditional_decision(phrase)
    state = await extract_state([phrase], source_event=_evt(phrase))
    # Stable behaviour: it becomes an active decision, never a generic task.
    assert len(active_decisions(state)) == 1
    assert state.tasks == []


@pytest.mark.asyncio
async def test_english_conditional_decision_is_extracted(monkeypatch):
    _mock_llm(monkeypatch)
    phrase = "If the access is not clear by 10:00, reschedule to Monday."
    assert is_conditional_decision(phrase)
    state = await extract_state([phrase], source_event=_evt(phrase))
    assert len(active_decisions(state)) == 1


@pytest.mark.asyncio
async def test_active_decisions_query_returns_conditional_decision(monkeypatch):
    _mock_llm(monkeypatch)
    phrase = "Se non arriva il materiale entro venerdì, si rimanda a lunedì."
    state = await extract_state([phrase], source_event=_evt(phrase))
    items = active_decisions(state)
    assert len(items) == 1
    assert items[0].status in {"confirmed", "active", "proposed"}


@pytest.mark.asyncio
async def test_conditional_decision_not_created_from_question(monkeypatch):
    _mock_llm(monkeypatch)
    phrase = "Se non è libero entro le 10:00 cosa facciamo?"
    assert is_conditional_decision(phrase) is False
    state = await extract_state([phrase], source_event=_evt(phrase))
    assert len(active_decisions(state)) == 0


@pytest.mark.asyncio
async def test_conditional_decision_extracted_via_pending_pipeline(monkeypatch, tmp_path):
    # End-to-end live path: event stored → domain gate (low score) → routed to
    # extraction because it is a conditional decision → safety-net creates it.
    from core.operational_memory import event_store, state_store
    from core.operational_memory.watcher_engine import ingest_event, process_pending_events

    monkeypatch.setattr(state_store, "_BASE_DIR", tmp_path / "state")
    monkeypatch.setattr(event_store, "_BASE_DIR", tmp_path / "events")
    _mock_llm(monkeypatch)
    ev = OperationalEvent(
        event_id="e1", project_id="proj", source="telegram", sender="Ann",
        content="Se l'area non è libera entro le 10:00, si rimanda tutto a lunedì.",
    )
    await ingest_event(ev)
    await process_pending_events("proj", rebuild_threads=False)
    state = await state_store.load_state("proj")
    assert len(active_decisions(state)) == 1


# --------------------------------------------------------------------------- #
# Resolution linking: completion updates close related open items (generic)
# --------------------------------------------------------------------------- #

from core.operational_memory.lifecycle_engine import apply_resolution_links


def _open_task(i, text):
    return OperationalTask(id=i, text=text, source="m", source_event_id=f"s{i}",
                           source_timestamp="2026-06-12T08:00:00+00:00", lifecycle=_lc("task", "open"))


def _open_issue(i, text):
    return Issue(id=i, text=text, source="m", source_event_id=f"s{i}",
                 source_timestamp="2026-06-12T08:00:00+00:00", lifecycle=_lc("issue", "open"))


def _open_question(i, text):
    return OperationalQuestion(id=i, text=text, source="m", source_event_id=f"s{i}",
                              source_timestamp="2026-06-12T08:00:00+00:00", lifecycle=_lc("question", "open"))


def _upd(eid, content, ts="2026-06-12T09:00:00+00:00"):
    return OperationalEvent(event_id=eid, project_id="p", source="telegram", sender="A", content=content, timestamp=ts)


def test_access_cleared_closes_related_open_issue_live_path():
    state = OperationalState(project_id="p", issues=[_open_issue("i1", "l'accesso all'area non è ancora libero")])
    events = [_upd("e1", "l'accesso all'area non è ancora libero", "2026-06-12T08:00:00+00:00"),
              _upd("e2", "Aggiornamento: l'accesso all'area è stato liberato")]
    apply_resolution_links(state, events)
    assert open_issues(state) == []
    assert remaining_open(state) == []


def test_sent_document_closes_related_photo_task_live_path():
    state = OperationalState(project_id="p", tasks=[_open_task("t1", "serve mandare la foto al cliente")])
    events = [_upd("e2", "Aggiornamento: la foto è stata inviata al cliente")]
    apply_resolution_links(state, events)
    assert open_tasks(state) == []


def test_supplier_reply_closes_open_answer_question():
    state = OperationalState(project_id="p", open_questions=[_open_question("q1", "serve risposta del fornitore sul materiale")])
    events = [_upd("e2", "Il fornitore ha risposto: materiale disponibile")]
    apply_resolution_links(state, events)
    assert all(it.text != "serve risposta del fornitore sul materiale" for it in remaining_open(state))


def test_confirmation_closes_material_task_but_not_unrelated_access_issue():
    state = OperationalState(
        project_id="p",
        tasks=[_open_task("t1", "materiale da confermare")],
        issues=[_open_issue("i1", "accesso non libero")],
    )
    events = [_upd("e2", "materiale confermato")]
    apply_resolution_links(state, events)
    assert open_tasks(state) == []                       # material closed
    assert {it.item_id for it in open_issues(state)} == {"i1"}  # access stays open


def test_negated_resolution_does_not_close():
    state = OperationalState(project_id="p", tasks=[_open_task("t1", "foto da inviare")])
    events = [_upd("e2", "La foto non è stata ancora inviata.")]
    apply_resolution_links(state, events)
    assert {it.item_id for it in open_tasks(state)} == {"t1"}   # still open


def test_live_update_corridor_photo_closes_only_matching_items():
    state = OperationalState(
        project_id="p",
        issues=[_open_issue("i1", "il passaggio non è ancora libero")],
        tasks=[_open_task("t1", "serve mandare una foto al cliente"),
               _open_task("t2", "materiale da confermare")],
    )
    events = [_upd("e2", "Aggiornamento: il passaggio è stato liberato e la foto è stata mandata al cliente")]
    apply_resolution_links(state, events)
    assert open_issues(state) == []                        # passage closed
    assert {it.item_id for it in open_tasks(state)} == {"t2"}  # photo closed, material untouched


def test_remaining_open_excludes_resolved_items_after_resolution():
    state = OperationalState(
        project_id="p",
        issues=[_open_issue("i1", "accesso non libero")],
        tasks=[_open_task("t1", "mandare la documentazione")],
    )
    before = {it.text for it in remaining_open(state)}
    assert "accesso non libero" in before
    events = [_upd("e2", "accesso liberato"), _upd("e3", "documentazione inviata")]
    apply_resolution_links(state, events)
    after = {it.text for it in remaining_open(state)}
    assert after == set()


def test_no_domain_hardcoding_for_resolution_linking():
    import re

    import core.operational_memory.extractor as m_ext
    import core.operational_memory.incremental_rebuild as m_reb
    import core.operational_memory.lifecycle_engine as m_life
    import core.operational_memory.query_engine as m_query
    import core.operational_memory.watcher_engine as m_watch

    forbidden = ["test tab", "tab cefla", "cantiere", "quadro elettrico", "corridoio", "sara", "pane", "-5408248562"]
    for mod in (m_life, m_watch, m_ext, m_query, m_reb):
        body = open(mod.__file__, "r", encoding="utf-8").read().lower()
        for token in forbidden:
            assert not re.search(rf"\b{re.escape(token)}\b", body), f"hardcoded '{token}' in {mod.__name__}"


def test_no_domain_hardcoding_for_conditional_decision_extractor():
    import re

    import core.operational_memory.extractor as m_ext
    import core.operational_memory.lifecycle_engine as m_life
    import core.operational_memory.query_engine as m_query
    import core.operational_memory.watcher_engine as m_watch

    forbidden = ["corridoio", "quadro elettrico", "pane", "test tab", "tab cefla", "cantiere", "magnetotermici"]
    for mod in (m_ext, m_life, m_query, m_watch):
        body = open(mod.__file__, "r", encoding="utf-8").read().lower()
        for token in forbidden:
            assert not re.search(rf"\b{re.escape(token)}\b", body), f"hardcoded '{token}' in {mod.__name__}"


def test_no_domain_hardcoding():
    import re

    import core.operational_memory.chat_presence as m_chat
    import core.operational_memory.extractor as m_ext
    import core.operational_memory.lifecycle_engine as m_life
    import core.operational_memory.quality as m_qual
    import core.operational_memory.query_engine as m_query

    forbidden = [
        "pane", "corridoio", "magnetotermici", "magnetotermico",
        "cefla", "test tab", "quadro elettrico", "tab cefla", "cantiere",
    ]
    for mod in (m_chat, m_ext, m_life, m_qual, m_query):
        body = open(mod.__file__, "r", encoding="utf-8").read().lower()
        for token in forbidden:
            assert not re.search(rf"\b{re.escape(token)}\b", body), (
                f"hardcoded domain token '{token}' leaked into {mod.__name__}"
            )
