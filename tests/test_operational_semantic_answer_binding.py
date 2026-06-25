"""Semantic answer binding: a short availability/location reply is linked to the
single recent open issue/media (information/mitigation), without resolving it.
Deterministic, fail-closed, generic (no V27/DN32 hardcode)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import core.operational_memory.event_store as es
from core.operational_memory.context_binding import infer_answer_binding, _looks_like_answer
from core.operational_memory.models import OperationalEvent

PROJECT = "answer-bind-proj"


def _ts(min_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=min_ago)).isoformat()


def _ev(eid, content="", min_ago=2.0, etype="text", extracted_text="", attachment_type=""):
    return OperationalEvent(event_id=eid, project_id=PROJECT, source="whatsapp", type=etype,
                            content=content, extracted_text=(extracted_text or None),
                            attachment_type=(attachment_type or None), timestamp=_ts(min_ago))


def _reply(text, min_ago=0.0):
    return OperationalEvent(event_id="REPLY", project_id=PROJECT, source="whatsapp", type="text",
                            content=text, timestamp=_ts(min_ago))


@pytest.fixture
def store(monkeypatch, tmp_path):
    monkeypatch.setattr(es, "_BASE_DIR", tmp_path)
    monkeypatch.delenv("OPERATIONAL_ANSWER_BINDING_ENABLED", raising=False)  # default ON
    return monkeypatch


async def _seed(events):
    await es.save_events(PROJECT, events)


# --------------------------------------------------------------------------- #
# answer-phrase detection
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("t,expected", [
    ("È giù in ufficio, nello scaffale centrale", True),
    ("ce l'ho io", True),
    ("è in magazzino", True),
    ("ok", False),
    ("grazie", False),
    ("Analizza questa immagine.", False),
    ("Manca manopola valvola di bilanciamento DN 32", False),
])
def test_looks_like_answer(t, expected):
    assert _looks_like_answer(t) is expected


# --------------------------------------------------------------------------- #
# binding
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_answer_bound_to_recent_issue(store):
    await _seed([_ev("ISSUE1", content="Manca manopola valvola di bilanciamento DN 32", min_ago=2)])
    reply = _reply("È giù in ufficio, nello scaffale centrale", min_ago=0)
    out = await infer_answer_binding(reply, PROJECT)
    assert out.parent_event_id == "ISSUE1"
    assert out.reply_relation == "answer_binding"
    assert "manopola" in (out.parent_context or "").lower()   # linked context, issue not resolved


@pytest.mark.asyncio
async def test_answer_bound_to_media_issue(store):
    await _seed([_ev("IMG1", content="", extracted_text="V27 LO FC FREDDO manca manopola DN32",
                     etype="image", attachment_type="image", min_ago=1)])
    out = await infer_answer_binding(_reply("ce l'ho io in officina", 0), PROJECT)
    assert out.parent_event_id == "IMG1"


@pytest.mark.asyncio
async def test_reply_outside_window_not_bound(store):
    await _seed([_ev("ISSUE1", content="manca guarnizione", min_ago=30)])   # > 10 min
    out = await infer_answer_binding(_reply("è in magazzino", 0), PROJECT)
    assert out.parent_event_id is None


@pytest.mark.asyncio
async def test_two_recent_issues_ambiguous(store):
    await _seed([
        _ev("ISSUE1", content="manca manopola DN32", min_ago=3),
        _ev("ISSUE2", content="rotto sensore di pressione", min_ago=4),
    ])
    out = await infer_answer_binding(_reply("è giù in ufficio", 0), PROJECT)
    assert out.parent_event_id is None        # ambiguous → no bind


@pytest.mark.asyncio
async def test_generic_ack_not_bound(store):
    await _seed([_ev("ISSUE1", content="manca manopola DN32", min_ago=2)])
    out = await infer_answer_binding(_reply("ok", 0), PROJECT)
    assert out.parent_event_id is None


@pytest.mark.asyncio
async def test_no_open_issue_not_bound(store):
    await _seed([_ev("INFO1", content="riunione lunedì alle 9", min_ago=2)])  # no problem marker
    out = await infer_answer_binding(_reply("è in magazzino", 0), PROJECT)
    assert out.parent_event_id is None


@pytest.mark.asyncio
async def test_disabled_flag_no_bind(monkeypatch, tmp_path):
    monkeypatch.setattr(es, "_BASE_DIR", tmp_path)
    monkeypatch.setenv("OPERATIONAL_ANSWER_BINDING_ENABLED", "false")
    await es.save_events(PROJECT, [_ev("ISSUE1", content="manca manopola DN32", min_ago=2)])
    out = await infer_answer_binding(_reply("è giù in ufficio", 0), PROJECT)
    assert out.parent_event_id is None
