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


# =========================================================================== #
# MEDIA STEP 2 — media/OCR attached to silent ingest (mapped chats only)
# =========================================================================== #

from core.operational_memory.media_analyzer import MediaAnalysisResult


def _img_res(text="ROOM 12 READY", status="text_extracted"):
    return MediaAnalysisResult(
        attachment_path="x", attachment_type="image", extracted_text=text,
        media_description="immagine", extraction_status=status,
        extraction_confidence="high" if text else "low", metadata={"file_name": "f"})


def _analyzer_spy(monkeypatch, result=None, raises=False):
    calls = {"n": 0}

    def spy(p):
        calls["n"] += 1
        if raises:
            raise RuntimeError("ocr boom")
        return result if result is not None else _img_res()

    monkeypatch.setattr("core.operational_memory.media_processor.analyze_media", spy)
    return calls


@pytest.mark.asyncio
async def test_whatsapp_mapped_image_media_runs_analyzer_and_silent_update(enabled, monkeypatch, tmp_path):
    calls = _analyzer_spy(monkeypatch, _img_res("ROOM 12 READY"))
    (tmp_path / "img1").write_bytes(b"fake")
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "vedi foto", send, message_id="i1",
        media_type="image", media_id="img1", media_dir=str(tmp_path), updater=updater)
    await asyncio.sleep(0)
    assert handled is True and sent == []
    assert calls["n"] == 1
    att = ingested[0].attachments[0]
    assert att.type == "image" and att.extracted_text == "ROOM 12 READY"
    assert ingested[0].text == "vedi foto"          # original message text preserved


@pytest.mark.asyncio
async def test_whatsapp_unmapped_media_does_not_run_analyzer(enabled, monkeypatch, tmp_path):
    calls = _analyzer_spy(monkeypatch)
    (tmp_path / "img1").write_bytes(b"fake")
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        "999@g.us", SENDER_JID, "Ann", "vedi foto", send, message_id="i2",
        media_type="image", media_id="img1", media_dir=str(tmp_path), updater=updater)
    await asyncio.sleep(0)
    assert handled is False and ingested == [] and calls["n"] == 0


@pytest.mark.asyncio
async def test_whatsapp_flag_off_media_does_not_run_analyzer(monkeypatch, tmp_path):
    monkeypatch.delenv("OPERATIONAL_MEMORY_WHATSAPP_ENABLED", raising=False)
    calls = _analyzer_spy(monkeypatch)
    (tmp_path / "img1").write_bytes(b"fake")
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "vedi foto", send, message_id="i3",
        media_type="image", media_id="img1", media_dir=str(tmp_path), updater=updater)
    await asyncio.sleep(0)
    assert handled is False and calls["n"] == 0


@pytest.mark.asyncio
async def test_whatsapp_media_missing_file_becomes_placeholder(enabled, monkeypatch, tmp_path):
    calls = _analyzer_spy(monkeypatch)   # must NOT be called (file missing)
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "", send, message_id="i4",
        media_type="image", media_id="missing", media_dir=str(tmp_path), updater=updater)
    await asyncio.sleep(0)
    assert handled is True and sent == []
    assert ingested[0].attachments[0].metadata["extraction_status"] == "file_missing"
    assert calls["n"] == 0


@pytest.mark.asyncio
async def test_whatsapp_media_path_outside_allowed_dir_rejected(enabled, monkeypatch, tmp_path):
    calls = _analyzer_spy(monkeypatch)
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "", send, message_id="i5",
        media_type="image", media_id="../../etc/passwd", media_dir=str(tmp_path), updater=updater)
    await asyncio.sleep(0)
    assert ingested[0].attachments[0].metadata["extraction_status"] == "rejected_path"
    assert calls["n"] == 0   # never read the file


@pytest.mark.asyncio
async def test_whatsapp_media_ocr_failure_does_not_block_ingest(enabled, monkeypatch, tmp_path):
    _analyzer_spy(monkeypatch, raises=True)
    (tmp_path / "img1").write_bytes(b"fake")
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "", send, message_id="i6",
        media_type="image", media_id="img1", media_dir=str(tmp_path), updater=updater)
    await asyncio.sleep(0)
    assert handled is True
    assert ingested[0].attachments[0].metadata["extraction_status"] == "analysis_error"


@pytest.mark.asyncio
async def test_whatsapp_media_text_is_available_to_operational_event(enabled, monkeypatch, tmp_path):
    from core.operational_memory.chat_presence import _event_from_message
    _analyzer_spy(monkeypatch, _img_res("DELIVERY DONE"))
    (tmp_path / "img1").write_bytes(b"fake")
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "guarda qui", send, message_id="i7",
        media_type="image", media_id="img1", media_dir=str(tmp_path), updater=updater)
    await asyncio.sleep(0)
    event = _event_from_message(ingested[0])
    assert event.extracted_text == "DELIVERY DONE"   # OCR available to the event
    assert event.content == "guarda qui"             # original text not lost


