"""T-A4.1 — Contextual parent inference (gated OFF), no quote/reply needed.

Secondary strategy: only when there is no explicit reply_to_id AND the flag
OPERATIONAL_CONTEXT_INFERENCE_ENABLED is on. The strong explicit PARENT_BOUND
path is never altered. Conservative: high score + margin + >=2 independent
signals (>=1 linking). Validates the listed scenarios. No env/live/send.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import core.operational_memory.event_store as es
from core.operational_memory.context_binding import infer_parent_context, resolve_parent_context
from core.operational_memory.models import OperationalEvent


PROJECT = "ta41-infer-proj"


def _ts(minutes_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)).isoformat()


def _ev(event_id, sender, content="", minutes_ago=5.0, etype="text", extracted_text=""):
    return OperationalEvent(
        event_id=event_id, project_id=PROJECT, source="whatsapp", sender=sender,
        type=etype, content=content, extracted_text=(extracted_text or None),
        timestamp=_ts(minutes_ago))


def _child(content="", extracted_text="", etype="text", minutes_ago=0.0):
    return OperationalEvent(
        event_id="CHILD", project_id=PROJECT, source="whatsapp", sender="Anna",
        type=etype, content=content, extracted_text=(extracted_text or None),
        timestamp=_ts(minutes_ago))


@pytest.fixture
def store_on(monkeypatch, tmp_path):
    monkeypatch.setattr(es, "_BASE_DIR", tmp_path)
    monkeypatch.setenv("OPERATIONAL_CONTEXT_INFERENCE_ENABLED", "true")
    return monkeypatch


async def _seed(events):
    await es.save_events(PROJECT, events)


# --------------------------------------------------------------------------- #
# Explicit path untouched + flag OFF
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_explicit_reply_untouched_by_inference(store_on):
    # Event already has explicit parent → inference is a no-op (returns as-is).
    child = _child(content="ok domattina")
    child.parent_event_id = "SOME_EXPLICIT"
    child.reply_relation = "reply_to"
    out = await infer_parent_context(child, PROJECT)
    assert out.parent_event_id == "SOME_EXPLICIT"
    assert out.reply_relation == "reply_to"
    assert out.parent_binding_meta == {}


@pytest.mark.asyncio
async def test_flag_off_no_inference(monkeypatch, tmp_path):
    monkeypatch.setattr(es, "_BASE_DIR", tmp_path)
    monkeypatch.delenv("OPERATIONAL_CONTEXT_INFERENCE_ENABLED", raising=False)  # OFF
    await es.save_events(PROJECT, [_ev("P1", "Marco", "ricontrolla il quadro EWC-10", 5)])
    child = _child(content="Marco allora lo facciamo domattina")
    out = await infer_parent_context(child, PROJECT)
    assert out.parent_event_id is None          # identical to today
    assert out.reply_relation == ""


# --------------------------------------------------------------------------- #
# Inference fires (author / tech / media)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_text_citing_author_inferred(store_on):
    await _seed([_ev("P1", "Marco", "ricontrolla il quadro EWC-10 al piano -1", 5)])
    child = _child(content="Marco allora lo facciamo domattina")
    out = await infer_parent_context(child, PROJECT)
    assert out.parent_event_id == "P1"
    assert out.reply_relation == "inferred_context"
    assert "author_mention" in out.parent_binding_meta["signals"]


@pytest.mark.asyncio
async def test_voice_citing_author_inferred(store_on):
    await _seed([_ev("P1", "Marco", "preparare il quadro EWC-12 in cantiere", 6)])
    child = _child(extracted_text="Marco lo facciamo come prima cosa domattina", etype="document")
    out = await infer_parent_context(child, PROJECT)
    assert out.parent_event_id == "P1"
    assert out.reply_relation == "inferred_context"


@pytest.mark.asyncio
async def test_voice_refers_to_recent_photo_inferred(store_on):
    # Photo with caption/OCR containing a tech code; voice shares the code → tech_overlap.
    await _seed([_ev("IMG1", "Luca", "quadro EWC-10 V10 cavedio L03", 4, etype="image")])
    child = _child(extracted_text="colleghiamo EWC-10 V10 domattina", etype="document")
    out = await infer_parent_context(child, PROJECT)
    assert out.parent_event_id == "IMG1"
    assert "tech_overlap" in out.parent_binding_meta["signals"]


# --------------------------------------------------------------------------- #
# No binding cases
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_two_same_author_candidates_ambiguous(store_on):
    await _seed([
        _ev("P1", "Marco", "ricontrolla il quadro al piano -1", 5),
        _ev("P2", "Marco", "verificare la fornitura materiale", 8),
    ])
    child = _child(content="Marco allora lo facciamo domattina")
    out = await infer_parent_context(child, PROJECT)
    assert out.parent_event_id is None          # ambiguous → no binding


@pytest.mark.asyncio
async def test_generic_message_no_binding(store_on):
    await _seed([_ev("P1", "Marco", "ricontrolla il quadro EWC-10", 5)])
    child = _child(content="ok grazie")          # no author/tech/lexical link
    out = await infer_parent_context(child, PROJECT)
    assert out.parent_event_id is None


@pytest.mark.asyncio
async def test_parent_too_old_no_binding(store_on):
    await _seed([_ev("P1", "Marco", "ricontrolla il quadro EWC-10", 90)])  # outside 45m window
    child = _child(content="Marco allora lo facciamo domattina")
    out = await infer_parent_context(child, PROJECT)
    assert out.parent_event_id is None


@pytest.mark.asyncio
async def test_closed_item_penalized_no_binding(store_on):
    # Tech overlap present but the candidate is resolved → closed_penalty drops it.
    await _seed([_ev("P1", "Marco", "quadro EWC-10 V10 risolto", 5)])
    child = _child(extracted_text="EWC-10 V10 domattina", etype="document")
    out = await infer_parent_context(child, PROJECT)
    assert out.parent_event_id is None


@pytest.mark.asyncio
async def test_no_candidates_not_found(store_on):
    await _seed([])
    child = _child(content="Marco allora lo facciamo domattina")
    out = await infer_parent_context(child, PROJECT)
    assert out.parent_event_id is None


# --------------------------------------------------------------------------- #
# Explicit binding still works (regression of T-A3 alongside the new field)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_explicit_resolve_still_binds(store_on):
    await _seed([_ev("PIMG", "Luca", "EWC-10 V10 cavedio L03", 5, etype="image")])
    child = _child(extracted_text="lo facciamo domattina", etype="document")
    child.parent_event_id = "PIMG"
    child.reply_relation = "reply_to"
    await resolve_parent_context(child, PROJECT)
    assert "EWC-10" in child.parent_context
    assert child.reply_relation == "reply_to"     # explicit value unchanged
