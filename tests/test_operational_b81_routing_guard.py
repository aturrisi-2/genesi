"""B8.1 — TAB routing guard + attention pattern expansion.

Tests verify:
  * New attention patterns: devo controllare / devo verificare / va attenzionato /
    devo guardare → intent=attention → bridge fires from canary.
  * TAB-targeted unknown query from canary → fail-closed reply, NO ingest canary.
  * TAB-targeted unknown query from non-canary → bridge never fires (existing guard).
  * 0 write TAB via bridge.
  * 0 write canary for TAB-targeted queries (bridge OR fail-closed).
  * B5/B8 regressions unaffected.
"""
from __future__ import annotations

import asyncio
import re

import pytest
from unittest.mock import AsyncMock, patch

from core.operational_memory.query_engine import (
    classify_query_intent,
    is_pure_operational_invocation,
)

CANARY_JID = "120363428502905378@g.us"
TAB_JID = "120363404290146040@g.us"
TAB_PROJECT = "tab-cefla-hq-enel-roma"
CANARY_PROJECT = "whatsapp-canary-ocr-01"

_TAB_RE = re.compile(r"\b(?:nel|del|di|in)\s+TAB\b|\bTAB\b", re.IGNORECASE)


def _strip_tab(q: str) -> str:
    s = _TAB_RE.sub("", q).strip()
    return re.sub(r"\s{2,}", " ", s).strip()


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _patch_resolve(monkeypatch):
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
        "core.operational_memory.whatsapp_operational._safe_update",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational.flush_project",
        AsyncMock(),
    )
    # B8.1 tests assume console mode OFF — pin the B8.3 flag regardless of host env.
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational._TAB_BRIDGE_DEFAULT_NO_TARGET",
        False,
    )


def _enable_bridge(monkeypatch):
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational._TAB_BRIDGE_ORIGIN_JID", CANARY_JID
    )
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational._TAB_BRIDGE_PROJECT_ID", TAB_PROJECT
    )


def _tab_reply_mock(intent="attention"):
    from core.operational_memory.models import ChatReply
    return ChatReply(
        project_id=TAB_PROJECT, intent=intent,
        reply_markdown="8 elementi che richiedono attenzione",
        synthesis="", table_markdown="", actions=[], evidence_event_ids=[],
        report_id="", report_url="",
    )


# ---------------------------------------------------------------------------
# 1. New attention patterns (query_engine)
# ---------------------------------------------------------------------------

def test_devo_controllare_attention():
    q = _strip_tab("cosa devo controllare nel TAB?")
    assert classify_query_intent(q) == "attention"
    assert is_pure_operational_invocation(q) is True


def test_devo_verificare_attention():
    q = _strip_tab("cosa devo verificare nel TAB?")
    assert classify_query_intent(q) == "attention"
    assert is_pure_operational_invocation(q) is True


def test_va_attenzionato_attention():
    q = _strip_tab("cosa va attenzionato nel TAB?")
    assert classify_query_intent(q) == "attention"
    assert is_pure_operational_invocation(q) is True


def test_devo_guardare_attention():
    q = _strip_tab("cosa devo guardare nel TAB?")
    assert classify_query_intent(q) == "attention"
    assert is_pure_operational_invocation(q) is True


def test_da_controllare_attention():
    assert classify_query_intent("cosa da controllare") == "attention"
    assert is_pure_operational_invocation("cosa da controllare") is True


# ---------------------------------------------------------------------------
# 2. Bridge fires for new patterns (integration)
# ---------------------------------------------------------------------------

def test_cosa_devo_controllare_tab_bridge_fires(monkeypatch):
    _enable_bridge(monkeypatch)
    sent = []

    async def send(jid, text, **kw):
        sent.append((jid, text))

    with patch(
        "core.operational_memory.whatsapp_operational.build_operational_reply",
        new=AsyncMock(return_value=_tab_reply_mock("attention")),
    ) as mock_build:
        from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
        result = _run(maybe_handle_whatsapp_operational(
            group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
            first_name="Alfio", text="Genesi, cosa devo controllare nel TAB?",
            send_message=send,
        ))

    assert result is True
    assert len(sent) == 1
    assert sent[0][0] == CANARY_JID
    assert "Vista TAB reale" in sent[0][1]
    assert mock_build.call_args[0][0] == TAB_PROJECT