@pytest.mark.asyncio
async def test_whatsapp_media_no_reply_when_reply_disabled(enabled, monkeypatch, tmp_path):
    _analyzer_spy(monkeypatch, _img_res("X"))
    (tmp_path / "img1").write_bytes(b"fake")
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "vedi", send, message_id="i8",
        media_type="image", media_id="img1", media_dir=str(tmp_path), updater=updater)
    await asyncio.sleep(0)
    assert handled is True and sent == []


@pytest.mark.asyncio
async def test_whatsapp_media_reply_enabled_mock_sends_to_group_jid(enabled, monkeypatch, tmp_path):
    monkeypatch.setenv("WHATSAPP_OPERATIONAL_REPLY_ENABLED", "true")
    import core.operational_memory.whatsapp_operational as mod
    _analyzer_spy(monkeypatch, _img_res("X"))
    (tmp_path / "img1").write_bytes(b"fake")

    async def fake_reply(project_id, query, report_base_url="", invoked_by="", save=True):
        return ChatReply(project_id=project_id, intent="briefing", reply_markdown="B", report_id="r", report_url="u")

    async def fake_flush(project_id, rebuild=True):
        return None

    monkeypatch.setattr(mod, "build_operational_reply", fake_reply)
    monkeypatch.setattr(mod, "flush_project", fake_flush)
    sent, ingested, send, updater = _spies()
    await mod.maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "Genesi, fammi il punto", send, message_id="i9",
        media_type="image", media_id="img1", media_dir=str(tmp_path), updater=updater)
    assert len(sent) == 1 and sent[0][0] == GROUP_JID and sent[0][0] != SENDER_JID


@pytest.mark.asyncio
async def test_whatsapp_media_no_double_reply_when_operational_handles(enabled, monkeypatch, tmp_path):
    _analyzer_spy(monkeypatch, _img_res("X"))
    (tmp_path / "img1").write_bytes(b"fake")
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "foto del lavoro", send, message_id="i10",
        media_type="image", media_id="img1", media_dir=str(tmp_path), updater=updater)
    await asyncio.sleep(0)
    assert handled is True and sent == []


@pytest.mark.asyncio
async def test_whatsapp_update_invocation_with_media_ingested(enabled, monkeypatch, tmp_path):
    # Scenario 6: "Genesi, segna che il documento ricevuto è valido" + media → ingested, no send.
    _analyzer_spy(monkeypatch, _img_res("DOC OK"))
    (tmp_path / "doc1").write_bytes(b"fake")
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "Genesi, segna che il documento ricevuto è valido", send,
        message_id="i11", media_type="document", media_id="doc1", media_dir=str(tmp_path), updater=updater)
    await asyncio.sleep(0)
    assert handled is True and sent == []
    assert [m.message_id for m in ingested] == ["i11"]
    assert ingested[0].attachments and ingested[0].attachments[0].extracted_text == "DOC OK"


@pytest.mark.asyncio
async def test_whatsapp_pure_invocation_with_media_not_ingested(enabled, monkeypatch, tmp_path):
    # Scenario 5: pure invocation with media, reply OFF → handled, no ingest item, no send.
    _analyzer_spy(monkeypatch, _img_res("X"))
    (tmp_path / "img1").write_bytes(b"fake")
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Ann", "Genesi, cosa resta aperto?", send, message_id="i12",
        media_type="image", media_id="img1", media_dir=str(tmp_path), updater=updater)
    await asyncio.sleep(0)
    assert handled is True and sent == [] and ingested == []


def test_whatsapp_media_no_hardcoding():
    import re
    import core.operational_memory.whatsapp_operational as mod
    body = open(mod.__file__, "r", encoding="utf-8").read().lower()
    for token in ["test tab", "tab cefla", "cantiere", "corridoio", "pane", "quadro elettrico", "120363", "genesi-baileys"]:
        assert not re.search(rf"{re.escape(token)}", body), f"hardcoded token: {token}"


# =========================================================================== #
# B0.1 — marker-only canary group jid diagnostic (in whatsapp_bot.handle_update)
# =========================================================================== #

MARKER = "GENESI_CANARY_JID_CHECK_20260621"


def _wa_payload(group_id, body, sender="393331234567", mtype="text"):
    msg = {"from": sender, "id": "mk1", "type": mtype}
    if mtype == "text":
        msg["text"] = {"body": body}
    value = {"contacts": [{"wa_id": sender, "profile": {"name": "Ann"}}], "messages": [msg]}
    if group_id:
        value["metadata"] = {"group_id": group_id}
    return {"entry": [{"changes": [{"value": value}]}]}


def _patch_bot(monkeypatch):
    import core.whatsapp_bot as bot
    logs = []
    calls = {"process": 0}

    def fake_log(event, **kw):
        logs.append((event, kw))

    async def fake_process(*a, **k):
        calls["process"] += 1

    monkeypatch.setattr(bot, "log", fake_log)
    monkeypatch.setattr(bot, "_process_message", fake_process)
    return bot, logs, calls


@pytest.mark.asyncio
async def test_whatsapp_canary_marker_logs_group_jid(monkeypatch):
    bot, logs, calls = _patch_bot(monkeypatch)
    await bot.handle_update(_wa_payload("120999000000@g.us", MARKER))
    seen = [kw for ev, kw in logs if ev == "WA_CANARY_GROUP_JID_SEEN"]
    assert seen and seen[0]["gid"] == "120999000000@g.us"
    assert "@g.us" in seen[0]["gid"]
    assert seen[0]["sender"].endswith("***")          # sender masked
    assert MARKER not in str(seen[0])                  # full text not logged


