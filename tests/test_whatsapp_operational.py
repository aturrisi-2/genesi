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
