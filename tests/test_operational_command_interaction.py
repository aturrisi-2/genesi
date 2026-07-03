"""Mini technical Operational Memory interaction — `@genesi stato|aperti|report`.

Deterministic command shortcuts (no LLM). Validates:
  * command classification + exact-anchored (natural-language phrasing unaffected);
  * commands are PURE invocations → never stored as project items;
  * short technical rendering (no general card, few lines);
  * bridge behaviour preserved: normal msg → silent_ingest; pure command with
    reply OFF → claim_no_reply, no ingest, no send; reply ON → short reply to
    the group JID.

Platform-independent: rendering tested at the shared core layer; the WhatsApp
bridge is used as the transport regression guard. Telegram inherits the same
core path. No env/restart/live; real group reply stays OFF.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from core.operational_memory.models import (
    ChatReply,
    Decision,
    Information,
    Issue,
    LifecycleHistoryEntry,
    LifecycleState,
    OperationalQuestion,
    OperationalState,
    OperationalTask,
)
from core.operational_memory.chat_presence import build_chat_reply
from core.operational_memory.query_engine import (
    answer_query,
    classify_query_intent,
    command_status_line,
    is_pure_operational_invocation,
)


# --------------------------------------------------------------------------- #
# State builders (mirror tests/test_operational_query.py)
# --------------------------------------------------------------------------- #


def _lc(category, status, evidence=None):
    return LifecycleState(
        category=category,
        current_status=status,
        confidence="medium",
        status_reason="r",
        evidence_event_ids=evidence or ["ev1"],
        lifecycle_history=[LifecycleHistoryEntry(status=status, changed_at="2026-06-21T08:00:00+00:00")],
    )


def _state():
    return OperationalState(
        project_id="tab-cefla-hq-enel-roma",
        updated_at="2026-06-21T10:00:00+00:00",
        tasks=[
            OperationalTask(id="t1", text="ordinare materiale", source="m", source_event_id="e1", lifecycle=_lc("task", "open")),
            OperationalTask(id="t2", text="montaggio quadro", source="m", source_event_id="e2", lifecycle=_lc("task", "completed")),
        ],
        issues=[
            Issue(id="i1", text="ritardo consegna", source="m", source_event_id="e3", lifecycle=_lc("issue", "open")),
            Issue(id="i2", text="errore cablaggio", source="m", source_event_id="e4", lifecycle=_lc("issue", "resolved")),
        ],
        decisions=[Decision(id="d1", text="usare fornitore X", source="m", source_event_id="e5", lifecycle=_lc("decision", "confirmed"))],
        open_questions=[OperationalQuestion(id="q1", text="data sopralluogo?", source="m", source_event_id="e6", lifecycle=_lc("question", "open"))],
        information=[Information(id="info1", text="contatto referente", source="m", source_event_id="e7", lifecycle=_lc("information", "current"))],
    )


# --------------------------------------------------------------------------- #
# Classification — commands recognised, natural language unaffected
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("text,intent", [
    ("stato", "cmd_stato"),
    ("aperti", "cmd_aperti"),
    ("report", "cmd_report"),
    ("  Stato  ", "cmd_stato"),
    ("REPORT", "cmd_report"),
])
def test_commands_classified(text, intent):
    assert classify_query_intent(text) == intent


@pytest.mark.parametrize("text,intent", [
    ("stato del progetto", "digest"),     # natural phrasing → existing intent, NOT cmd
    ("fammi il report", "briefing"),
    ("cosa resta aperto?", "remaining_open"),
])
def test_natural_language_not_captured_by_commands(text, intent):
    assert classify_query_intent(text) == intent


# --------------------------------------------------------------------------- #
# Commands are PURE invocations → never ingested as events
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("text", ["stato", "aperti", "report"])
def test_commands_are_pure_invocations(text):
    assert is_pure_operational_invocation(text) is True


# --------------------------------------------------------------------------- #
# Deterministic short rendering (no card, few lines)
# --------------------------------------------------------------------------- #


def test_command_status_line_counts():
    line = command_status_line(_state())
    assert line == (
        "Task 1 aperti · Problemi 1 aperti (1 risolti) · Decisioni attive 1 · "
        "Info 1 · Domande aperte 1 · agg. 21/6 10:00"
    )


def test_cmd_stato_reply_is_short_no_card():
    reply = build_chat_reply(_state(), "stato")
    assert reply.intent == "cmd_stato"
    assert "Quadro operativo" not in reply.reply_markdown   # never the general card
    assert reply.reply_markdown.count("\n") == 0            # single line
    assert "Task 1 aperti" in reply.reply_markdown


def test_cmd_aperti_reply_lists_open_items_no_card():
    reply = build_chat_reply(_state(), "aperti")
    assert reply.intent == "cmd_aperti"
    assert "Quadro operativo" not in reply.reply_markdown
    assert "Problemi aperti:" in reply.reply_markdown
    assert "ritardo consegna" in reply.reply_markdown       # open issue
    assert "ordinare materiale" in reply.reply_markdown     # open task
    assert "errore cablaggio" not in reply.reply_markdown   # resolved → excluded


def test_cmd_report_reply_short_with_link():
    reply = build_chat_reply(_state(), "report", report_id="r1", report_url="https://x/view")
    assert reply.intent == "cmd_report"
    assert reply.reply_markdown == "Report operativo: https://x/view"


def test_cmd_report_reply_without_link():
    reply = build_chat_reply(_state(), "report")
    assert reply.intent == "cmd_report"
    assert "nessun link configurato" in reply.reply_markdown


def test_unknown_command_stays_conservative():
    # An unrecognised token is NOT a command → conservative unknown reply, no card.
    reply = build_chat_reply(_state(), "qwerty")
    assert reply.intent == "unknown"
    assert "Quadro operativo" not in reply.reply_markdown


# --------------------------------------------------------------------------- #
# Bridge regression (WhatsApp transport; Telegram shares the same core)
# --------------------------------------------------------------------------- #


GROUP_JID = "120363000000000000@g.us"
SENDER_JID = "393331234567"
PROJECT = "wa-cmd-proj"


def _spies():
    sent, ingested = [], []

    async def send(to, text, *a, **k):
        sent.append((to, text))

    async def updater(message):
        ingested.append(message)

    return sent, ingested, send, updater


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("OPERATIONAL_MEMORY_WHATSAPP_ENABLED", "true")
    monkeypatch.setenv("WHATSAPP_CHAT_PROJECT_MAP", json.dumps({GROUP_JID: PROJECT}))
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://genesi.example.com/")
    return monkeypatch


@pytest.mark.asyncio
async def test_normal_mapped_message_silent_ingest(enabled):
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    result: dict = {}
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "materiale arrivato in cantiere", send,
        message_id="n1", updater=updater, result=result)
    await asyncio.sleep(0)
    assert handled is True
    assert result["action"] == "silent_ingest"
    assert sent == []
    assert [m.message_id for m in ingested] == ["n1"]   # ingested silently


@pytest.mark.asyncio
async def test_command_pure_reply_off_claim_no_reply(enabled):
    # reply flag default OFF → command claimed, NOT ingested, no send.
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    result: dict = {}
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "@genesi stato", send,
        message_id="c1", updater=updater, result=result)
    await asyncio.sleep(0)
    assert handled is True
    assert result["action"] == "claim_no_reply"
    assert sent == []
    assert ingested == []                                # pure command never stored


@pytest.mark.asyncio
@pytest.mark.parametrize("command,expect", [
    ("@genesi stato", "Task 1 aperti"),
    ("@genesi aperti", "Problemi aperti:"),
    ("@genesi report", "Report operativo:"),
])
async def test_command_reply_on_sends_short_technical_reply(enabled, monkeypatch, command, expect):
    monkeypatch.setenv("WHATSAPP_OPERATIONAL_REPLY_ENABLED", "true")
    import core.operational_memory.whatsapp_operational as mod

    async def fake_flush(project_id, rebuild=True):
        return None

    async def fake_reply(project_id, query, report_base_url="", invoked_by="", save=True):
        # Render the command over a fixed state via the REAL core renderer so the
        # query → intent → short technical body path is exercised end-to-end.
        return build_chat_reply(_state(), query, report_id="r", report_url="https://x/view")

    monkeypatch.setattr(mod, "flush_project", fake_flush)
    monkeypatch.setattr(mod, "build_operational_reply", fake_reply)
    sent, ingested, send, updater = _spies()
    result: dict = {}
    handled = await mod.maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", command, send, message_id="r1", updater=updater, result=result)
    assert handled is True
    assert result["action"] == "reply"
    assert len(sent) == 1
    to, body = sent[0]
    assert to == GROUP_JID and to != SENDER_JID          # group JID, never sender
    assert expect in body
    assert ingested == []                                # command is pure → not stored
