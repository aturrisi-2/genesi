"""T-A3.2 — Adapters forward reply_to_id / parent context to the core (T-A3.1).

Adapters only pass metadata; the binding logic lives in the core. Validates:
  * Telegram reply_to_message → ChatMessage.reply_to_id + parent snapshot;
  * Telegram reply to media/caption → parent context fields populated;
  * WhatsApp bridge reply_to_id → ChatMessage.reply_to_id;
  * WhatsApp without quoted id → unchanged (reply_to_id None);
  * GroupChatRequest backward compatible (no new fields) + accepts reply_to_id;
  * normal messages / pure invocation / reply OFF unchanged.

No env/restart/live, no Baileys index.js. Reply OFF.
"""

from __future__ import annotations

import asyncio
import json

import pytest


# --------------------------------------------------------------------------- #
# Telegram host helper: reply_to_message → parent snapshot
# --------------------------------------------------------------------------- #


def test_telegram_parent_from_reply_text():
    import core.telegram_bot as tb
    msg = {"reply_to_message": {"message_id": 555, "text": "Dentro cavedio L03"}}
    rid, ptext, ptype, psum = tb._telegram_parent_from_reply(msg)
    assert rid == "555"
    assert ptext == "Dentro cavedio L03"
    assert ptype == "" and psum == ""


def test_telegram_parent_from_reply_photo_caption():
    import core.telegram_bot as tb
    msg = {"reply_to_message": {"message_id": 9, "caption": "EWC-10 V10",
                                "photo": [{"file_id": "P"}]}}
    rid, ptext, ptype, psum = tb._telegram_parent_from_reply(msg)
    assert rid == "9" and ptext == "EWC-10 V10" and ptype == "image" and psum == "image"


def test_telegram_parent_from_reply_none():
    import core.telegram_bot as tb
    assert tb._telegram_parent_from_reply({"text": "hi"}) == ("", "", "", "")


# --------------------------------------------------------------------------- #
# Telegram bridge: reply params → ChatMessage
# --------------------------------------------------------------------------- #


TG_CHAT = "-5009998888"
TG_PROJECT = "tg-reply-proj"


@pytest.fixture
def tg_enabled(monkeypatch):
    monkeypatch.setenv("OPERATIONAL_MEMORY_TELEGRAM_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_CHAT_PROJECT_MAP", json.dumps({TG_CHAT: TG_PROJECT}))
    monkeypatch.setenv("TELEGRAM_OPERATIONAL_REPLY_ENABLED", "false")  # reply OFF
    return monkeypatch


@pytest.mark.asyncio
async def test_telegram_bridge_sets_reply_to_id(tg_enabled):
    from core.operational_memory.telegram_operational import maybe_handle_operational
    captured = []

    async def updater(message):
        captured.append(message)

    async def send(*a, **k):
        raise AssertionError("reply OFF → no send")

    handled = await maybe_handle_operational(
        chat_id=TG_CHAT, from_id=7, first_name="Marco",
        text="ok domattina", send_message=send, message_id=101,
        reply_to_id="9", parent_text="EWC-10 V10", parent_media_type="image",
        parent_attachment_summary="image", updater=updater)
    await asyncio.sleep(0)
    assert handled is False                      # reply OFF → silent ingest
    m = captured[0]
    assert m.reply_to_id == "9"
    assert m.parent_text == "EWC-10 V10"
    assert m.parent_media_type == "image"


@pytest.mark.asyncio
async def test_telegram_bridge_no_reply_unchanged(tg_enabled):
    from core.operational_memory.telegram_operational import maybe_handle_operational
    captured = []

    async def updater(message):
        captured.append(message)

    async def send(*a, **k):
        return None

    await maybe_handle_operational(
        chat_id=TG_CHAT, from_id=7, first_name="Ann",
        text="materiale arrivato", send_message=send, message_id=102, updater=updater)
    await asyncio.sleep(0)
    assert captured[0].reply_to_id is None


