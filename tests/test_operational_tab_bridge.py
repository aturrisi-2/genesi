"""B5 — TAB bridge: canary-only read-only cross-project queries.

Tests verify:
  * TAB-scoped intents from canary use TAB project state, reply to canary.
  * Non-canary origin → bridge does not fire (fail-closed).
  * Non-TAB update → normal canary flow, not TAB bridge.
  * No sendMessage to TAB JID.
  * No write / rebuild of TAB state.
  * B2/B4 regressions unaffected.
"""
from __future__ import annotations

import asyncio
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

CANARY_JID = "120363428502905378@g.us"
TAB_JID = "120363404290146040@g.us"
TAB_PROJECT = "tab-cefla-hq-enel-roma"
CANARY_PROJECT = "whatsapp-canary-ocr-01"


def _enable_bridge(monkeypatch):
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational._TAB_BRIDGE_ORIGIN_JID", CANARY_JID
    )
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational._TAB_BRIDGE_PROJECT_ID", TAB_PROJECT
    )


def _mock_tab_state():
    from core.operational_memory.models import OperationalState, Task, LifecycleState
    s = OperationalState(project_id=TAB_PROJECT)
    t = Task(text="installare quadro Q1", source="wa", source_event_id="e1",
             source_timestamp="2026-07-01T08:00:00+00:00", owner="Mario", due="2026-07-05")
    s.tasks.append(t)
    return s


def _run(coro):
    return asyncio.get_event_loop().run_until_complete(coro)


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


def _tab_reply_mock(intent="open_tasks"):
    from core.operational_memory.models import ChatReply
    return ChatReply(
        project_id=TAB_PROJECT, intent=intent,
        reply_markdown="installare quadro Q1 → Mario (entro 5/7)",
        synthesis="", table_markdown="", actions=[], evidence_event_ids=[],
        report_id="", report_url="",
    )


# ---------------------------------------------------------------------------
# 1. stato TAB dal canary → TAB bridge fires, reply in canary
# ---------------------------------------------------------------------------
def test_stato_tab_from_canary_uses_tab_project(monkeypatch):
    _enable_bridge(monkeypatch)
    sent = []

    async def send(jid, text, **kw):
        sent.append((jid, text))

    with patch(
        "core.operational_memory.whatsapp_operational.build_operational_reply",
        new=AsyncMock(return_value=_tab_reply_mock("cmd_stato")),
    ) as mock_build:
        from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
        result = _run(maybe_handle_whatsapp_operational(
            group_jid=CANARY_JID, sender_jid="sender@s.whatsapp.net",
            first_name="Alfio", text="Genesi, stato TAB",
            send_message=send,
        ))

    assert result is True
    assert len(sent) == 1, "must reply exactly once"
    jid, text = sent[0]
    assert jid == CANARY_JID, "reply must go to CANARY, not TAB"
    assert "Vista TAB reale:" in text
    # build_operational_reply called with TAB project, not canary
    args, kwargs = mock_build.call_args
    assert args[0] == TAB_PROJECT


# ---------------------------------------------------------------------------
# 2. problemi aperti TAB → TAB bridge fires
# ---------------------------------------------------------------------------
def test_problemi_tab_from_canary(monkeypatch):
    _enable_bridge(monkeypatch)
    sent = []

    async def send(jid, text, **kw):
        sent.append((jid, text))

    with patch(
        "core.operational_memory.whatsapp_operational.build_operational_reply",
        new=AsyncMock(return_value=_tab_reply_mock("open_issues")),
    ):
        from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
        _run(maybe_handle_whatsapp_operational(
            group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
            first_name="Alfio", text="Genesi, problemi aperti TAB",
            send_message=send,
        ))

    assert len(sent) == 1
    assert sent[0][0] == CANARY_JID
    assert "Vista TAB reale:" in sent[0][1]


# ---------------------------------------------------------------------------
# 3. cosa manca nel TAB → open_tasks intent on TAB
# ---------------------------------------------------------------------------
def test_cosa_manca_tab_from_canary(monkeypatch):
    _enable_bridge(monkeypatch)
    sent = []

    async def send(jid, text, **kw):
        sent.append((jid, text))

    with patch(
        "core.operational_memory.whatsapp_operational.build_operational_reply",
        new=AsyncMock(return_value=_tab_reply_mock("open_tasks")),
    ) as mock_build:
        from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
        _run(maybe_handle_whatsapp_operational(
            group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
            first_name="Alfio", text="Genesi, cosa manca nel TAB?",
            send_message=send,
        ))

    assert mock_build.call_args[0][0] == TAB_PROJECT
    assert sent[0][0] == CANARY_JID
    assert "Vista TAB reale:" in sent[0][1]


# ---------------------------------------------------------------------------
# 4. report TAB → save=True (report link intent)
# ---------------------------------------------------------------------------
def test_report_tab_saves_report(monkeypatch):
    _enable_bridge(monkeypatch)

    async def send(jid, text, **kw):
        pass

    with patch(
        "core.operational_memory.whatsapp_operational.build_operational_reply",
        new=AsyncMock(return_value=_tab_reply_mock("cmd_report")),
    ) as mock_build:
        from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
        _run(maybe_handle_whatsapp_operational(
            group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
            first_name="Alfio", text="Genesi, report TAB",
            send_message=send,
        ))

    _, kwargs = mock_build.call_args
    assert kwargs.get("save") is True, "report TAB must save=True"


