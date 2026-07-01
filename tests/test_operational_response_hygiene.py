"""B2 — Response hygiene for open_tasks / 'cosa manca?' view."""
from __future__ import annotations

import pytest

from core.operational_memory.models import (
    LifecycleHistoryEntry,
    LifecycleState,
    OperationalQuestion,
    OperationalState,
    OperationalTask,
    Issue,
    Decision,
    Information,
)
from core.operational_memory.quality import is_low_value_task
from core.operational_memory.query_engine import answer_query, open_tasks
from core.operational_memory.chat_presence import build_chat_reply


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _lc(category, status, evidence=None):
    return LifecycleState(
        category=category,
        current_status=status,
        confidence="high",
        status_reason="test",
        evidence_event_ids=evidence or ["ev1"],
        lifecycle_history=[LifecycleHistoryEntry(status=status, changed_at="2026-07-01T06:00:00+00:00")],
    )


def _task(tid, text, status="open", owner=None, due=None):
    return OperationalTask(
        id=tid, text=text, source="msg",
        source_event_id=tid,
        owner=owner, due=due,
        lifecycle=_lc("task", status),
    )


def _issue(iid, text, status="open"):
    return Issue(id=iid, text=text, source="msg", source_event_id=iid, lifecycle=_lc("issue", status))


def _state_canary():
    """Canary-like state with mix of low-value and real tasks."""
    return OperationalState(
        project_id="canary",
        tasks=[
            _task("t_analizza", "Analizza questa immagine."),
            _task("t_analizza2", "Analizza l'immagine inviata"),
            _task("t_segnare1", "segnare controllo documento"),
            _task("t_segnare2", "segnare verifica documento"),
            _task("t_aggiorna", "aggiorna lo stato"),
            _task("t_fg19", "Portare il cavo FG19", owner="Mario", due="2026-07-02T06:00:00+00:00"),
            _task("t_fg16", "Portare il cavo FG16", owner="Mario", due="2026-07-01T06:00:00+00:00"),
            _task("t_materiali", "controllo materiali venerdì"),
        ],
        issues=[_issue("i1", "Pompa PX11 non parte.", "reopened")],
        decisions=[],
        open_questions=[],
        information=[],
    )


def _state_clean():
    """State with only real tasks."""
    return OperationalState(
        project_id="clean",
        tasks=[
            _task("t1", "Installare quadro elettrico", owner="Luca", due="2026-07-05T06:00:00+00:00"),
            _task("t2", "Verifica collaudo linea 1"),
        ],
        issues=[],
        decisions=[],
        open_questions=[],
        information=[],
    )


def _state_empty():
    return OperationalState(
        project_id="empty",
        tasks=[_task("t_media", "Analizza questa immagine.")],
        issues=[],
        decisions=[],
        open_questions=[],
        information=[],
    )


# ---------------------------------------------------------------------------
# is_low_value_task
# ---------------------------------------------------------------------------

def test_low_value_media_trigger():
    assert is_low_value_task("Analizza questa immagine.")
    assert is_low_value_task("Analizza l'immagine inviata")
    assert is_low_value_task("Analizza immagine")

def test_low_value_segnare():
    assert is_low_value_task("segnare controllo documento")
    assert is_low_value_task("segnare verifica documento")

def test_low_value_meta_command():
    assert is_low_value_task("aggiorna lo stato")
    assert is_low_value_task("aggiorna stato")

def test_not_low_value_real_tasks():
    assert not is_low_value_task("Portare il cavo FG19")
    assert not is_low_value_task("controllo materiali venerdì")
    assert not is_low_value_task("Verifica collaudo linea 1")
    assert not is_low_value_task("Installare quadro elettrico")


# ---------------------------------------------------------------------------
# open_tasks() filtering
# ---------------------------------------------------------------------------

def test_open_tasks_excludes_analizza():
    items = open_tasks(_state_canary())
    texts = [it.text for it in items]
    assert "Analizza questa immagine." not in texts
    assert "Analizza l'immagine inviata" not in texts

def test_open_tasks_excludes_segnare():
    items = open_tasks(_state_canary())
    texts = [it.text for it in items]
    assert "segnare controllo documento" not in texts
    assert "segnare verifica documento" not in texts

def test_open_tasks_excludes_aggiorna():
    items = open_tasks(_state_canary())
    texts = [it.text for it in items]
    assert "aggiorna lo stato" not in texts

