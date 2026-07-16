"""B10.1 — natural query gap fixes from the B10 field trial.

  * "su cosa mi devo concentrare" → attention
  * "cosa ci manca per chiudere" → open_tasks
  * "mandami/inviami il report" → cmd_report
  * decision guard: opinion/decision requests never captured by task patterns;
    fixed reply, no ingest, no invented decision
  * status line: human D/M HH:MM, never raw ISO
"""
from __future__ import annotations

import asyncio

import pytest
from unittest.mock import AsyncMock, patch

from core.operational_memory.models import OperationalState
from core.operational_memory.query_engine import (
    _DECISION_GUARD_REPLY,
    answer_query,
    classify_query_intent,
    command_status_line,
    is_pure_operational_invocation,
)
from core.operational_memory.chat_presence import build_chat_reply

CANARY_JID = "120363428502905378@g.us"
TAB_JID = "120363404290146040@g.us"
TAB_PROJECT = "tab-cefla-hq-enel-roma"
CANARY_PROJECT = "whatsapp-canary-ocr-01"


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Routing fixes
# ---------------------------------------------------------------------------

def test_concentrare_attention():
    q = "su cosa mi devo concentrare adesso?"
    assert classify_query_intent(q) == "attention"
    assert is_pure_operational_invocation(q) is True


def test_cosa_ci_manca_open_tasks():
    q = "cosa ci manca per chiudere?"
    assert classify_query_intent(q) == "open_tasks"
    assert is_pure_operational_invocation(q) is True


def test_mandami_report_cmd_report():
    assert classify_query_intent("mandami il report") == "cmd_report"
    assert is_pure_operational_invocation("mandami il report") is True


def test_inviami_report_cmd_report():
    assert classify_query_intent("inviami il report") == "cmd_report"


# ---------------------------------------------------------------------------
# Decision guard
# ---------------------------------------------------------------------------

def test_secondo_te_decision_guard_not_open_tasks():
    q = "secondo te possiamo decidere di chiudere questa attività?"
    assert classify_query_intent(q) == "decision_guard"
    assert is_pure_operational_invocation(q) is True


def test_possiamo_chiudere_decision_guard():
    q = "possiamo chiudere questa attività?"
    assert classify_query_intent(q) == "decision_guard"


def test_conviene_decision_guard():
    assert classify_query_intent("conviene aprire gli intercetti o aspettiamo?") == "decision_guard"


def test_che_ne_dici_decision_guard():
    assert classify_query_intent("che ne dici di anticipare il collaudo?") == "decision_guard"


def test_decision_guard_reply_text():
    r = build_chat_reply(OperationalState(project_id="x"),
                         "secondo te possiamo decidere di chiudere questa attività?")
    assert r.intent == "decision_guard"
    assert r.reply_markdown == _DECISION_GUARD_REPLY
    assert "Non posso decidere al posto del team" in r.reply_markdown


def test_decision_guard_answer_query_no_items():
    res = answer_query(OperationalState(project_id="x"), "conviene chiudere?")
    assert res.intent == "decision_guard"
    assert res.count == 0 and res.items == []


# ---------------------------------------------------------------------------
# Non-regression on task patterns
# ---------------------------------------------------------------------------

def test_attivita_aperte_still_open_tasks():
    assert classify_query_intent("attività aperte") == "open_tasks"


def test_chi_deve_muoversi_still_open_tasks():
    assert classify_query_intent("chi deve muoversi?") == "open_tasks"


def test_cosa_manca_still_open_tasks():
    assert classify_query_intent("cosa manca") == "open_tasks"


def test_meteo_is_safe_read_only_intent():
    q = "che tempo fa domani?"
    assert classify_query_intent(q) == "weather"
    assert is_pure_operational_invocation(q) is True


def test_report_variants_unchanged():
    assert classify_query_intent("report") == "cmd_report"
    assert classify_query_intent("report operativo") == "cmd_report"


# ---------------------------------------------------------------------------
# Status line timestamp
# ---------------------------------------------------------------------------

def test_status_line_no_raw_iso():
    s = OperationalState(project_id="x", updated_at="2026-07-02T14:47:25.383431+00:00")
    line = command_status_line(s)
    assert "2026-07-02T" not in line
    assert "agg. 2/7 14:47" in line


def test_status_line_unparsable_fallback():
    s = OperationalState(project_id="x", updated_at="boh")
    assert "agg. boh" in command_status_line(s)


# ---------------------------------------------------------------------------
# Console mode integration
# ---------------------------------------------------------------------------

@pytest.fixture()
def _console(monkeypatch):
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational.is_whatsapp_operational_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational.resolve_whatsapp_project_id",
        lambda jid: CANARY_PROJECT if jid == CANARY_JID else None,
    )
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational.is_whatsapp_operational_reply_enabled",
        lambda jid=None: True,
    )
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational._TAB_BRIDGE_ORIGIN_JID", CANARY_JID
    )
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational._TAB_BRIDGE_PROJECT_ID", TAB_PROJECT
    )
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational._TAB_BRIDGE_DEFAULT_NO_TARGET", True
    )
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational.flush_project", AsyncMock()
    )
    update_mock = AsyncMock()
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational._safe_update", update_mock
    )
    return update_mock


def _mock_reply(intent):
    from core.operational_memory.models import ChatReply
    return ChatReply(
        project_id=TAB_PROJECT, intent=intent, reply_markdown="mock",
        synthesis="", table_markdown="", actions=[], evidence_event_ids=[],
        report_id="", report_url="",
    )


def test_fixed_queries_bridge_tab_console(_console):
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    for text, intent in [
        ("Genesi, su cosa mi devo concentrare adesso?", "attention"),
        ("Genesi, cosa ci manca per chiudere?", "open_tasks"),
        ("Genesi, mandami il report", "cmd_report"),
        ("Genesi, secondo te possiamo decidere di chiudere questa attività?", "decision_guard"),
    ]:
        sent = []

        async def send(jid, t, **kw):
            sent.append((jid, t))

        with patch(
            "core.operational_memory.whatsapp_operational.build_operational_reply",
            new=AsyncMock(return_value=_mock_reply(intent)),
        ) as mb:
            _run(maybe_handle_whatsapp_operational(
                group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
                first_name="Alfio", text=text, send_message=send,
            ))
        assert mb.call_args[0][0] == TAB_PROJECT, text
        assert sent and sent[0][0] == CANARY_JID, text
        assert TAB_JID not in [j for j, _ in sent], text
    _console.assert_not_called()  # 0 ingest


def test_mandami_report_save_true_console(_console):
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational

    async def send(jid, t, **kw):
        pass

    with patch(
        "core.operational_memory.whatsapp_operational.build_operational_reply",
        new=AsyncMock(return_value=_mock_reply("cmd_report")),
    ) as mb:
        _run(maybe_handle_whatsapp_operational(
            group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
            first_name="Alfio", text="Genesi, mandami il report", send_message=send,
        ))
    _, kwargs = mb.call_args
    assert kwargs.get("save") is True
