"""B8.3 — Canary console mode (OPERATIONAL_TAB_BRIDGE_DEFAULT_NO_TARGET).

Flag OFF (default) → B8.2 behaviour unchanged: no-target queries answer on the
group's own project.
Flag ON + origin canary → pure operational queries WITHOUT explicit target
default to the TAB bridge; "canary" keyword pins the own project; unknown
queries without update payload fail closed (no spurious ingest); explicit
update payloads still ingest normally; TAB stays read-only.
"""
from __future__ import annotations

import asyncio

import pytest
from unittest.mock import AsyncMock, patch

CANARY_JID = "120363428502905378@g.us"
TAB_JID = "120363404290146040@g.us"
TAB_PROJECT = "tab-cefla-hq-enel-roma"
CANARY_PROJECT = "whatsapp-canary-ocr-01"


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture(autouse=True)
def _wa_env(monkeypatch):
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
        "core.operational_memory.whatsapp_operational.flush_project", AsyncMock()
    )


@pytest.fixture()
def _update_mock(monkeypatch):
    m = AsyncMock()
    monkeypatch.setattr("core.operational_memory.whatsapp_operational._safe_update", m)
    return m


def _flag(monkeypatch, value: bool):
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational._TAB_BRIDGE_DEFAULT_NO_TARGET", value
    )


def _reply_mock(intent):
    from core.operational_memory.models import ChatReply
    return ChatReply(
        project_id=TAB_PROJECT, intent=intent,
        reply_markdown="mock", synthesis="", table_markdown="",
        actions=[], evidence_event_ids=[], report_id="", report_url="",
    )


async def _invoke(text, jid=CANARY_JID, sent=None, build_mock=None):
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational

    async def send(j, t, **kw):
        if sent is not None:
            sent.append((j, t))

    with patch(
        "core.operational_memory.whatsapp_operational.build_operational_reply",
        new=build_mock or AsyncMock(return_value=_reply_mock("attention")),
    ) as mb:
        result = await maybe_handle_whatsapp_operational(
            group_jid=jid, sender_jid="s@s.whatsapp.net",
            first_name="Alfio", text=text, send_message=send,
        )
    return result, mb


# ---------------------------------------------------------------------------
# 1. Flag OFF (default) → own-project (B8.2 unchanged)
# ---------------------------------------------------------------------------

def test_flag_off_priorita_own_project(monkeypatch, _update_mock):
    _flag(monkeypatch, False)
    _, mb = _run(_invoke("Genesi, dammi solo le priorità"))
    assert mb.call_args[0][0] == CANARY_PROJECT


# ---------------------------------------------------------------------------
# 2-5. Flag ON → console default: pure no-target queries → TAB bridge
# ---------------------------------------------------------------------------

def test_flag_on_priorita_bridges_tab(monkeypatch, _update_mock):
    _flag(monkeypatch, True)
    sent = []
    _, mb = _run(_invoke("Genesi, dammi solo le priorità", sent=sent))
    assert mb.call_args[0][0] == TAB_PROJECT
    assert sent[0][0] == CANARY_JID
    assert "Vista TAB reale" in sent[0][1]


def test_flag_on_messaggio_operativo_bridges_tab(monkeypatch, _update_mock):
    _flag(monkeypatch, True)
    sent = []
    _, mb = _run(_invoke("Genesi, preparami un messaggio operativo", sent=sent,
                         build_mock=AsyncMock(return_value=_reply_mock("team_brief"))))
    assert mb.call_args[0][0] == TAB_PROJECT
    assert sent[0][0] == CANARY_JID


def test_flag_on_chi_deve_muoversi_bridges_tab(monkeypatch, _update_mock):
    _flag(monkeypatch, True)
    _, mb = _run(_invoke("Genesi, chi deve muoversi?",
                         build_mock=AsyncMock(return_value=_reply_mock("open_tasks"))))
    assert mb.call_args[0][0] == TAB_PROJECT


def test_flag_on_cosa_rischia_bridges_tab(monkeypatch, _update_mock):
    _flag(monkeypatch, True)
    _, mb = _run(_invoke("Genesi, cosa rischia di bloccarci?"))
    assert mb.call_args[0][0] == TAB_PROJECT


# ---------------------------------------------------------------------------
# 6-7. Flag ON → "canary" keyword pins own project (escape hatch)
# ---------------------------------------------------------------------------

