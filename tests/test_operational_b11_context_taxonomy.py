"""B11 — Context taxonomy / spatial grouping.

  * extractor: scala, level ranges (L3-7), technical rooms (CED, centrale X),
    canonical aliases in tags (Torre 2→T2, piano 5→L5, SC3→SCALA 3, L3-7 expanded)
  * normalize_context_token / expand_level_range
  * query-side spatial filter: "problemi scala 2", "cosa manca in torre 2",
    "punto del piano 5", "aperto in CED"
  * never invents context: item without context excluded from scoped queries;
    text without spatial refs yields empty context
"""
from __future__ import annotations

from core.operational_memory.context_extractor import (
    expand_level_range,
    extract_context,
    normalize_context_token,
)
from core.operational_memory.models import (
    Issue,
    LifecycleState,
    OperationalState,
    OperationalTask,
    QueryAnswerItem,
)
from core.operational_memory.query_engine import (
    answer_query,
    classify_query_intent,
    extract_query_context,
    filter_items_by_context,
    is_pure_operational_invocation,
)
from core.operational_memory.chat_presence import build_chat_reply


# ---------------------------------------------------------------------------
# Extraction — mandate examples
# ---------------------------------------------------------------------------

def test_extract_fc_scala2_t2_range():
    c = extract_context("FC SCALA 2 T2 DA L3-7")
    assert c.context_system == "T2"
    assert c.context_location == "SCALA 2"
    assert c.context_level == "L3-7"
    for tag in ["SCALA 2", "T2", "L3", "L4", "L5", "L6", "L7"]:
        assert tag in c.context_tags, tag


def test_extract_t2_l5_ced():
    c = extract_context("T2 L5 FC CED perde")
    assert c.context_system == "T2"
    assert c.context_level == "L5"
    assert c.context_location == "CED"


def test_extract_centrale_uta():
    c = extract_context("centrale UTA")
    assert c.context_system == "UTA"
    assert c.context_location and "centrale" in c.context_location.lower()


def test_extract_no_context_not_invented():
    c = extract_context("bracci per ogni zona")
    assert c.context_area is None and c.context_system is None
    assert c.context_level is None and c.context_location is None
    assert c.context_tags == []


def test_extract_torre_alias_in_tags():
    c = extract_context("Torre 2 quadro QGBT2")
    assert c.context_location == "Torre 2"
    assert "T2" in c.context_tags  # canonical alias


def test_extract_piano_alias_in_tags():
    c = extract_context("problemi al piano 5")
    assert "L5" in c.context_tags


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------

def test_normalize_tokens():
    assert normalize_context_token("Torre 2") == "T2"
    assert normalize_context_token("piano 5") == "L5"
    assert normalize_context_token("livello 4") == "L4"
    assert normalize_context_token("scala 2") == "SCALA 2"
    assert normalize_context_token("SC3") == "SCALA 3"
    assert normalize_context_token("L3-7") == "L3-L7"
    assert normalize_context_token("CED") == "CED"


def test_expand_level_range():
    assert expand_level_range("L3-L7") == ["L3", "L4", "L5", "L6", "L7"]
    assert expand_level_range("L3-7") == ["L3", "L4", "L5", "L6", "L7"]
    assert expand_level_range("L5") == ["L5"]
    assert expand_level_range("") == []


# ---------------------------------------------------------------------------
# Query context detection
# ---------------------------------------------------------------------------

def test_query_context_tokens():
    assert extract_query_context("cosa manca in torre 2?") == ["T2"]
    assert extract_query_context("problemi scala 2?") == ["SCALA 2"]
    assert extract_query_context("fammi il punto del piano 5") == ["L5"]
    assert extract_query_context("cosa resta aperto in CED?") == ["CED"]
    assert extract_query_context("problemi aperti") == []
    assert extract_query_context("cosa manca?") == []


def test_query_context_bare_codes_need_preposition():
    assert extract_query_context("cosa manca in T2?") == ["T2"]
    assert extract_query_context("aperti su L5") == ["L5"]
    # bare code without preposition → not a context filter
    assert extract_query_context("T2 non parte") == []


# ---------------------------------------------------------------------------
# Filtering — never invents, range matching
# ---------------------------------------------------------------------------

def _qitem(text, **ctx):
    return QueryAnswerItem(text=text, status="open", **ctx)


def test_filter_matches_normalized_fields_and_tags():
    items = [
        _qitem("a", context_system="T2"),
        _qitem("b", context_location="Torre 2"),
        _qitem("c", context_tags=["T2"]),
        _qitem("d qualcosa d'altro senza riferimenti"),
    ]
    out = filter_items_by_context(items, ["T2"])
    assert [it.text for it in out][:3] == ["a", "b", "c"]
    assert all("d " not in it.text for it in out)


