from __future__ import annotations

import asyncio
import json

import pytest

from core.operational_memory.models import ChatReply


GROUP_JID = "120363000000000000@g.us"
SENDER_JID = "393331234567"
PROJECT = "wa-test-proj"


def _spies():
    sent = []      # (to, text)
    ingested = []  # ChatMessage

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


# --------------------------------------------------------------------------- #
# Config / mapping
# --------------------------------------------------------------------------- #


def test_whatsapp_mapped_group_resolves_project(enabled):
    from core.operational_memory.whatsapp_operational import resolve_whatsapp_project_id
    assert resolve_whatsapp_project_id(GROUP_JID) == PROJECT
    assert resolve_whatsapp_project_id("999@g.us") is None


# --------------------------------------------------------------------------- #
# Default OFF
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_whatsapp_operational_disabled_by_default(monkeypatch):
    # No env set → disabled → bridge does not claim, no ingest, no send.
    monkeypatch.delenv("OPERATIONAL_MEMORY_WHATSAPP_ENABLED", raising=False)
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "Genesi, fammi il punto", send, message_id="m1", updater=updater)
    await asyncio.sleep(0)
    assert handled is False and sent == [] and ingested == []


@pytest.mark.asyncio
async def test_whatsapp_existing_behavior_unchanged_when_disabled(monkeypatch):
    monkeypatch.setenv("OPERATIONAL_MEMORY_WHATSAPP_ENABLED", "false")
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "ciao a tutti", send, message_id="m2", updater=updater)
    await asyncio.sleep(0)
    assert handled is False           # control returned to existing flow
    assert sent == [] and ingested == []


@pytest.mark.asyncio
async def test_whatsapp_unmapped_group_not_ingested(enabled):
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        "999999@g.us", SENDER_JID, "Ann", "Genesi, fammi il punto", send, message_id="m3", updater=updater)
    await asyncio.sleep(0)
    assert handled is False           # unmapped → legacy, not operational
    assert sent == [] and ingested == []


# --------------------------------------------------------------------------- #
# Mapped group: silent ingest + claim
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_whatsapp_mapped_group_silent_ingest_when_enabled(enabled):
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "domani portiamo i pezzi", send, message_id="m4", updater=updater)
    await asyncio.sleep(0)
    assert handled is True            # operational-dominant: claims, suppresses empathic
    assert sent == []                 # silent: no reply
    assert [m.message_id for m in ingested] == ["m4"]   # ingested
    assert ingested[0].chat_id == GROUP_JID and ingested[0].source == "whatsapp"


@pytest.mark.asyncio
async def test_whatsapp_media_placeholder_ingested_for_mapped_group(enabled):
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "", send, message_id="m5", media_type="image", updater=updater)
    await asyncio.sleep(0)
    assert handled is True
    assert ingested and ingested[0].attachments
    att = ingested[0].attachments[0]
    assert att.type == "image" and att.metadata.get("placeholder") is True


# --------------------------------------------------------------------------- #
# Invocation reply gating
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_whatsapp_invocation_reply_disabled_by_default(enabled):
    # reply flag not set → default OFF → invocation does not send a live reply.
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "Genesi, fammi il punto", send, message_id="m6", updater=updater)
    await asyncio.sleep(0)
    assert handled is True             # claimed
    assert sent == []                  # but no reply sent (reply disabled)


@pytest.mark.asyncio
async def test_whatsapp_invocation_reply_enabled_uses_group_jid(enabled, monkeypatch):
    monkeypatch.setenv("WHATSAPP_OPERATIONAL_REPLY_ENABLED", "true")
    import core.operational_memory.whatsapp_operational as mod

    async def fake_flush(project_id, rebuild=True):
        return None

    async def fake_reply(project_id, query, report_base_url="", invoked_by="", save=True):
        return ChatReply(project_id=project_id, intent="briefing", reply_markdown="BODY", report_id="r", report_url="u")

    monkeypatch.setattr(mod, "flush_project", fake_flush)
    monkeypatch.setattr(mod, "build_operational_reply", fake_reply)
    sent, ingested, send, updater = _spies()
    handled = await mod.maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "Genesi, fammi il punto", send, message_id="m7", updater=updater)
    assert handled is True
    assert len(sent) == 1
    to, body = sent[0]
    assert to == GROUP_JID            # reply goes to the GROUP jid, not the sender
    assert to != SENDER_JID
    assert "BODY" in body and "📄 Report: u" in body


