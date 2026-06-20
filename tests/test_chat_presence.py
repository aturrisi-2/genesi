from __future__ import annotations

import asyncio

import pytest

from core.operational_memory.chat_presence import (
    _event_from_message,
    build_chat_reply,
    handle_incoming,
)
from core.operational_memory.models import (
    ChatAttachment,
    ChatMessage,
    Decision,
    Issue,
    InvocationConfig,
    LifecycleHistoryEntry,
    LifecycleState,
    OperationalQuestion,
    OperationalState,
    OperationalTask,
)


PROJECT = "chat-proj"


def _lc(category, status):
    return LifecycleState(
        category=category, current_status=status, status_reason="r", evidence_event_ids=["ev1"],
        lifecycle_history=[LifecycleHistoryEntry(status=status, changed_at="2026-06-12T08:00:00+00:00")],
    )


def _seed_state():
    return OperationalState(
        project_id=PROJECT,
        tasks=[OperationalTask(id="t1", text="ordinare il materiale", source="m", source_event_id="e1", lifecycle=_lc("task", "open")),
               OperationalTask(id="t2", text="inviare il preventivo", source="m", source_event_id="e2", lifecycle=_lc("task", "completed"))],
        issues=[Issue(id="i1", text="accesso non funziona", source="m", source_event_id="e3", lifecycle=_lc("issue", "open"))],
        decisions=[Decision(id="d1", text="scelto fornitore A", source="m", source_event_id="e4", lifecycle=_lc("decision", "confirmed"))],
        open_questions=[OperationalQuestion(id="q1", text="quando consegniamo?", source="m", source_event_id="e5", lifecycle=_lc("question", "open"))],
    )


@pytest.fixture
def stores(monkeypatch, tmp_path):
    from core.operational_memory import state_store, report_store
    monkeypatch.setattr(state_store, "_BASE_DIR", tmp_path / "state")
    monkeypatch.setattr(report_store, "_BASE_DIR", tmp_path / "reports")
    asyncio.run(state_store.save_state(PROJECT, _seed_state()))
    return tmp_path


def _msg(text, message_id="m1", is_dm=False, sender="ann"):
    return ChatMessage(project_id=PROJECT, message_id=message_id, text=text, sender=sender, is_dm=is_dm)


# --------------------------------------------------------------------------- #
# Silent vs invoked
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_normal_message_is_silent_but_updates_memory(stores):
    seen = []

    async def spy(message):
        seen.append(message.message_id)

    reply = await handle_incoming(_msg("ragazzi a che ora domani?"), updater=spy)
    assert reply is None  # silent
    assert seen == ["m1"]  # memory update still happened


@pytest.mark.asyncio
async def test_invocation_returns_reply(stores):
    seen = []

    async def spy(message):
        seen.append(message.message_id)

    reply = await handle_incoming(_msg("Genesi, fammi il punto"), updater=spy)
    assert reply is not None
    assert seen == ["m1"]  # updated even before replying
    assert reply.table_markdown and reply.synthesis and reply.actions
    assert reply.report_id and reply.report_url
    assert "/reports/" in reply.report_url
    assert "Quadro operativo" in reply.reply_markdown
    # URL is kept in report_url field, not embedded in the reply text
    assert "Report completo:" not in reply.reply_markdown
    assert reply.report_url not in reply.reply_markdown
    # No pipe table in the reply text (mobile card format)
    assert "| Categoria | N |" not in reply.reply_markdown
    # Bullet card present
    assert "•" in reply.reply_markdown
    # Structured synthesis section
    assert "🧭 Sintesi operativa" in reply.reply_markdown
    assert "• Stato:" in reply.reply_markdown
    assert "• Attenzione:" in reply.reply_markdown
    assert "• Azione consigliata:" in reply.reply_markdown


@pytest.mark.asyncio
async def test_silent_path_does_not_save_report(stores):
    from core.operational_memory.report_store import list_reports

    async def spy(message):
        return None

    await handle_incoming(_msg("messaggio normale"), updater=spy)
    assert list_reports(PROJECT) == []


@pytest.mark.asyncio
async def test_reply_uses_previously_stored_state(stores):
    # The seeded state stands in for earlier, non-invoked messages already folded
    # into memory. An invocation must answer using them.
    async def spy(message):
        return None

    reply = await handle_incoming(_msg("@genesi cosa resta da fare?"), updater=spy)
    assert reply is not None
    # focused open-tasks answer must reference the previously stored open task
    assert "ordinare il materiale" in reply.reply_markdown


# --------------------------------------------------------------------------- #
# Pure reply rendering
# --------------------------------------------------------------------------- #


def test_build_chat_reply_focused_intent():
    reply = build_chat_reply(_seed_state(), "quali problemi sono aperti?", report_url="/x")
    assert reply.intent == "open_issues"
    assert "accesso non funziona" in reply.reply_markdown
    assert reply.evidence_event_ids  # evidence carried


def test_build_chat_reply_generic_briefing():
    reply = build_chat_reply(_seed_state(), "fammi il punto")
    assert reply.intent == "briefing"
    # table_markdown still has the pipe table (for report/API use)
    assert "| Categoria | N |" in reply.table_markdown
    # but reply_markdown uses the mobile card (no pipe tables)
    assert "| Categoria | N |" not in reply.reply_markdown
    assert "•" in reply.reply_markdown
    assert reply.synthesis and reply.actions


def test_build_chat_reply_excludes_completed_from_open_tasks():
    reply = build_chat_reply(_seed_state(), "cosa resta da fare?")
    assert "ordinare il materiale" in reply.reply_markdown
    assert "inviare il preventivo" not in reply.reply_markdown  # completed, not active


# --------------------------------------------------------------------------- #
# Multimodal mapping + no hardcoding
# --------------------------------------------------------------------------- #


def test_event_from_message_maps_attachment():
    msg = ChatMessage(
        project_id=PROJECT, message_id="img1", text="foto del quadro",
        attachments=[ChatAttachment(path="/tmp/x.jpg", type="image", extracted_text="OCR text", metadata={"k": "v"})],
    )
    event = _event_from_message(msg)
    assert event.type == "image" and event.attachment_path == "/tmp/x.jpg"
    assert event.extracted_text == "OCR text" and event.attachment_metadata == {"k": "v"}


def test_event_from_message_plain_text():
    event = _event_from_message(ChatMessage(project_id=PROJECT, message_id="m9", text="ciao", sender="bob"))
    assert event.content == "ciao" and event.sender == "bob" and event.type == "text"


def test_synthesis_is_structured_not_paragraph():
    reply = build_chat_reply(_seed_state(), "fammi il punto")
    md = reply.reply_markdown
    # No single long synthesis line — should be separate bullet lines
    assert "Sintesi operativa" in md
    for key in ["Stato:", "Attenzione:", "Cambiamenti:", "Esclusioni:", "Azione consigliata:"]:
        assert f"• {key}" in md, f"missing structured line: {key}"


def test_no_hardcoded_domain_tokens_in_chat_presence():
    import re

    import core.operational_memory.chat_presence as mod

    body = open(mod.__file__, "r", encoding="utf-8").read().upper()
    for token in ["TAB CEFLA", "T6", "T7", "UTA", "EWC05", "SS01", "B02", "CANTIERE", "WHATSAPP"]:
        assert not re.search(rf"\b{re.escape(token)}\b", body), f"hardcoded token: {token}"
