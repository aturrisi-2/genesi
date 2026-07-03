"""B11.1 — report grouped by spatial context.

'## Criticità per contesto' section in the briefing markdown: active issues
grouped by primary context (stored fields, gaps filled from text), one group
per item, reopened groups first, max 5 groups + overflow line, undetermined
context last and never invented. Chat replies and routing untouched.
"""
from __future__ import annotations

from core.operational_memory.context_extractor import normalize_context_token
from core.operational_memory.models import (
    Issue,
    LifecycleState,
    OperationalState,
    QueryAnswerItem,
)
from core.operational_memory.query_engine import (
    _primary_context_parts,
    build_briefing,
    group_items_by_context,
)
from core.operational_memory.chat_presence import build_chat_reply


def _issue(text, status="open", eid="e1", **ctx):
    return Issue(text=text, source="wa", source_event_id=eid,
                 source_timestamp="2026-07-01T08:00:00+00:00", confidence="high",
                 lifecycle=LifecycleState(category="issue", current_status=status,
                                          confidence="high"), **ctx)


def _state(issues):
    s = OperationalState(project_id="b111-test")
    s.issues.extend(issues)
    return s


# ---------------------------------------------------------------------------
# Primary context selection
# ---------------------------------------------------------------------------

def test_primary_from_stored_fields():
    it = QueryAnswerItem(text="x", status="open",
                         context_system="T2", context_level="L5",
                         context_location="CED")
    assert _primary_context_parts(it) == ["CED", "T2", "L5"]


def test_primary_fills_gaps_from_text():
    # stored truncated level (legacy) — fresh scan completes range + scala
    it = QueryAnswerItem(text="Intercetti aperti in FC SCALA 2 T2 DA L3-7",
                         status="open", context_system="T2", context_level="L3")
    assert _primary_context_parts(it) == ["SCALA 2", "T2", "L3-L7"]


def test_primary_no_context_empty_not_invented():
    it = QueryAnswerItem(text="verificare documentazione", status="open")
    assert _primary_context_parts(it) == []


def test_leading_zero_levels_merge():
    assert normalize_context_token("L01") == "L1"
    assert normalize_context_token("L1") == "L1"
    assert normalize_context_token("L00") == "L0"


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------

def test_group_each_item_once_and_undetermined_last():
    items = [
        QueryAnswerItem(text="T2 L5 FC CED perde", status="open"),
        QueryAnswerItem(text="senza alcun riferimento", status="open"),
    ]
    groups, overflow = group_items_by_context(items)
    headers = [h for h, _ in groups]
    assert headers[-1] == "Contesto non determinato"
    total = sum(len(g) for _, g in groups) + len(overflow)
    assert total == 2  # one bucket each, no duplication


def test_group_reopened_first_and_max5_overflow():
    items = [QueryAnswerItem(text=f"guasto in T{i} L1", status="open")
             for i in range(1, 8)]  # 7 distinct contexts
    items.append(QueryAnswerItem(text="FC SCALA 2 T9 rotto", status="reopened"))
    groups, overflow = group_items_by_context(items)
    assert len(groups) == 5
    # reopened group first
    assert any(it.status == "reopened" for it in groups[0][1])
    assert overflow  # remaining contexts collapsed


# ---------------------------------------------------------------------------
# Report markdown
# ---------------------------------------------------------------------------

def _rich_state():
    return _state([
        _issue("Intercetti aperti in FC SCALA 2 T2 DA L3-7", status="reopened", eid="e1"),
        _issue("T2 L5 FC CED perde", eid="e2"),
        _issue("problema senza riferimenti spaziali", eid="e3"),
    ])


def test_report_contains_context_section():
    md = build_briefing(_rich_state()).markdown
    assert "## Criticità per contesto" in md
    assert "### SCALA 2 / T2 / L3-L7" in md
    assert "### CED / T2 / L5" in md
    assert "### Contesto non determinato" in md
    assert "problema senza riferimenti spaziali" in md


def test_report_ced_item_under_ced_header():
    md = build_briefing(_rich_state()).markdown
    ced_pos = md.find("### CED / T2 / L5")
    next_h = md.find("###", ced_pos + 3)
    section = md[ced_pos:next_h if next_h > ced_pos else None]
    assert "T2 L5 FC CED perde" in section


def test_report_item_appears_once_in_context_section():
    md = build_briefing(_rich_state()).markdown
    start = md.find("## Criticità per contesto")
    end = md.find("## Dettaglio")
    section = md[start:end]
    assert section.count("T2 L5 FC CED perde") == 1


def test_report_no_issues_no_section():
    md = build_briefing(OperationalState(project_id="empty")).markdown
    assert "## Criticità per contesto" not in md


# ---------------------------------------------------------------------------
# Chat replies untouched
# ---------------------------------------------------------------------------

def test_open_issues_reply_unchanged():
    r = build_chat_reply(_rich_state(), "problemi aperti")
    assert r.reply_markdown.startswith("Problemi aperti:")
    assert "## Criticità per contesto" not in r.reply_markdown


def test_briefing_card_unchanged():
    r = build_chat_reply(_rich_state(), "fammi il punto")
    assert "📌 Quadro operativo" in r.reply_markdown
    assert "## Criticità per contesto" not in r.reply_markdown


def test_spatial_queries_still_green():
    from core.operational_memory.query_engine import answer_query
    res = answer_query(_rich_state(), "problemi scala 2?")
    assert [it.text for it in res.items] == ["Intercetti aperti in FC SCALA 2 T2 DA L3-7"]
    res = answer_query(_rich_state(), "cosa resta aperto in CED?")
    assert [it.text for it in res.items] == ["T2 L5 FC CED perde"]