@pytest.mark.asyncio
async def test_whatsapp_pure_invocation_not_ingested(enabled, monkeypatch):
    monkeypatch.setenv("WHATSAPP_OPERATIONAL_REPLY_ENABLED", "true")
    import core.operational_memory.whatsapp_operational as mod

    flushed = []

    async def fake_flush(project_id, rebuild=True):
        flushed.append(project_id)

    async def fake_reply(project_id, query, report_base_url="", invoked_by="", save=True):
        return ChatReply(project_id=project_id, intent="remaining_open", reply_markdown="X", report_id="", report_url="")

    monkeypatch.setattr(mod, "flush_project", fake_flush)
    monkeypatch.setattr(mod, "build_operational_reply", fake_reply)
    sent, ingested, send, updater = _spies()
    await mod.maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "Genesi, cosa resta aperto?", send, message_id="m8", updater=updater)
    assert flushed == [PROJECT]        # rebuilt before reply
    assert ingested == []              # pure query NOT stored as an event


# --------------------------------------------------------------------------- #
# No hardcoding
# --------------------------------------------------------------------------- #


def test_no_whatsapp_domain_hardcoding():
    import re
    import core.operational_memory.whatsapp_operational as mod
    body = open(mod.__file__, "r", encoding="utf-8").read().lower()
    for token in ["test tab", "tab cefla", "cantiere", "corridoio", "pane", "quadro elettrico", "@g.us\":\"wa-"]:
        assert not re.search(rf"{re.escape(token)}", body), f"hardcoded token: {token}"


# =========================================================================== #
# STEP 2 — real silent ingest, suppression, reply gating
# =========================================================================== #

import json as _json
from unittest.mock import AsyncMock

_EMPTY_LLM = _json.dumps({"decisions": [], "tasks": [], "issues": [], "information": [], "open_questions": []})


async def _drain_background_tasks():
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


@pytest.mark.asyncio
async def test_whatsapp_flag_off_process_message_legacy_unchanged(monkeypatch):
    # Flag OFF → bridge contract is "not handled" → the whatsapp_bot hook falls
    # through to the legacy path unchanged.
    monkeypatch.delenv("OPERATIONAL_MEMORY_WHATSAPP_ENABLED", raising=False)
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "domani portiamo i pezzi", send, message_id="l1", updater=updater)
    await asyncio.sleep(0)
    assert handled is False and sent == [] and ingested == []
    # hook wired and flag-guarded
    src = open("core/whatsapp_bot.py", "r", encoding="utf-8").read()
    assert "maybe_handle_whatsapp_operational" in src
    assert "if is_group and group_jid:" in src


@pytest.mark.asyncio
async def test_whatsapp_unmapped_group_process_message_legacy_unchanged(enabled):
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        "000000@g.us", SENDER_JID, "Ann", "domani portiamo i pezzi", send, message_id="l2", updater=updater)
    await asyncio.sleep(0)
    assert handled is False and sent == [] and ingested == []


@pytest.mark.asyncio
async def test_whatsapp_mapped_group_silent_update_creates_event(enabled, monkeypatch, tmp_path):
    # Real silent_update path: the message must become an operational event in the
    # store, scoped to the mapped project_id.
    from core.operational_memory import event_store, incremental_index, snapshot_store, state_store
    monkeypatch.setattr(event_store, "_BASE_DIR", tmp_path / "events")
    monkeypatch.setattr(state_store, "_BASE_DIR", tmp_path / "state")
    monkeypatch.setattr(snapshot_store, "_BASE_DIR", tmp_path / "snap")
    monkeypatch.setattr(snapshot_store, "_LIFECYCLE_BASE_DIR", tmp_path / "lcsnap")
    monkeypatch.setattr(incremental_index, "_BASE_DIR", tmp_path / "idx")
    monkeypatch.setattr("core.operational_memory.extractor.llm_service._call_model", AsyncMock(return_value=_EMPTY_LLM))
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational

    sent = []

    async def send(to, text, *a, **k):
        sent.append((to, text))

    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "domani portiamo i pezzi al deposito", send, message_id="ev1")
    await _drain_background_tasks()
    events = await event_store.list_events(PROJECT)
    assert handled is True
    assert sent == []
    assert any(e.event_id == "ev1" and "deposito" in e.content for e in events)


