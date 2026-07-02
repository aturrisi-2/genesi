"""B9 — Professional response quality polish.

  * recommended_action grammar: correct singular/plural ("il problema riaperto"
    vs "i N problemi riaperti").
  * attention items priority-sorted: reopened > due > high-confidence > rest.
  * attention reply: site-manager style — numbered priorities (max 5), risk
    line, next-check pointer, no emoji.
  * team_brief: singular/plural in Situazione, [riaperto]/due markers.
  * No routing changes; report flow unchanged.
"""
from __future__ import annotations

from core.operational_memory.models import (
    Issue,
    LifecycleState,
    OperationalState,
    OperationalTask,
)
from core.operational_memory.query_engine import (
    _attention_rank,
    answer_query,
    attention_items,
    build_briefing,
    classify_query_intent,
)
from core.operational_memory.chat_presence import build_chat_reply


def _issue(text, status="open", confidence="high", eid="e1"):
    return Issue(
        text=text, source="wa", source_event_id=eid,
        source_timestamp="2026-07-01T08:00:00+00:00", confidence=confidence,
        lifecycle=LifecycleState(category="issue", current_status=status,
                                 confidence=confidence),
    )


def _task(text, due=None, eid="t1"):
    return OperationalTask(
        text=text, source="wa", source_event_id=eid,
        source_timestamp="2026-07-01T08:00:00+00:00", due=due,
        lifecycle=LifecycleState(category="task", current_status="open",
                                 confidence="high"),
    )


def _state(**kw):
    s = OperationalState(project_id="test-b9")
    for k, v in kw.items():
        getattr(s, k).extend(v)
    return s


# ---------------------------------------------------------------------------
# 1. recommended_action grammar
# ---------------------------------------------------------------------------

def test_one_reopened_singular():
    s = _state(issues=[_issue("Pompa P1 ferma", status="reopened")])
    b = build_briefing(s)
    assert b.recommended_action == "Affrontare prima il problema riaperto."
    assert "i 1 problemi" not in b.recommended_action


def test_many_reopened_plural():
    s = _state(issues=[
        _issue("Pompa P1 ferma", status="reopened", eid="e1"),
        _issue("Quadro Q2 in errore", status="reopened", eid="e2"),
    ])
    b = build_briefing(s)
    assert b.recommended_action == "Affrontare prima i 2 problemi riaperti."


def test_one_open_issue_singular():
    s = _state(issues=[_issue("FC T2 perde", confidence="low")])
    b = build_briefing(s)
    assert b.recommended_action == "Pianificare la risoluzione del problema aperto."


def test_one_task_singular():
    s = _state(tasks=[_task("verificare bracci")])
    b = build_briefing(s)
    assert b.recommended_action == "Avanzare sul task aperto."


def test_empty_state_monitor():
    b = build_briefing(OperationalState(project_id="x"))
    assert b.recommended_action == "Monitorare il prossimo aggiornamento operativo."


# ---------------------------------------------------------------------------
# 2. attention ordering: reopened > due > high-confidence issue > rest
# ---------------------------------------------------------------------------

def test_attention_sorted_reopened_first():
    s = _state(
        issues=[
            _issue("issue critico generico", eid="e1"),
            _issue("issue riaperto", status="reopened", eid="e2"),
        ],
        tasks=[_task("task con scadenza", due="2026-07-03", eid="t1")],
    )
    s.tasks[0].lifecycle.current_status = "blocked"  # flag into attention set
    items = attention_items(s)
    texts = [it.text for it in items]
    assert texts[0] == "issue riaperto"
    assert texts.index("task con scadenza") < texts.index("issue critico generico")


def test_attention_due_dates_earliest_first():
    s = _state(tasks=[
        _task("scade dopo", due="2026-07-10", eid="t1"),
        _task("scade prima", due="2026-07-03", eid="t2"),
    ])
    # tasks without attention flag are not in attention; make due tasks flagged
    # by giving them blocked status
    for t in s.tasks:
        t.lifecycle.current_status = "blocked"
    items = attention_items(s)
    texts = [it.text for it in items]
    assert texts.index("scade prima") < texts.index("scade dopo")