def test_flag_on_stato_canary_own_project(monkeypatch, _update_mock):
    _flag(monkeypatch, True)
    _, mb = _run(_invoke("Genesi, stato canary",
                         build_mock=AsyncMock(return_value=_reply_mock("cmd_stato"))))
    assert mb.call_args[0][0] == CANARY_PROJECT
    # keyword stripped → query passed is "stato", not "stato canary"
    assert "canary" not in mb.call_args[0][1].lower()


def test_flag_on_nel_canary_cosa_manca_own_project(monkeypatch, _update_mock):
    _flag(monkeypatch, True)
    _, mb = _run(_invoke("Genesi, nel canary cosa manca?",
                         build_mock=AsyncMock(return_value=_reply_mock("open_tasks"))))
    assert mb.call_args[0][0] == CANARY_PROJECT


# ---------------------------------------------------------------------------
# 8. Non-canary origin + flag ON → no TAB default
# ---------------------------------------------------------------------------

def test_flag_on_non_canary_no_tab_default(monkeypatch, _update_mock):
    _flag(monkeypatch, True)
    OTHER = "999000000000000001@g.us"
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational.resolve_whatsapp_project_id",
        lambda jid: "other-project" if jid == OTHER else None,
    )
    _, mb = _run(_invoke("Genesi, dammi solo le priorità", jid=OTHER))
    assert mb.call_args[0][0] == "other-project"


# ---------------------------------------------------------------------------
# 9-10. Flag ON → unknown/non-operational query → fail-closed, no ingest
# ---------------------------------------------------------------------------

def test_flag_on_non_operational_fail_closed(monkeypatch, _update_mock):
    _flag(monkeypatch, True)
    sent = []
    _, mb = _run(_invoke("Genesi, fai una magia", sent=sent))
    # No project reply built (fail-closed hint only)
    mb.assert_not_called()
    assert sent and (_t := sent[0][1]) and ("non voglio inventare" in _t or "esco dal mio campo" in _t or "non so leggerla" in _t)
    _update_mock.assert_not_called()


def test_flag_on_borderline_unknown_fail_closed_no_ingest(monkeypatch, _update_mock):
    _flag(monkeypatch, True)
    sent = []
    _, mb = _run(_invoke("Genesi, sistemare la faccenda di ieri", sent=sent))
    mb.assert_not_called()
    _update_mock.assert_not_called()
    assert sent and (_t := sent[0][1]) and ("non voglio inventare" in _t or "esco dal mio campo" in _t or "non so leggerla" in _t)


# ---------------------------------------------------------------------------
# Update payload with flag ON → still ingested (own project, not dropped)
# ---------------------------------------------------------------------------

def test_flag_on_explicit_update_still_ingested(monkeypatch, _update_mock):
    _flag(monkeypatch, True)
    _run(_invoke("Genesi, segna che Mario ha consegnato il cavo FG16"))
    _update_mock.assert_called_once()


# ---------------------------------------------------------------------------
# Flag ON → explicit TAB keyword unchanged (B5/B8 path wins)
# ---------------------------------------------------------------------------

def test_flag_on_explicit_tab_unchanged(monkeypatch, _update_mock):
    _flag(monkeypatch, True)
    sent = []
    _, mb = _run(_invoke("Genesi, stato TAB", sent=sent,
                         build_mock=AsyncMock(return_value=_reply_mock("cmd_stato"))))
    assert mb.call_args[0][0] == TAB_PROJECT
    # query passed is the stripped one, without "TAB"
    assert "tab" not in mb.call_args[0][1].lower()
    assert "Vista TAB reale" in sent[0][1]


# ---------------------------------------------------------------------------
# Flag ON → console bridge is read-only (save=False for non-report intents)
# ---------------------------------------------------------------------------

def test_flag_on_console_bridge_read_only(monkeypatch, _update_mock):
    _flag(monkeypatch, True)
    _, mb = _run(_invoke("Genesi, dammi solo le priorità"))
    _, kwargs = mb.call_args
    assert kwargs.get("save") is False
    _update_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Flag ON → no message ever sent to TAB JID
# ---------------------------------------------------------------------------

def test_flag_on_never_sends_to_tab_jid(monkeypatch, _update_mock):
    _flag(monkeypatch, True)
    sent = []
    for q in ["Genesi, dammi solo le priorità", "Genesi, chi deve muoversi?",
              "Genesi, fai una magia", "Genesi, stato canary"]:
        _run(_invoke(q, sent=sent))
    assert all(j == CANARY_JID for j, _ in sent)
    assert TAB_JID not in [j for j, _ in sent]