def test_cosa_devo_verificare_tab_bridge_fires(monkeypatch):
    _enable_bridge(monkeypatch)
    sent = []

    async def send(jid, text, **kw):
        sent.append((jid, text))

    with patch(
        "core.operational_memory.whatsapp_operational.build_operational_reply",
        new=AsyncMock(return_value=_tab_reply_mock("attention")),
    ) as mock_build:
        from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
        result = _run(maybe_handle_whatsapp_operational(
            group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
            first_name="Alfio", text="Genesi, cosa devo verificare nel TAB?",
            send_message=send,
        ))

    assert result is True
    assert sent[0][0] == CANARY_JID
    assert "Vista TAB reale" in sent[0][1]
    assert mock_build.call_args[0][0] == TAB_PROJECT


def test_cosa_va_attenzionato_tab_bridge_fires(monkeypatch):
    _enable_bridge(monkeypatch)
    sent = []

    async def send(jid, text, **kw):
        sent.append((jid, text))

    with patch(
        "core.operational_memory.whatsapp_operational.build_operational_reply",
        new=AsyncMock(return_value=_tab_reply_mock("attention")),
    ) as mock_build:
        from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
        _run(maybe_handle_whatsapp_operational(
            group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
            first_name="Alfio", text="Genesi, cosa va attenzionato nel TAB?",
            send_message=send,
        ))

    assert sent[0][0] == CANARY_JID
    assert "Vista TAB reale" in sent[0][1]
    assert mock_build.call_args[0][0] == TAB_PROJECT


def test_cosa_devo_guardare_tab_bridge_fires(monkeypatch):
    _enable_bridge(monkeypatch)
    sent = []

    async def send(jid, text, **kw):
        sent.append((jid, text))

    with patch(
        "core.operational_memory.whatsapp_operational.build_operational_reply",
        new=AsyncMock(return_value=_tab_reply_mock("attention")),
    ) as mock_build:
        from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
        _run(maybe_handle_whatsapp_operational(
            group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
            first_name="Alfio", text="Genesi, cosa devo guardare nel TAB?",
            send_message=send,
        ))

    assert sent[0][0] == CANARY_JID
    assert "Vista TAB reale" in sent[0][1]
    assert mock_build.call_args[0][0] == TAB_PROJECT


# ---------------------------------------------------------------------------
# 3. TAB-targeted unknown → fail-closed, NO ingest canary
# ---------------------------------------------------------------------------

def test_tab_unknown_query_fail_closed_no_ingest(monkeypatch):
    """Unknown TAB-targeted query → fail-closed reply, _safe_update NOT called."""
    _enable_bridge(monkeypatch)
    safe_update_mock = monkeypatch.getattr(
        "core.operational_memory.whatsapp_operational._safe_update"
    ) if False else None
    # Re-patch _safe_update to track calls
    update_mock = AsyncMock()
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational._safe_update", update_mock
    )
    sent = []

    async def send(jid, text, **kw):
        sent.append((jid, text))

    with patch(
        "core.operational_memory.whatsapp_operational.build_operational_reply",
        new=AsyncMock(return_value=_tab_reply_mock("unknown")),
    ):
        from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
        result = _run(maybe_handle_whatsapp_operational(
            group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
            first_name="Alfio", text="Genesi, altra query strana nel TAB",
            send_message=send,
        ))

    assert result is True
    assert len(sent) == 1
    assert sent[0][0] == CANARY_JID
    assert "TAB non riconosciuta" in sent[0][1] or "non riconosciuta" in sent[0][1].lower()
    # _safe_update must NOT be called → no canary ingest
    update_mock.assert_not_called()


