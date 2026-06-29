"""Tests for media transparency in the daily report.

All datasets are synthetic — no real project store is read or mutated.
Covers the regression where technically-relevant ``MEDIA_EVIDENCE`` media
(default score 30) silently disappeared from the daily report.
"""

from core.operational_memory.daily_report import (
    compute_media_transparency,
    _media_in_report,
    _media_kind,
    _media_content_state,
    _media_transparency_lines,
)
from core.operational_memory.models import OperationalEvent
from core.operational_memory.quality import is_technically_significant

TECH_TEXT = "Manca manopola valvola di bilanciamento DN32 zona T2 L01"
NOISE_TEXT = "Buongiorno a tutti, ci vediamo dopo"


def _ev(eid, **kw):
    base = dict(
        event_id=eid,
        project_id="synthetic-001",
        attachment_path=f"/cache/{eid}.bin",
        attachment_type="image",
        attachment_metadata={},
        type="image",
        domain="MEDIA_EVIDENCE",
        secondary_domains=[],
        project_impact_score=30,
        operational_relevance_score=30,
        sender="Tester",
        timestamp="2026-06-29T10:00:00+00:00",
    )
    base.update(kw)
    return OperationalEvent(**base)


def _report(media):
    visible = {e.event_id for e in media if _media_in_report(e, "OPERATIVE_ONLY")}
    return compute_media_transparency(media, visible, "OPERATIVE_ONLY")


def test_detector_sanity():
    # Guards the chosen fixtures against detector drift.
    assert is_technically_significant(TECH_TEXT) is True
    assert is_technically_significant(NOISE_TEXT) is False


def test_media_evidence_score30_with_technical_text_is_visible():
    ev = _ev("AAAA1111", extracted_text=TECH_TEXT, extraction_status="vision_described")
    assert _media_in_report(ev, "OPERATIVE_ONLY") is True
    mt = _report([ev])
    assert mt["counts"]["media_visible_in_report"] == 1
    assert mt["counts"]["media_analyzed_with_content"] == 1


def test_score30_without_content_counted_not_promoted():
    ev = _ev("BBBB2222", extracted_text=None, extraction_status="no_text_found")
    assert _media_in_report(ev, "OPERATIVE_ONLY") is False
    mt = _report([ev])
    assert mt["counts"]["media_without_content"] == 1
    assert mt["counts"]["media_visible_in_report"] == 0
    assert any(e["media_id"] == "BBBB2222" for e in mt["hidden_media_summary"])


def test_video_with_description_counted_and_visible():
    ev = _ev(
        "CCCC3333",
        type="document",
        attachment_type="video",
        extracted_text="Il video mostra una valvola DN32 che perde in zona T2",
        extraction_status="video_analyzed",
        domain="TECHNICAL_OPERATION",
        project_impact_score=58,
        operational_relevance_score=58,
    )
    assert _media_kind(ev) == "video"
    mt = _report([ev])
    assert mt["counts"]["videos_received"] == 1
    assert mt["counts"]["media_visible_in_report"] == 1


def test_unsupported_media_counted_as_unsupported():
    ev = _ev(
        "DDDD4444",
        type="document",
        attachment_type="unknown",
        extraction_status="unsupported",
        extracted_text=None,
    )
    assert _media_content_state(ev) == "unsupported"
    mt = _report([ev])
    assert mt["counts"]["media_unsupported"] == 1
    assert any(e["media_id"] == "DDDD4444" for e in mt["unsupported_media_summary"])


def test_social_logistic_noise_not_promoted_but_counted():
    ev = _ev(
        "EEEE5555",
        extracted_text=NOISE_TEXT,
        extraction_status="text_extracted",
        domain="SOCIAL",
        secondary_domains=["LOGISTICS_PERSONAL"],
        project_impact_score=10,
        operational_relevance_score=10,
    )
    assert _media_in_report(ev, "OPERATIVE_ONLY") is False
    mt = _report([ev])
    assert mt["counts"]["media_received_total"] == 1
    assert mt["counts"]["media_visible_in_report"] == 0
    # still declared, never silently dropped
    assert mt["counts"]["media_hidden_by_filter"] == 1


def test_total_greater_than_visible_and_all_accounted():
    media = [
        _ev("AAAA1111", extracted_text=TECH_TEXT, extraction_status="vision_described"),
        _ev("BBBB2222", extracted_text=None, extraction_status="no_text_found"),
        _ev("DDDD4444", type="document", attachment_type="unknown", extraction_status="unsupported"),
        _ev("EEEE5555", extracted_text=NOISE_TEXT, extraction_status="text_extracted",
            domain="SOCIAL", project_impact_score=10, operational_relevance_score=10),
    ]
    mt = _report(media)
    c = mt["counts"]
    assert c["media_received_total"] == 4
    assert c["media_received_total"] > c["media_visible_in_report"]
    # every media falls into exactly one outcome bucket
    accounted = (
        c["media_visible_in_report"]
        + c["media_hidden_by_filter"]
        + c["media_without_content"]
        + c["media_unsupported"]
    )
    # without_content / unsupported media are not also counted as hidden_by_filter
    assert accounted == c["media_received_total"]


def test_markdown_signals_hidden_media():
    media = [
        _ev("AAAA1111", extracted_text=TECH_TEXT, extraction_status="vision_described"),
        _ev("EEEE5555", extracted_text=NOISE_TEXT, extraction_status="text_extracted",
            domain="SOCIAL", project_impact_score=10, operational_relevance_score=10),
    ]
    mt = _report(media)
    lines = _media_transparency_lines(mt)
    blob = "\n".join(lines)
    assert "Media ricevuti totali: 2" in blob
    assert "non promossi" in blob
    # an explicit diagnostic note must exist whenever total > visible
    assert any("Nota:" in line for line in lines)
