"""B9 Conversational Contract — end-to-end contract tests.

For each contract intent: correct route (console→TAB from canary), correct
professional format, no emoji, no raw dump, caps respected, drafts never sent,
pure/conversational queries never ingested, TAB read-only.
"""
from __future__ import annotations

import asyncio

import pytest
from unittest.mock import AsyncMock, patch

from core.operational_memory.models import (
    Issue,
    LifecycleState,
    OperationalState,
    OperationalTask,
)
from core.operational_memory.query_engine import (
    _attention_rank,
    attention_items,
    classify_query_intent,
    is_pure_operational_invocation,
)
from core.operational_memory.chat_presence import build_chat_reply

CANARY_JID = "120363428502905378@g.us"
TAB_JID = "120363404290146040@g.us"
TAB_PROJECT = "tab-cefla-hq-enel-roma"
CANARY_PROJECT = "whatsapp-canary-ocr-01"

_EMOJI = ["📌", "🧭", "📄", "⚠", "✅", "❤", "🔥", "👍"]


def _run(coro):
    return asyncio.run(coro)


def _issue(text, status="open", confidence="high", eid="e1"):
    return Issue(
        text=text, source="wa", source_event_id=eid,
        source_timestamp="2026-07-01T08:00:00+00:00", confidence=confidence,
        lifecycle=LifecycleState(category="issue", current_status=status,
                                 confidence=confidence),
    )


def _task(text, due=None, owner=None, status="open", eid="t1"):
    return OperationalTask(
        text=text, source="wa", source_event_id=eid,
        source_timestamp="2026-07-01T08:00:00+00:00", due=due, owner=owner,
        lifecycle=LifecycleState(category="task", current_status=status,
                                 confidence="high"),
    )


def _state(**kw):
    s = OperationalState(project_id="test-b9c")
    for k, v in kw.items():
        getattr(s, k).extend(v)
    return s


def _rich_state():
    return _state(
        issues=[
            _issue("guasto riaperto UTA", status="reopened", eid="e1"),
            _issue("perdita FC CED", eid="e2"),
            _issue("valvola V80 disallineata", eid="e3"),
        ],
        tasks=[
            _task("verificare bracci", due="2026-07-03", status="blocked", eid="t1"),
            _task("pulire filtri", owner=None, eid="t2"),
        ],
    )


# ---------------------------------------------------------------------------
# Console routing (canary → TAB) for all contract intents
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


CONTRACT_QUERIES = [
    ("Genesi, dammi solo le priorità", "attention"),
    ("Genesi, cosa devo controllare", "attention"),
    ("Genesi, dove siamo scoperti", "attention"),
    ("Genesi, cosa rischia di bloccarci", "attention"),
    ("Genesi, chi deve muoversi", "open_tasks"),
    ("Genesi, preparami un messaggio operativo", "team_brief"),
    ("Genesi, cosa diresti al team", "team_brief"),
    ("Genesi, fammi il quadro della situazione", "briefing"),
]


def test_contract_queries_route_console_to_tab(_console):
    """All contract queries from the canary (console mode) → TAB source,
    reply in canary, never ingested, never sent to TAB JID."""
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    for text, expected_intent in CONTRACT_QUERIES:
        sent = []

        async def send(jid, t, **kw):
            sent.append((jid, t))

        with patch(
            "core.operational_memory.whatsapp_operational.build_operational_reply",
            new=AsyncMock(return_value=_mock_reply(expected_intent)),
        ) as mb:
            _run(maybe_handle_whatsapp_operational(
                group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
                first_name="Alfio", text=text, send_message=send,
            ))
        assert mb.call_args[0][0] == TAB_PROJECT, text
        assert sent and sent[0][0] == CANARY_JID, text
        assert TAB_JID not in [j for j, _ in sent], text
    _console.assert_not_called()  # 0 ingest across all contract queries


def test_report_operativo_routes_report(_console):
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent = []

    async def send(jid, t, **kw):
        sent.append((jid, t))

    with patch(
        "core.operational_memory.whatsapp_operational.build_operational_reply",
        new=AsyncMock(return_value=_mock_reply("cmd_report")),
    ) as mb:
        _run(maybe_handle_whatsapp_operational(
            group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
            first_name="Alfio", text="Genesi, report operativo", send_message=send,
        ))
    assert mb.call_args[0][0] == TAB_PROJECT
    _, kwargs = mb.call_args
    assert kwargs.get("save") is True  # cmd_report persists the report
    assert sent[0][0] == CANARY_JID