# --------------------------------------------------------------------------- #
# WhatsApp bridge: reply_to_id → ChatMessage
# --------------------------------------------------------------------------- #


WA_JID = "120363000000000000@g.us"
WA_PROJECT = "wa-reply-proj"


@pytest.fixture
def wa_enabled(monkeypatch):
    monkeypatch.setenv("OPERATIONAL_MEMORY_WHATSAPP_ENABLED", "true")
    monkeypatch.setenv("WHATSAPP_CHAT_PROJECT_MAP", json.dumps({WA_JID: WA_PROJECT}))
    monkeypatch.delenv("WHATSAPP_OPERATIONAL_REPLY_ENABLED", raising=False)  # reply OFF
    return monkeypatch


@pytest.mark.asyncio
async def test_whatsapp_bridge_sets_reply_to_id(wa_enabled):
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    captured = []

    async def updater(message):
        captured.append(message)

    async def send(*a, **k):
        raise AssertionError("reply OFF → no send")

    handled = await maybe_handle_whatsapp_operational(
        WA_JID, "393331112222", "Marco", "ok domattina", send,
        message_id="wm-reply", reply_to_id="PARENT_MSG_ID",
        parent_text="Dentro cavedio L03", updater=updater)
    await asyncio.sleep(0)
    assert handled is True
    assert captured[0].reply_to_id == "PARENT_MSG_ID"
    assert captured[0].parent_text == "Dentro cavedio L03"


@pytest.mark.asyncio
async def test_whatsapp_bridge_without_reply_unchanged(wa_enabled):
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    captured = []

    async def updater(message):
        captured.append(message)

    async def send(*a, **k):
        return None

    await maybe_handle_whatsapp_operational(
        WA_JID, "393331112222", "Ann", "consegna venerdì", send,
        message_id="wm-plain", updater=updater)
    await asyncio.sleep(0)
    assert captured[0].reply_to_id is None


# --------------------------------------------------------------------------- #
# GroupChatRequest backward compatibility
# --------------------------------------------------------------------------- #


def test_group_chat_request_backward_compatible():
    from api.chat import GroupChatRequest
    # No new fields → still valid (old Baileys payload).
    r = GroupChatRequest(text="ciao", sender_name="A", sender_id="x", group_id=WA_JID)
    assert r.reply_to_id is None
    # With reply_to_id → accepted.
    r2 = GroupChatRequest(text="ok", sender_name="A", sender_id="x", group_id=WA_JID,
                          reply_to_id="QID", parent_text="cap")
    assert r2.reply_to_id == "QID" and r2.parent_text == "cap"


# --------------------------------------------------------------------------- #
# Pure invocation still not ingested (reply params don't change gating)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_whatsapp_pure_invocation_not_ingested_with_reply(wa_enabled, monkeypatch):
    monkeypatch.setenv("WHATSAPP_OPERATIONAL_REPLY_ENABLED", "true")
    import core.operational_memory.whatsapp_operational as mod
    from core.operational_memory.models import ChatReply

    async def fake_flush(project_id, rebuild=True):
        return None

    async def fake_reply(project_id, query, report_base_url="", invoked_by="", save=True):
        return ChatReply(project_id=project_id, intent="remaining_open", reply_markdown="X")

    monkeypatch.setattr(mod, "flush_project", fake_flush)
    monkeypatch.setattr(mod, "build_operational_reply", fake_reply)
    ingested = []

    async def updater(message):
        ingested.append(message)

    sent = []

    async def send(to, text, *a, **k):
        sent.append((to, text))

    await mod.maybe_handle_whatsapp_operational(
        WA_JID, "393331112222", "Ann", "Genesi, cosa resta aperto?", send,
        message_id="inv1", reply_to_id="SOMEPARENT", updater=updater)
    assert ingested == []          # pure query still not stored even with reply_to_id
