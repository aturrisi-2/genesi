"""T-A3.1 — Core reply/quoted binding (no host/bridge changes).

A reply (e.g. a voice note) is interpreted with its parent's context (photo
caption + OCR) so one complete operational item is extracted. Validates:
  * ChatMessage.reply_to_id → OperationalEvent.parent_event_id / reply_relation;
  * resolve_parent_context merges parent caption + OCR into the child;
  * extraction message of the child carries the parent context (task complete);
  * audio reply to image-with-caption / to OCR-image → full context;
  * no parent / parent not found → no crash, child stays standalone;
  * Telegram-style and WhatsApp-style replies hit the SAME core;
  * evidence/relation keep parent and child separate;
  * normal text / no-reply events unchanged.

analyze_audio not needed (attachments pre-built). Parent lookup uses a tmp store.
"""

from __future__ import annotations

import pytest

import core.operational_memory.event_store as es
from core.operational_memory.context_binding import resolve_parent_context
from core.operational_memory.chat_presence import _event_from_message
from core.operational_memory.watcher_engine import event_to_extraction_message
from core.operational_memory.models import ChatAttachment, ChatMessage, OperationalEvent


PROJECT = "ta3-bind-proj"
CAPTION = "Dentro cavedio L03 - Da collegare potenziometro"
OCR = "EWC-10 V10"
VOICE = "lo facciamo domattina, prima cosa"


@pytest.fixture
def tmp_store(monkeypatch, tmp_path):
    monkeypatch.setattr(es, "_BASE_DIR", tmp_path)
    return tmp_path


def _img_parent(event_id="IMG1", caption=CAPTION, ocr=OCR):
    return OperationalEvent(
        event_id=event_id, project_id=PROJECT, source="whatsapp", sender="Luca",
        type="image", content=caption, extracted_text=ocr,
        attachment_type="image", media_description="foto quadro elettrico")


def _voice_reply_msg(parent_id="IMG1", source="whatsapp"):
    return ChatMessage(
        project_id=PROJECT, message_id="VOICE1", source=source, sender="Marco",
        text="", reply_to_id=parent_id,
        attachments=[ChatAttachment(type="voice", extracted_text=VOICE,
                                    metadata={"extraction_status": "transcribed"})],
    )


# --------------------------------------------------------------------------- #
# Mapping
# --------------------------------------------------------------------------- #


def test_reply_to_id_maps_to_parent_event_id():
    event = _event_from_message(_voice_reply_msg())
    assert event.parent_event_id == "IMG1"
    assert event.reply_relation == "reply_to"
    assert event.event_id == "VOICE1"           # child evidence is its own id
    assert event.parent_event_id != event.event_id   # separate from parent


def test_inline_parent_snapshot_seeded_when_provided():
    msg = ChatMessage(project_id=PROJECT, message_id="V2", reply_to_id="P2",
                      parent_text="caption inline", parent_attachment_summary="image")
    event = _event_from_message(msg)
    assert event.parent_context == "caption inline\nimage"


# --------------------------------------------------------------------------- #
# Parent context resolution
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_audio_reply_to_image_with_caption_full_context(tmp_store):
    await es.save_events(PROJECT, [_img_parent()])
    event = _event_from_message(_voice_reply_msg())
    await resolve_parent_context(event, PROJECT)
    assert CAPTION in event.parent_context
    assert OCR in event.parent_context              # OCR (extracted_text) merged too
    # Child's own transcription stays in extracted_text (not overwritten).
    assert event.extracted_text == VOICE


@pytest.mark.asyncio
async def test_extraction_message_contains_parent_and_child(tmp_store):
    await es.save_events(PROJECT, [_img_parent()])
    event = _event_from_message(_voice_reply_msg())
    await resolve_parent_context(event, PROJECT)
    msg = event_to_extraction_message(event)
    assert VOICE in msg and CAPTION in msg and OCR in msg     # complete task context
    assert "messaggio collegato" in msg                       # parent flagged as a source


@pytest.mark.asyncio
async def test_audio_reply_to_ocr_only_image(tmp_store):
    await es.save_events(PROJECT, [_img_parent(caption="", ocr=OCR)])
    event = _event_from_message(_voice_reply_msg())
    await resolve_parent_context(event, PROJECT)
    assert OCR in event.parent_context


# --------------------------------------------------------------------------- #
# Fallback / no-crash
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_parent_not_found_no_crash_keeps_inline(tmp_store):
    await es.save_events(PROJECT, [])             # empty store
    msg = _voice_reply_msg(parent_id="MISSING")
    msg.parent_text = "snapshot inline"
    event = _event_from_message(msg)
    await resolve_parent_context(event, PROJECT)  # must not raise
    assert event.parent_context == "snapshot inline"   # inline fallback kept
    assert event.extracted_text == VOICE


@pytest.mark.asyncio
async def test_audio_without_parent_unchanged():
    msg = ChatMessage(project_id=PROJECT, message_id="V3", source="whatsapp",
                      attachments=[ChatAttachment(type="voice", extracted_text=VOICE)])
    event = _event_from_message(msg)
    assert event.parent_event_id is None
    await resolve_parent_context(event, PROJECT)  # no-op, no crash
    assert event.parent_context == ""
    msg_out = event_to_extraction_message(event)
    assert "messaggio collegato" not in msg_out


def test_normal_text_event_unchanged():
    msg = ChatMessage(project_id=PROJECT, message_id="T1", source="whatsapp",
                      sender="Ann", text="materiale arrivato")
    event = _event_from_message(msg)
    out = event_to_extraction_message(event)
    assert out.endswith("materiale arrivato")
    assert "Messaggio collegato" not in out


# --------------------------------------------------------------------------- #
# Platform independence
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["whatsapp", "telegram"])
async def test_same_core_for_whatsapp_and_telegram_replies(tmp_store, source):
    await es.save_events(PROJECT, [_img_parent()])
    event = _event_from_message(_voice_reply_msg(source=source))
    await resolve_parent_context(event, PROJECT)
    assert CAPTION in event.parent_context and OCR in event.parent_context
    assert event.reply_relation == "reply_to"


def test_text_reply_also_gets_parent_context():
    # Platform-independent: a plain-text reply carrying parent_context is linked too.
    msg = ChatMessage(project_id=PROJECT, message_id="TR1", source="telegram",
                      sender="Marco", text="ok domattina", reply_to_id="IMG1",
                      parent_text=CAPTION)
    event = _event_from_message(msg)
    out = event_to_extraction_message(event)
    assert "ok domattina" in out and CAPTION in out and "Messaggio collegato" in out