# ---------------------------------------------------------------------------
# 5. stato TAB (non-report) → save=False (no write side effects)
# ---------------------------------------------------------------------------
def test_stato_tab_does_not_save_report(monkeypatch):
    _enable_bridge(monkeypatch)

    async def send(jid, text, **kw):
        pass

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

    _, kwargs = mock_build.call_args
    assert kwargs.get("save") is False, "non-report TAB intent must save=False"


# ---------------------------------------------------------------------------
# 6. Non-canary origin → bridge does NOT fire (fail-closed)
# ---------------------------------------------------------------------------
def test_non_canary_origin_bridge_does_not_fire(monkeypatch):
    _enable_bridge(monkeypatch)
    OTHER_JID = "999000000000000001@g.us"
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational.resolve_whatsapp_project_id",
        lambda jid: "other-project" if jid == OTHER_JID else None,
    )

    sent = []
    tab_build_called = False

    async def send(jid, text, **kw):
        sent.append((jid, text))

    async def fake_build(project_id, *a, **kw):
        nonlocal tab_build_called
        if project_id == TAB_PROJECT:
            tab_build_called = True
        return _tab_reply_mock("open_tasks")

    with patch("core.operational_memory.whatsapp_operational.build_operational_reply", new=fake_build):
        from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
        _run(maybe_handle_whatsapp_operational(
            group_jid=OTHER_JID, sender_jid="s@s.whatsapp.net",
            first_name="Alfio", text="Genesi, stato TAB",
            send_message=send,
        ))

    assert not tab_build_called, "TAB build must not fire from non-canary origin"


# ---------------------------------------------------------------------------
# 7. Bridge disabled (env vars empty) → TAB keyword falls through to normal flow
# ---------------------------------------------------------------------------
def test_bridge_disabled_by_default(monkeypatch):
    # Do NOT call _enable_bridge → env vars are empty strings
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational._TAB_BRIDGE_ORIGIN_JID", ""
    )
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational._TAB_BRIDGE_PROJECT_ID", ""
    )

    tab_build_called = False

    async def send(jid, text, **kw):
        pass

    async def fake_build(project_id, *a, **kw):
        nonlocal tab_build_called
        if project_id == TAB_PROJECT:
            tab_build_called = True
        return _tab_reply_mock("open_tasks")

    with patch("core.operational_memory.whatsapp_operational.build_operational_reply", new=fake_build):
        from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
        _run(maybe_handle_whatsapp_operational(
            group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
            first_name="Alfio", text="Genesi, stato TAB",
            send_message=send,
        ))

    assert not tab_build_called, "Bridge disabled → TAB project must not be queried"


# ---------------------------------------------------------------------------
# 8. send_message is NEVER called with TAB JID
# ---------------------------------------------------------------------------
def test_no_message_sent_to_tab_jid(monkeypatch):
    _enable_bridge(monkeypatch)
    sent_jids = []

    async def send(jid, text, **kw):
        sent_jids.append(jid)

    with patch(
        "core.operational_memory.whatsapp_operational.build_operational_reply",
        new=AsyncMock(return_value=_tab_reply_mock("open_tasks")),
    ):
        from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
        _run(maybe_handle_whatsapp_operational(
            group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
            first_name="Alfio", text="Genesi, problemi aperti TAB",
            send_message=send,
        ))

    assert TAB_JID not in sent_jids, "must never send to TAB JID"
    assert all(jid == CANARY_JID for jid in sent_jids)


# ---------------------------------------------------------------------------
# 9. cosa manca? (without TAB) → normal canary flow, NOT TAB bridge
# ---------------------------------------------------------------------------
def test_cosa_manca_without_tab_uses_canary(monkeypatch):
    _enable_bridge(monkeypatch)
    called_projects = []

    async def send(jid, text, **kw):
        pass

    async def fake_build(project_id, *a, **kw):
        called_projects.append(project_id)
        return _tab_reply_mock("open_tasks")

    with patch("core.operational_memory.whatsapp_operational.build_operational_reply", new=fake_build):
        from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
        _run(maybe_handle_whatsapp_operational(
            group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
            first_name="Alfio", text="Genesi, cosa manca?",
            send_message=send,
        ))

    assert called_projects, "build_operational_reply must be called"
    assert called_projects[0] == CANARY_PROJECT, "without TAB keyword must use canary project"
    assert TAB_PROJECT not in called_projects


# ---------------------------------------------------------------------------
# 10. riepiloga TAB → briefing/digest intent, save=False (no report)
# ---------------------------------------------------------------------------
def test_riepiloga_tab(monkeypatch):
    _enable_bridge(monkeypatch)
    sent = []

    async def send(jid, text, **kw):
        sent.append((jid, text))

    with patch(
        "core.operational_memory.whatsapp_operational.build_operational_reply",
        new=AsyncMock(return_value=_tab_reply_mock("briefing")),
    ) as mock_build:
        from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
        _run(maybe_handle_whatsapp_operational(
            group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
            first_name="Alfio", text="Genesi, riepiloga TAB",
            send_message=send,
        ))

    assert sent[0][0] == CANARY_JID
    assert "Vista TAB reale:" in sent[0][1]
    _, kwargs = mock_build.call_args
    assert kwargs.get("save") is False
