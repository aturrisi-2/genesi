"""T-A2 — WhatsApp/Telegram adapters forward voice/audio to the Operational core.

The adapters only recognise the media kind, save/forward a safe path + metadata;
the core (T-A1) is the single source of transcription. Validates:
  * WhatsApp voice/audio mapped → audio attachment reaches the core (transcribed);
  * WhatsApp decrypt/download fail (missing file) → no crash, no send;
  * Telegram voice/audio mapped → audio attachment reaches the core;
  * Telegram _download_operational_media handles voice + audio (+ failure);
  * unmapped chat / normal text / pure invocation / reply OFF unchanged.

analyze_audio is mocked (no real STT call). No env/restart/live, reply OFF.
"""

from __future__ import annotations

import asyncio
import json

import pytest


SECRET = "portare il generatore al piano -1 entro domani mattina"


def _spies():
    sent, ingested = [], []

    async def send(*a, **k):
        sent.append((a, k))

    async def updater(message):
        ingested.append(message)

    return sent, ingested, send, updater


def _mock_analyze_audio(monkeypatch, transcription=SECRET, kind="speech", language="it"):
    async def fake(audio_bytes, content_type="audio/ogg"):
        return {"kind": kind, "language": language, "transcription": transcription,
                "translation_it": None, "description": "desc"}
    monkeypatch.setattr("core.audio_analysis_service.analyze_audio", fake)


# =========================================================================== #
# WhatsApp bridge — voice/audio → core
# =========================================================================== #


GROUP_JID = "120363000000000000@g.us"
PROJECT = "wa-audio-proj"


@pytest.fixture
def wa_enabled(monkeypatch):
    monkeypatch.setenv("OPERATIONAL_MEMORY_WHATSAPP_ENABLED", "true")
    monkeypatch.setenv("WHATSAPP_CHAT_PROJECT_MAP", json.dumps({GROUP_JID: PROJECT}))
    monkeypatch.delenv("WHATSAPP_OPERATIONAL_REPLY_ENABLED", raising=False)  # reply OFF
    return monkeypatch


@pytest.mark.asyncio
async def test_whatsapp_voice_mapped_audio_attachment_reaches_core(wa_enabled, monkeypatch, tmp_path):
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    _mock_analyze_audio(monkeypatch)
    f = tmp_path / "v.ogg"
    f.write_bytes(b"OggS-bytes")
    sent, ingested, send, updater = _spies()

    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, "3931112222", "Ann", "", send,
        message_id="wm1", media_type="voice", media_id="v.ogg",
        media_dir=str(tmp_path), mime_type="audio/ogg", updater=updater)
    await asyncio.sleep(0)
    assert handled is True
    assert sent == []                       # reply OFF → no send
    assert len(ingested) == 1
    att = ingested[0].attachments[0]
    assert att.type == "voice"
    assert att.extracted_text == SECRET     # transcription rode through the core
    assert att.metadata["extraction_status"] == "transcribed"


@pytest.mark.asyncio
async def test_whatsapp_audio_download_fail_no_crash(wa_enabled, monkeypatch, tmp_path):
    # media_id points to a non-existent file (decrypt/download failed upstream).
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, "3931112222", "Ann", "", send,
        message_id="wm2", media_type="voice", media_id="gone.ogg",
        media_dir=str(tmp_path), mime_type="audio/ogg", updater=updater)
    await asyncio.sleep(0)
    assert handled is True                  # claimed, no crash
    assert sent == []
    att = ingested[0].attachments[0]
    assert att.metadata["extraction_status"] == "file_missing"   # audio event w/ technical status


@pytest.mark.asyncio
async def test_whatsapp_normal_text_unchanged(wa_enabled, monkeypatch):
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        GROUP_JID, "3931112222", "Ann", "consegna prevista venerdì", send,
        message_id="wm3", updater=updater)
    await asyncio.sleep(0)
    assert handled is True
    assert sent == []
    assert ingested[0].attachments == []     # text-only, unchanged


@pytest.mark.asyncio
async def test_whatsapp_unmapped_chat_unchanged(wa_enabled, monkeypatch, tmp_path):
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_whatsapp_operational(
        "999999@g.us", "3931112222", "Ann", "", send,
        message_id="wm4", media_type="voice", media_id="v.ogg",
        media_dir=str(tmp_path), updater=updater)
    await asyncio.sleep(0)
    assert handled is False                  # unmapped → legacy, no operational side effects
    assert ingested == []


# =========================================================================== #
# Telegram adapter — _download_operational_media voice/audio
# =========================================================================== #