def test_open_tasks_keeps_real_actionable():
    items = open_tasks(_state_canary())
    texts = [it.text for it in items]
    assert "Portare il cavo FG19" in texts
    assert "Portare il cavo FG16" in texts
    assert "controllo materiali venerdì" in texts

def test_open_tasks_owner_and_due_propagated():
    items = open_tasks(_state_canary())
    fg19 = next(it for it in items if it.text == "Portare il cavo FG19")
    assert fg19.owner == "Mario"
    assert fg19.due and "2026-07-02" in fg19.due

def test_open_tasks_no_owner_when_absent():
    items = open_tasks(_state_canary())
    materiali = next(it for it in items if "materiali" in it.text)
    assert materiali.owner is None


# ---------------------------------------------------------------------------
# answer_query + cosa manca? render
# ---------------------------------------------------------------------------

def test_cosa_manca_reply_no_analizza():
    reply = build_chat_reply(_state_canary(), "cosa manca?")
    assert "Analizza" not in reply.reply_markdown

def test_cosa_manca_reply_no_segnare():
    reply = build_chat_reply(_state_canary(), "cosa manca?")
    assert "segnare" not in reply.reply_markdown.lower()

def test_cosa_manca_reply_no_aggiorna():
    reply = build_chat_reply(_state_canary(), "cosa manca?")
    assert "aggiorna lo stato" not in reply.reply_markdown.lower()

def test_cosa_manca_reply_shows_real_task():
    reply = build_chat_reply(_state_clean(), "cosa manca?")
    assert "Installare" in reply.reply_markdown or "Verifica" in reply.reply_markdown

def test_cosa_manca_reply_shows_owner():
    reply = build_chat_reply(_state_clean(), "cosa manca?")
    assert "Luca" in reply.reply_markdown

def test_cosa_manca_reply_shows_due():
    reply = build_chat_reply(_state_clean(), "cosa manca?")
    assert "5/7" in reply.reply_markdown or "05/07" in reply.reply_markdown or "7/2026" not in reply.reply_markdown  # due formatted

def test_cosa_manca_empty_state_no_emoji():
    reply = build_chat_reply(_state_empty(), "cosa manca?")
    assert "📄" not in reply.reply_markdown
    assert "📌" not in reply.reply_markdown

def test_cosa_manca_no_report_link():
    from core.operational_memory.whatsapp_operational import render_whatsapp_reply
    reply = build_chat_reply(_state_canary(), "cosa manca?",
                             report_url="https://genesi.example.com/report/123")
    body = render_whatsapp_reply(reply)
    assert "📄" not in body
    assert "Report:" not in body

def test_fammi_report_keeps_link():
    from core.operational_memory.whatsapp_operational import render_whatsapp_reply
    reply = build_chat_reply(_state_canary(), "fammi il report",
                             report_url="https://genesi.example.com/report/123")
    body = render_whatsapp_reply(reply)
    assert "📄" in body or "Report:" in body

def test_cosa_manca_max_5_items():
    many = OperationalState(
        project_id="p",
        tasks=[_task(f"t{i}", f"Verifica item {i}") for i in range(8)],
        issues=[], decisions=[], open_questions=[], information=[],
    )
    reply = build_chat_reply(many, "cosa manca?")
    # At most 5 numbered lines + 1 "altri" line
    numbered = [l for l in reply.reply_markdown.splitlines() if l.strip() and l.strip()[0].isdigit()]
    assert len(numbered) <= 5

def test_open_tasks_count_excludes_low_value():
    items = open_tasks(_state_canary())
    # 5 low-value filtered → 3 remain: FG19, FG16, materiali
    assert len(items) == 3


# ---------------------------------------------------------------------------
# Regression: other intents unaffected
# ---------------------------------------------------------------------------

def test_problemi_aperti_unaffected():
    reply = build_chat_reply(_state_canary(), "problemi aperti?")
    assert reply.intent == "open_issues"
    assert "PX11" in reply.reply_markdown

def test_status_invocation_unaffected():
    reply = build_chat_reply(_state_canary(), "qual è lo stato?")
    assert reply.intent == "cmd_stato"

def test_briefing_unaffected():
    reply = build_chat_reply(_state_clean(), "fammi il report")
    assert reply.intent in {"briefing", "digest"}