def test_tab_unknown_query_result_action(monkeypatch):
    """Result dict action=tab_unknown_fail_closed for routing guard path."""
    _enable_bridge(monkeypatch)
    result_dict = {}

    async def send(jid, text, **kw):
        pass

    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    _run(maybe_handle_whatsapp_operational(
        group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
        first_name="Alfio", text="Genesi, altra query strana nel TAB",
        send_message=send, result=result_dict,
    ))

    assert result_dict.get("action") == "tab_unknown_fail_closed"


# ---------------------------------------------------------------------------
# 4. Non-canary origin → bridge/guard do NOT fire (fail-closed)
# ---------------------------------------------------------------------------

def test_tab_unknown_non_canary_no_fail_closed(monkeypatch):
    """Unknown TAB query from non-canary → bridge disabled, falls to normal flow."""
    _enable_bridge(monkeypatch)
    OTHER_JID = "999000000000000001@g.us"
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational.resolve_whatsapp_project_id",
        lambda jid: "other-project" if jid == OTHER_JID else None,
    )
    sent = []

    async def send(jid, text, **kw):
        sent.append((jid, text))

    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    _run(maybe_handle_whatsapp_operational(
        group_jid=OTHER_JID, sender_jid="s@s.whatsapp.net",
        first_name="Alfio", text="Genesi, altra query strana nel TAB",
        send_message=send,
    ))

    # Must NOT send the fail-closed TAB message
    for jid, text in sent:
        assert "TAB non riconosciuta" not in text


# ---------------------------------------------------------------------------
# 5. 0 write TAB — bridge never calls _safe_update with TAB project
# ---------------------------------------------------------------------------

def test_bridge_new_patterns_no_tab_write(monkeypatch):
    """Bridge for new attention patterns must not write TAB state."""
    _enable_bridge(monkeypatch)
    update_calls = []

    async def fake_update(msg):
        update_calls.append(msg.project_id)

    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational._safe_update",
        lambda update, msg: fake_update(msg),
    )

    async def send(jid, text, **kw):
        pass

    with patch(
        "core.operational_memory.whatsapp_operational.build_operational_reply",
        new=AsyncMock(return_value=_tab_reply_mock("attention")),
    ):
        from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
        _run(maybe_handle_whatsapp_operational(
            group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
            first_name="Alfio", text="Genesi, cosa devo controllare nel TAB?",
            send_message=send,
        ))

    assert TAB_PROJECT not in update_calls, "bridge must not write TAB state"
    assert CANARY_PROJECT not in update_calls, "pure invocation must not ingest canary"


# ---------------------------------------------------------------------------
# 6. Non-regression: existing B5/B8 patterns unchanged
# ---------------------------------------------------------------------------

def test_stato_tab_still_fires(monkeypatch):
    _enable_bridge(monkeypatch)
    sent = []

    async def send(jid, text, **kw):
        sent.append((jid, text))

    with patch(
        "core.operational_memory.whatsapp_operational.build_operational_reply",
        new=AsyncMock(return_value=_tab_reply_mock("cmd_stato")),
    ) as mock_build:
        from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
        _run(maybe_handle_whatsapp_operational(
            group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
            first_name="Alfio", text="Genesi, stato TAB",
            send_message=send,
        ))

    assert mock_build.call_args[0][0] == TAB_PROJECT
    assert "Vista TAB reale" in sent[0][1]


def test_existing_attention_patterns_unchanged():
    for q in ["bloccante", "scadenze", "dove siamo scoperti"]:
        assert classify_query_intent(q) == "attention", q
        assert is_pure_operational_invocation(q) is True, q


def test_existing_open_tasks_unchanged():
    for q in ["cosa manca", "da fare", "cosa serve"]:
        assert classify_query_intent(q) == "open_tasks", q


def test_existing_briefing_unchanged():
    assert classify_query_intent("fammi il punto") == "briefing"
    assert classify_query_intent("fammi il quadro") == "briefing"