@pytest.mark.asyncio
async def test_telegram_download_media_voice(monkeypatch, tmp_path):
    import core.telegram_bot as tb
    monkeypatch.setattr(tb, "_TG_OPERATIONAL_MEDIA_DIR", str(tmp_path))

    async def fake_download(file_id):
        return b"OggS-voice"

    monkeypatch.setattr(tb, "download_file", fake_download)
    mtype, path, fname, mime = await tb._download_operational_media(
        {"voice": {"file_id": "VOICEID", "mime_type": "audio/ogg"}})
    assert mtype == "voice"
    assert path.endswith("VOICEID") and mime == "audio/ogg"
    import os
    assert os.path.exists(path)


@pytest.mark.asyncio
async def test_telegram_download_media_audio(monkeypatch, tmp_path):
    import core.telegram_bot as tb
    monkeypatch.setattr(tb, "_TG_OPERATIONAL_MEDIA_DIR", str(tmp_path))

    async def fake_download(file_id):
        return b"mp3-bytes"

    monkeypatch.setattr(tb, "download_file", fake_download)
    mtype, path, fname, mime = await tb._download_operational_media(
        {"audio": {"file_id": "AUDIOID", "mime_type": "audio/mpeg", "file_name": "rec.mp3"}})
    assert mtype == "audio" and mime == "audio/mpeg" and fname == "rec.mp3"


@pytest.mark.asyncio
async def test_telegram_download_media_voice_fail_no_path(monkeypatch, tmp_path):
    import core.telegram_bot as tb
    monkeypatch.setattr(tb, "_TG_OPERATIONAL_MEDIA_DIR", str(tmp_path))

    async def fake_download(file_id):
        return None

    monkeypatch.setattr(tb, "download_file", fake_download)
    mtype, path, fname, mime = await tb._download_operational_media(
        {"voice": {"file_id": "X", "mime_type": "audio/ogg"}})
    assert mtype == "voice" and path == ""   # download fail → no path, bridge text-only


# =========================================================================== #
# Telegram bridge — voice/audio path → core
# =========================================================================== #


TG_CHAT = "-5001234567"
TG_PROJECT = "tg-audio-proj"


@pytest.fixture
def tg_enabled(monkeypatch):
    monkeypatch.setenv("OPERATIONAL_MEMORY_TELEGRAM_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_CHAT_PROJECT_MAP", json.dumps({TG_CHAT: TG_PROJECT}))
    monkeypatch.setenv("TELEGRAM_OPERATIONAL_REPLY_ENABLED", "false")  # reply OFF
    return monkeypatch


@pytest.mark.asyncio
async def test_telegram_voice_mapped_audio_attachment_reaches_core(tg_enabled, monkeypatch, tmp_path):
    from core.operational_memory.telegram_operational import maybe_handle_operational
    _mock_analyze_audio(monkeypatch)
    f = tmp_path / "tgvoice.ogg"
    f.write_bytes(b"OggS-bytes")
    sent, ingested, send, updater = _spies()

    handled = await maybe_handle_operational(
        chat_id=TG_CHAT, from_id=42, first_name="Bob", text="", send_message=send,
        message_id=11, media_type="voice", media_path=str(f), media_mime="audio/ogg",
        updater=updater)
    await asyncio.sleep(0)
    assert handled is False                  # reply OFF → silent ingest, pipeline proceeds
    assert sent == []
    att = ingested[0].attachments[0]
    assert att.type in ("voice", "audio")
    assert att.extracted_text == SECRET


@pytest.mark.asyncio
async def test_telegram_pure_invocation_not_ingested(tg_enabled, monkeypatch):
    monkeypatch.setenv("TELEGRAM_OPERATIONAL_REPLY_ENABLED", "true")
    import core.operational_memory.telegram_operational as mod

    flushed = []

    async def fake_flush(project_id, rebuild=True):
        flushed.append(project_id)

    from core.operational_memory.models import ChatReply

    async def fake_reply(project_id, query, report_base_url="", invoked_by="", save=True):
        return ChatReply(project_id=project_id, intent="remaining_open", reply_markdown="X")

    monkeypatch.setattr(mod, "flush_project", fake_flush)
    monkeypatch.setattr(mod, "build_operational_reply", fake_reply)
    sent, ingested, send, updater = _spies()
    await mod.maybe_handle_operational(
        chat_id=TG_CHAT, from_id=42, first_name="Bob",
        text="Genesi, cosa resta aperto?", send_message=send, message_id=12, updater=updater)
    assert flushed == [TG_PROJECT]
    assert ingested == []                    # pure query not stored