@pytest.mark.asyncio
async def test_whatsapp_mapped_group_suppresses_empathic_auto_intervention(enabled):
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "messaggio qualunque", send, message_id="s1", updater=updater)
    await asyncio.sleep(0)
    assert handled is True   # claimed → host bot returns → empathic suppressed
    assert sent == []


@pytest.mark.asyncio
async def test_whatsapp_pure_invocation_reply_disabled_no_send_but_handled(enabled):
    # reply flag default OFF
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "Genesi, cosa resta aperto?", send, message_id="p1", updater=updater)
    await asyncio.sleep(0)
    assert handled is True
    assert sent == []
    assert ingested == []   # pure query NOT stored even with reply OFF


@pytest.mark.asyncio
async def test_whatsapp_update_invocation_reply_disabled_ingests_update(enabled):
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "Genesi, segna che il materiale è confermato", send, message_id="u1", updater=updater)
    await asyncio.sleep(0)
    assert handled is True
    assert sent == []                                  # reply OFF → no send
    assert [m.message_id for m in ingested] == ["u1"]  # update captured


@pytest.mark.asyncio
async def test_whatsapp_reply_enabled_sends_to_group_jid_not_sender(enabled, monkeypatch):
    monkeypatch.setenv("WHATSAPP_OPERATIONAL_REPLY_ENABLED", "true")
    import core.operational_memory.whatsapp_operational as mod

    async def fake_flush(project_id, rebuild=True):
        return None

    async def fake_reply(project_id, query, report_base_url="", invoked_by="", save=True):
        return ChatReply(project_id=project_id, intent="briefing", reply_markdown="B", report_id="r", report_url="u")

    monkeypatch.setattr(mod, "flush_project", fake_flush)
    monkeypatch.setattr(mod, "build_operational_reply", fake_reply)
    sent, ingested, send, updater = _spies()
    await mod.maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "Genesi, fammi il punto", send, message_id="g1", updater=updater)
    assert len(sent) == 1 and sent[0][0] == GROUP_JID and sent[0][0] != SENDER_JID


def test_whatsapp_private_chat_mapping_works_only_if_explicitly_mapped(monkeypatch):
    priv = "393331234567@s.whatsapp.net"
    monkeypatch.setenv("OPERATIONAL_MEMORY_WHATSAPP_ENABLED", "true")
    monkeypatch.setenv("WHATSAPP_CHAT_PROJECT_MAP", json.dumps({priv: "priv-proj"}))
    from core.operational_memory.whatsapp_operational import resolve_whatsapp_project_id
    assert resolve_whatsapp_project_id(priv) == "priv-proj"
    assert resolve_whatsapp_project_id("999@s.whatsapp.net") is None


@pytest.mark.asyncio
async def test_whatsapp_media_placeholder_silent_update(enabled):
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "", send, message_id="md1", media_type="document", updater=updater)
    await asyncio.sleep(0)
    assert handled is True
    att = ingested[0].attachments[0]
    assert att.type == "document" and att.metadata.get("placeholder") is True


@pytest.mark.asyncio
async def test_whatsapp_no_double_reply_when_operational_handles(enabled):
    # When the bridge claims (handled True) on a normal message it sends nothing
    # itself and the host returns → the legacy send is never reached.
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "ci vediamo dopo", send, message_id="d1", updater=updater)
    await asyncio.sleep(0)
    assert handled is True and sent == []


def test_no_whatsapp_domain_hardcoding_step2():
    import re
    import core.operational_memory.whatsapp_operational as mod
    body = open(mod.__file__, "r", encoding="utf-8").read().lower()
    for token in ["test tab", "tab cefla", "cantiere", "corridoio", "pane", "quadro elettrico", "120363", "@g.us\":\"wa-"]:
        assert not re.search(rf"{re.escape(token)}", body), f"hardcoded token: {token}"