def test_attention_rank_deterministic():
    from core.operational_memory.models import QueryAnswerItem
    reo = QueryAnswerItem(text="a", status="reopened")
    due = QueryAnswerItem(text="b", status="open", due="2026-07-05")
    hi = QueryAnswerItem(text="c", status="open", category="issue", confidence="high")
    other = QueryAnswerItem(text="d", status="open")
    ranked = sorted([other, hi, due, reo], key=_attention_rank)
    assert [it.text for it in ranked] == ["a", "b", "c", "d"]


# ---------------------------------------------------------------------------
# 3. attention reply: capocantiere style
# ---------------------------------------------------------------------------

def test_attention_reply_structure():
    s = _state(issues=[
        _issue(f"problema {i}", status="reopened" if i == 0 else "open", eid=f"e{i}")
        for i in range(7)
    ])
    r = build_chat_reply(s, "dammi solo le priorità")
    assert r.intent == "attention"
    body = r.reply_markdown
    assert body.startswith("Priorità operative:")
    assert "1. problema 0 [riaperto]" in body
    assert "Rischio principale: problema 0 (riaperto)." in body
    assert "Prossima verifica: partire dal punto 1." in body
    assert "Altri 2 elementi in coda." in body
    # max 5 numbered
    assert "6." not in body


def test_attention_reply_no_emoji():
    s = _state(issues=[_issue("problema X")])
    r = build_chat_reply(s, "cosa richiede attenzione?")
    for emoji in ["📌", "🧭", "📄", "⚠", "✅", "•"]:
        assert emoji not in r.reply_markdown


def test_attention_reply_empty():
    r = build_chat_reply(OperationalState(project_id="x"), "dammi solo le priorità")
    assert "Nessuna priorità aperta" in r.reply_markdown


# ---------------------------------------------------------------------------
# 4. team_brief singular/plural + markers
# ---------------------------------------------------------------------------

def test_team_brief_singular_situation():
    s = _state(issues=[_issue("unico problema", status="reopened")],
               tasks=[_task("unico task")])
    r = build_chat_reply(s, "preparami un messaggio operativo")
    assert r.intent == "team_brief"
    assert "1 task aperto," in r.reply_markdown
    assert "1 problema aperto," in r.reply_markdown
    assert "0 decisioni attive." in r.reply_markdown
    assert "Prossima azione: Affrontare prima il problema riaperto." in r.reply_markdown


def test_team_brief_plural_situation():
    s = _state(issues=[_issue(f"p{i}", eid=f"e{i}") for i in range(3)],
               tasks=[_task(f"t{i}", eid=f"t{i}") for i in range(2)])
    r = build_chat_reply(s, "cosa diresti al team?")
    assert "2 task aperti," in r.reply_markdown
    assert "3 problemi aperti," in r.reply_markdown


def test_team_brief_markers():
    s = _state(issues=[_issue("guasto R", status="reopened")],
               tasks=[_task("consegna cavo", due="2026-07-05")])
    s.tasks[0].lifecycle.current_status = "blocked"  # flag into attention
    r = build_chat_reply(s, "preparami un messaggio operativo")
    assert "guasto R [riaperto]" in r.reply_markdown
    assert "(entro 5/7)" in r.reply_markdown


# ---------------------------------------------------------------------------
# 5. Non-regression: routing + report flow unchanged
# ---------------------------------------------------------------------------

def test_routing_unchanged():
    for q, exp in [
        ("dammi solo le priorità", "attention"),
        ("preparami un messaggio operativo", "team_brief"),
        ("cosa diresti al team?", "team_brief"),
        ("report", "cmd_report"),
        ("stato", "cmd_stato"),
        ("cosa manca", "open_tasks"),
        ("problemi aperti", "open_issues"),
    ]:
        assert classify_query_intent(q) == exp, q


def test_cmd_report_render_unchanged():
    s = _state(issues=[_issue("problema X")])
    r = build_chat_reply(s, "report", report_url="https://x/report/1")
    assert r.intent == "cmd_report"
    assert "https://x/report/1" in r.reply_markdown


def test_answer_query_attention_summary():
    s = _state(issues=[_issue("problema X")])
    res = answer_query(s, "cosa richiede attenzione?")
    assert res.intent == "attention"
    assert res.count == 1