@pytest.mark.asyncio
async def test_whatsapp_canary_marker_not_logged_for_normal_messages(monkeypatch):
    bot, logs, calls = _patch_bot(monkeypatch)
    await bot.handle_update(_wa_payload("120999000000@g.us", "ciao a tutti"))
    assert not any(ev == "WA_CANARY_GROUP_JID_SEEN" for ev, _ in logs)


@pytest.mark.asyncio
async def test_whatsapp_canary_marker_private_chat_does_not_log_group_jid(monkeypatch):
    bot, logs, calls = _patch_bot(monkeypatch)
    await bot.handle_update(_wa_payload(None, MARKER))   # no group_id → private
    assert not any(ev == "WA_CANARY_GROUP_JID_SEEN" for ev, _ in logs)
    # optional ignored log, never a group jid
    assert all("@g.us" not in str(kw.get("gid", "")) for ev, kw in logs)


@pytest.mark.asyncio
async def test_whatsapp_canary_marker_does_not_change_processing_behavior(monkeypatch):
    bot, logs, calls = _patch_bot(monkeypatch)
    await bot.handle_update(_wa_payload("120999000000@g.us", MARKER))
    assert calls["process"] == 1   # message still flows to _process_message


def test_no_hardcoding_canary_diagnostic():
    src = open("core/whatsapp_bot.py", "r", encoding="utf-8").read()
    # marker is allowed; the diagnostic must log the variable, not a real jid
    assert MARKER in src
    assert 'log("WA_CANARY_GROUP_JID_SEEN", gid=gid' in src


# =========================================================================== #
# B0.2 — /api/chat (Baileys) bridge to WhatsApp operational memory
# =========================================================================== #


@pytest.mark.asyncio
async def test_api_chat_group_mapped_claims_and_suppresses_legacy(enabled, monkeypatch):
    import api.chat as apichat
    captured = {}

    async def fake_bridge(**kw):
        captured.update(kw)
        return True   # claimed, no send (reply OFF) → empty response

    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational.maybe_handle_whatsapp_operational", fake_bridge)
    request = apichat.GroupChatRequest(text="ciao a tutti", sender_name="Ann", sender_id="3939", group_id=GROUP_JID)
    resp = await apichat.group_chat_endpoint(request, req=None, user=None)
    assert resp.status == "operational" and resp.response == ""     # legacy suppressed, silent
    assert captured["group_jid"] == GROUP_JID                       # full JID mapping key, not truncated


@pytest.mark.asyncio
async def test_api_chat_group_reply_enabled_returns_text(enabled, monkeypatch):
    monkeypatch.setenv("WHATSAPP_OPERATIONAL_REPLY_ENABLED", "true")
    import api.chat as apichat

    async def fake_bridge(group_jid, sender_jid, first_name, text, send_message, **kw):
        await send_message(group_jid, "OP REPLY BODY")   # bridge sends via injected sender
        return True

    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational.maybe_handle_whatsapp_operational", fake_bridge)
    request = apichat.GroupChatRequest(text="Genesi, fammi il punto", sender_name="Ann", sender_id="3939", group_id=GROUP_JID)
    resp = await apichat.group_chat_endpoint(request, req=None, user=None)
    assert resp.status == "operational" and resp.response == "OP REPLY BODY"


@pytest.mark.asyncio
async def test_api_chat_group_unmapped_falls_through(enabled, monkeypatch):
    # Unmapped group → bridge resolves no project → hook does not return → legacy.
    # We assert the hook does NOT claim (no operational early-return) by spying the
    # bridge: it must not be called for an unmapped group.
    import api.chat as apichat
    called = {"n": 0}

    async def fake_bridge(**kw):
        called["n"] += 1
        return True

    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational.maybe_handle_whatsapp_operational", fake_bridge)
    # group not in WHATSAPP_CHAT_PROJECT_MAP → resolve returns None → bridge skipped
    request = apichat.GroupChatRequest(text="ciao", sender_name="Ann", sender_id="3939", group_id="000000@g.us")
    # legacy path is heavy; assert only that the operational bridge was not invoked
    try:
        await apichat.group_chat_endpoint(request, req=None, user=None)
    except Exception:
        pass
    assert called["n"] == 0


def test_api_chat_operational_hook_wired_and_no_hardcoding():
    src = open("api/chat.py", "r", encoding="utf-8").read()
    assert "maybe_handle_whatsapp_operational(" in src
    assert "group_jid=request.group_id" in src          # full JID, not truncated log value
    assert "is_whatsapp_operational_enabled" in src       # flag-guarded
    assert "group_hash=group_int" in src                  # privacy: hash, not full jid in check log
    low = src.lower()
    for token in ["120363428502905378", "genesi canary", "tab cefla", "cantiere", "corridoio"]:
        assert token not in low, f"hardcoded token in api/chat.py: {token}"