def test_filter_level_range_matches_contained_level():
    items = [_qitem("range", context_level="L3-7")]
    assert filter_items_by_context(items, ["L5"]) == items
    assert filter_items_by_context(items, ["L9"]) == []


def test_filter_text_fallback_for_legacy_items():
    """Items stored before the extractor knew a token still match via their text."""
    items = [_qitem("Intercetti aperti in FC SCALA 2 T2 DA L3-7")]
    assert filter_items_by_context(items, ["SCALA 2"]) == items
    assert filter_items_by_context(items, ["L6"]) == items


def test_filter_no_context_item_excluded_not_invented():
    items = [_qitem("verificare documentazione")]
    assert filter_items_by_context(items, ["T2"]) == []


# ---------------------------------------------------------------------------
# End-to-end: spatial queries over a state
# ---------------------------------------------------------------------------

def _issue(text, status="open", eid="e1"):
    return Issue(text=text, source="wa", source_event_id=eid,
                 source_timestamp="2026-07-01T08:00:00+00:00", confidence="high",
                 lifecycle=LifecycleState(category="issue", current_status=status,
                                          confidence="high"))


def _task(text, eid="t1"):
    return OperationalTask(text=text, source="wa", source_event_id=eid,
                           source_timestamp="2026-07-01T08:00:00+00:00",
                           lifecycle=LifecycleState(category="task",
                                                    current_status="open",
                                                    confidence="high"))


def _state():
    s = OperationalState(project_id="b11-test")
    s.issues.extend([
        _issue("FC SCALA 2 T2 DA L3-7 intercetti aperti", eid="e1"),
        _issue("T2 L5 FC CED perde", eid="e2"),
        _issue("Pompa P9 ferma", eid="e3"),
    ])
    s.tasks.extend([
        _task("Verificare portate T2 L6", eid="t1"),
        _task("verificare documentazione", eid="t2"),
    ])
    return s


def test_query_problemi_scala2():
    res = answer_query(_state(), "problemi scala 2?")
    assert res.intent == "open_issues"
    texts = [it.text for it in res.items]
    assert any("SCALA 2" in t for t in texts)
    assert all("Pompa P9" not in t for t in texts)


def test_query_cosa_manca_torre2():
    res = answer_query(_state(), "cosa manca in torre 2?")
    assert res.intent == "open_tasks"
    texts = [it.text for it in res.items]
    assert "Verificare portate T2 L6" in texts
    assert "verificare documentazione" not in texts  # no context → excluded


def test_query_punto_piano5_briefing_scoped():
    res = answer_query(_state(), "fammi il punto del piano 5")
    assert res.intent == "remaining_open"
    texts = [it.text for it in res.items]
    assert any("L3-7" in t for t in texts)   # range contains L5
    assert any("L5" in t for t in texts)
    assert all("Pompa P9" not in t for t in texts)


def test_query_aperto_in_ced():
    res = answer_query(_state(), "cosa resta aperto in CED?")
    assert res.intent == "remaining_open"
    assert [it.text for it in res.items] == ["T2 L5 FC CED perde"]


def test_query_no_match_honest_zero():
    res = answer_query(_state(), "problemi in torre 9?")
    assert res.count == 0
    assert "T9" in res.summary


def test_unscoped_queries_unchanged():
    res = answer_query(_state(), "problemi aperti")
    assert res.count == 3  # all issues, no filter


def test_scoped_reply_renders():
    r = build_chat_reply(_state(), "problemi scala 2?")
    assert "SCALA 2" in r.reply_markdown or "Scala 2" in r.reply_markdown.title()


# ---------------------------------------------------------------------------
# Non-regression: routing + purity untouched
# ---------------------------------------------------------------------------

def test_intents_unchanged_by_context():
    for q, exp in [
        ("cosa manca in torre 2?", "open_tasks"),
        ("problemi scala 2?", "open_issues"),
        ("fammi il punto della situazione", "briefing"),
        ("dammi solo le priorità", "attention"),
        ("secondo te possiamo chiudere?", "decision_guard"),
        ("report operativo", "cmd_report"),
    ]:
        assert classify_query_intent(q) == exp, q


def test_scoped_queries_are_pure():
    for q in ["cosa manca in torre 2?", "problemi scala 2?", "cosa resta aperto in CED?"]:
        assert is_pure_operational_invocation(q) is True, q