def test_ambiguous_query_fail_closed_no_ingest(_console):
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent = []

    async def send(jid, t, **kw):
        sent.append((jid, t))

    _run(maybe_handle_whatsapp_operational(
        group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
        first_name="Alfio", text="Genesi, sistemare quella cosa di ieri",
        send_message=send,
    ))
    assert sent and (_t := sent[0][1]) and ("non voglio inventare" in _t or "esco dal mio campo" in _t or "non so leggerla" in _t)
    _console.assert_not_called()


# ---------------------------------------------------------------------------
# Contract formats — no emoji, caps, structure, drafts
# ---------------------------------------------------------------------------

def test_attention_contract_format():
    r = build_chat_reply(_rich_state(), "dammi solo le priorità")
    body = r.reply_markdown
    assert body.startswith("Priorità operative:")
    assert "[riaperto]" in body
    assert "Rischio principale:" in body
    assert "Prossima verifica:" in body
    numbered = [l for l in body.splitlines() if l[:2] in {"1.", "2.", "3.", "4.", "5."}]
    assert len(numbered) <= 5
    for e in _EMOJI:
        assert e not in body


def test_open_issues_contract_format():
    s = _state(issues=[_issue(f"problema {i}", status="reopened" if i == 0 else "open",
                              eid=f"e{i}") for i in range(7)])
    r = build_chat_reply(s, "problemi aperti")
    body = r.reply_markdown
    assert body.startswith("Problemi aperti:")
    assert "1. problema 0 [riaperto]" in body
    assert "Altri 2 in coda." in body
    assert "Azione consigliata: ripartire da problema 0." in body
    for e in _EMOJI:
        assert e not in body


def test_open_issues_empty():
    r = build_chat_reply(OperationalState(project_id="x"), "problemi aperti")
    assert "Nessun problema aperto." in r.reply_markdown


def test_team_brief_contract_format():
    r = build_chat_reply(_rich_state(), "preparami un messaggio operativo")
    body = r.reply_markdown
    assert body.startswith("Bozza messaggio operativo (non inviata):")
    assert "Situazione:" in body
    assert "Priorità:" in body
    assert "Prossima azione:" in body
    assert "Richiesta operativa:" in body
    assert "Prossimo aggiornamento:" in body
    for e in _EMOJI:
        assert e not in body


def test_cmd_report_no_emoji():
    r = build_chat_reply(_rich_state(), "report", report_url="https://x/r/1")
    assert r.reply_markdown == "Report operativo: https://x/r/1"


def test_whatsapp_report_link_no_emoji():
    from core.operational_memory.whatsapp_operational import render_whatsapp_reply
    from core.operational_memory.models import ChatReply
    reply = ChatReply(project_id="p", intent="cmd_report", reply_markdown="BODY",
                      synthesis="", table_markdown="", actions=[],
                      evidence_event_ids=[], report_id="r", report_url="https://x/u")
    body = render_whatsapp_reply(reply)
    assert "Report: https://x/u" in body
    assert "📄" not in body


# ---------------------------------------------------------------------------
# Ranking contract: reopened > due > critical issue > task w/o owner > rest
# ---------------------------------------------------------------------------

def test_rank_tiers_full_contract():
    from core.operational_memory.models import QueryAnswerItem
    reo = QueryAnswerItem(text="a", status="reopened")
    due = QueryAnswerItem(text="b", status="open", due="2026-07-05")
    hi = QueryAnswerItem(text="c", status="open", category="issue", confidence="high")
    noown = QueryAnswerItem(text="d", status="open", category="task", owner=None)
    owned = QueryAnswerItem(text="e", status="open", category="task", owner="Mario")
    ranked = sorted([owned, noown, hi, due, reo], key=_attention_rank)
    assert [it.text for it in ranked] == ["a", "b", "c", "d", "e"]


def test_attention_items_apply_contract_order():
    s = _rich_state()
    items = attention_items(s)
    texts = [it.text for it in items]
    assert texts[0] == "guasto riaperto UTA"
    assert texts[1] == "verificare bracci"  # due 3/7, blocked


# ---------------------------------------------------------------------------
# Purity: contract queries are never ingestable
# ---------------------------------------------------------------------------

def test_contract_queries_are_pure():
    for q in ["dammi solo le priorità", "cosa devo controllare", "dove siamo scoperti",
              "cosa rischia di bloccarci", "chi deve muoversi",
              "preparami un messaggio operativo", "cosa diresti al team",
              "fammi il quadro della situazione", "report operativo"]:
        assert is_pure_operational_invocation(q) is True, q


def test_briefing_card_unchanged_for_telegram():
    """Deviazione documentata: card briefing resta nel formato condiviso 📌/🧭
    (il renderer Telegram ne dipende per bold + focus links)."""
    r = build_chat_reply(_rich_state(), "fammi il punto")
    assert "📌 Quadro operativo" in r.reply_markdown
