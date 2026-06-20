"""FASE 7 — Silent Chat Presence.

Genesi listens to every message, stores it, and updates the operational memory
— always, silently. It produces a visible chat reply ONLY when explicitly
invoked (see invocation_router). When it does reply, the answer is a compact,
mobile-readable payload (table + short synthesis + actions + a link to the full
downloadable report) — never a wall of text.

Generic and multimodal: text and attachments (image/pdf/document) both feed the
memory. No chat/platform/profession token is hardcoded; no LLM decides when to
speak."""

from __future__ import annotations

from typing import Awaitable, Callable, Optional

from core.log import log
from core.operational_memory.incremental_rebuild import incremental_rebuild
from core.operational_memory.invocation_router import is_invoked
from core.operational_memory.models import (
    ChatMessage,
    ChatReply,
    InvocationConfig,
    OperationalEvent,
    OperationalState,
)
from core.operational_memory.query_engine import answer_query, build_briefing
from core.operational_memory.report_store import save_report
from core.operational_memory.state_store import load_state
from core.operational_memory.watcher_engine import ingest_event, process_pending_events


Updater = Callable[[ChatMessage], Awaitable[None]]


def _event_from_message(message: ChatMessage) -> OperationalEvent:
    event = OperationalEvent(
        event_id=message.message_id,
        project_id=message.project_id,
        source=message.source or "chat",
        sender=message.sender or "",
        content=message.text or "",
    )
    if message.timestamp:
        event.timestamp = message.timestamp
    if message.attachments:
        attachment = message.attachments[0]
        event.type = attachment.type or "document"  # type: ignore[assignment]
        event.attachment_path = attachment.path
        event.attachment_type = attachment.type
        if attachment.extracted_text:
            event.extracted_text = attachment.extracted_text
        if attachment.metadata:
            event.attachment_metadata = dict(attachment.metadata)
    return event


async def silent_update(message: ChatMessage, rebuild: bool = True) -> None:
    """Listen + store + update memory. Never returns anything to the chat."""
    event = _event_from_message(message)
    _stored, created = await ingest_event(event)
    log(
        "OPERATIONAL_SILENT_INGEST",
        project_id=message.project_id,
        message_id=message.message_id,
        created=created,
        source=message.source,
    )
    if not created:
        return  # idempotent: already seen, no duplicate processing
    await process_pending_events(message.project_id, rebuild_threads=False)
    if rebuild:
        await incremental_rebuild(
            message.project_id,
            relation_window_days=21,
            relation_max_candidates_per_thread=40,
        )


def _compact_table(state: OperationalState) -> str:
    briefing = build_briefing(state)
    lines = ["| Categoria | N |", "| --- | ---: |"]
    for row in briefing.rows:
        if row.count:
            lines.append(f"| {row.label} | {row.count} |")
    return "\n".join(lines)


def build_chat_reply(
    state: OperationalState,
    query: str,
    report_id: str = "",
    report_url: str = "",
    invoked_by: str = "",
) -> ChatReply:
    """Pure: turn the current state + the asked query into a compact chat reply."""
    briefing = build_briefing(state)
    result = answer_query(state, query)
    focused = result.intent not in {"briefing", "digest", "unknown"}

    evidence: list[str] = []
    focused_lines: list[str] = []
    if focused and result.items:
        for item in result.items[:5]:
            status = f" ({item.status})" if item.status else ""
            focused_lines.append(f"- {item.text}{status}")
            evidence.extend(item.evidence_event_ids[:1])
        if result.count > 5:
            focused_lines.append(f"- … e altri {result.count - 5}")

    synthesis = result.summary if (focused and result.summary) else briefing.synthesis
    actions = [briefing.recommended_action]

    parts: list[str] = []
    if focused:
        parts.append(f"**{result.summary}**")
        parts.extend(focused_lines)
        parts.append("")
    parts.append("**Quadro operativo**")
    parts.append(_compact_table(state))
    parts.append("")
    parts.append(f"**Sintesi:** {briefing.synthesis}")
    parts.append(f"**Azione consigliata:** {briefing.recommended_action}")
    if report_url:
        parts.append(f"**Report completo:** {report_url}")
    reply_markdown = "\n".join(parts).strip()

    return ChatReply(
        project_id=state.project_id or "",
        invoked_by=invoked_by,
        intent=result.intent,
        table_markdown=_compact_table(state),
        synthesis=synthesis,
        actions=actions,
        evidence_event_ids=evidence,
        report_id=report_id,
        report_url=report_url,
        reply_markdown=reply_markdown,
    )


async def handle_incoming(
    message: ChatMessage,
    config: Optional[InvocationConfig] = None,
    updater: Optional[Updater] = None,
    save_report_on_reply: bool = True,
) -> Optional[ChatReply]:
    """Always ingest + update memory silently. Return a ChatReply ONLY when the
    message explicitly invokes Genesi; otherwise return None (stay silent)."""
    config = config or InvocationConfig()
    update = updater or silent_update

    # 1. Silent listen + memory update — always, for every message.
    await update(message)

    # 2. Explicit invocation gate.
    decision = is_invoked(message.text, config, is_dm=message.is_dm)
    if not decision.respond:
        return None

    # 3. Build the reply from the (now updated) operational state.
    state = await load_state(message.project_id)
    report_id = ""
    report_url = ""
    if save_report_on_reply:
        report = save_report(message.project_id, build_briefing(state).markdown)
        report_id = report.report_id
        report_url = f"/api/operational/projects/{message.project_id}/reports/{report_id}/download"
    return build_chat_reply(
        state,
        decision.query,
        report_id=report_id,
        report_url=report_url,
        invoked_by=message.sender,
    )
