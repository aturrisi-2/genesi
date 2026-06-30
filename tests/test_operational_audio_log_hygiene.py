"""Log hygiene: OPERATIONAL_RESOLUTION_CANDIDATE must not leak audio transcription text.

Synthetic data only. Verifies that for an audio-transcribed event the log carries
safe metadata (no text_preview), while a normal text event keeps text_preview.
"""
import core.operational_memory.lifecycle_engine as le
from core.operational_memory.models import OperationalEvent, OperationalState

RES_TEXT = "Risolto problema valvola DN32"


def _event(eid, **kw):
    base = dict(event_id=eid, project_id="synthetic-001", timestamp="2026-06-30T10:00:00+00:00")
    base.update(kw)
    return OperationalEvent(**base)


def _capture(monkeypatch):
    calls = []
    monkeypatch.setattr(le, "log", lambda name, **kw: calls.append((name, kw)))
    return calls


def _candidates(calls):
    return [kw for name, kw in calls if name == "OPERATIONAL_RESOLUTION_CANDIDATE"]


def test_audio_event_logs_no_text_preview(monkeypatch):
    calls = _capture(monkeypatch)
    ev = _event("AUD1", type="document", attachment_type="audio",
                extraction_status="transcribed", extracted_text=RES_TEXT,
                attachment_metadata={"mime_type": "audio/ogg; codecs=opus"})
    le.apply_resolution_links(OperationalState(project_id="synthetic-001"), [ev])
    cands = _candidates(calls)
    assert len(cands) == 1
    c = cands[0]
    assert "text_preview" not in c
    assert c.get("media_type") == "audio"
    assert c.get("transcribed") is True
    assert c.get("text_len") == len(RES_TEXT)
    # no field carries the raw transcription text
    assert all(RES_TEXT not in str(v) for v in c.values())


def test_text_event_keeps_text_preview(monkeypatch):
    calls = _capture(monkeypatch)
    ev = _event("TXT1", type="text", content=RES_TEXT)
    le.apply_resolution_links(OperationalState(project_id="synthetic-001"), [ev])
    cands = _candidates(calls)
    assert len(cands) == 1
    c = cands[0]
    assert "text_preview" in c
    assert "media_type" not in c


def test_helper_detects_audio_only():
    assert le._is_transcribed_audio_event(_event("a", extraction_status="transcribed")) is True
    assert le._is_transcribed_audio_event(_event("b", attachment_type="audio")) is True
    assert le._is_transcribed_audio_event(
        _event("c", attachment_metadata={"mime_type": "audio/ogg"})) is True
    # non-audio media must NOT be masked
    assert le._is_transcribed_audio_event(_event("d", extraction_status="text_extracted")) is False
    assert le._is_transcribed_audio_event(_event("e", extraction_status="video_analyzed")) is False
    assert le._is_transcribed_audio_event(_event("f", type="text")) is False
