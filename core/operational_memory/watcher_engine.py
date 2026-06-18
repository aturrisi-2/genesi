from __future__ import annotations

from core.log import log
from core.operational_memory.domain_classifier import classify_event, should_extract_operationally
from core.operational_memory.event_store import (
    append_event,
    list_events,
    mark_event_status,
    save_events,
)
from core.operational_memory.models import OperationalEvent, OperationalState
from core.operational_memory.state_engine import ingest_messages
from core.operational_memory.state_store import load_state, save_state
from core.operational_memory.thread_engine import rebuild_project_threads


def normalize_event(event: OperationalEvent) -> OperationalEvent:
    event.content = (event.content or "").strip()
    event.sender = (event.sender or "").strip()
    event.source = (event.source or "simulated").strip()
    event.processed_status = event.processed_status or "pending"
    return classify_event(event)


def _domain_stats(events: list[OperationalEvent]) -> dict[str, int]:
    def has_domain(event: OperationalEvent, domain: str) -> bool:
        return event.domain == domain or domain in event.secondary_domains

    return {
        "technical_events": len(
            [
                event
                for event in events
                if event.domain in {"TECHNICAL_OPERATION", "TECHNICAL_ISSUE", "TASK_ASSIGNMENT"}
                or any(domain in {"TECHNICAL_OPERATION", "TECHNICAL_ISSUE", "TASK_ASSIGNMENT"} for domain in event.secondary_domains)
            ]
        ),
        "logistics_operational_events": len([event for event in events if has_domain(event, "LOGISTICS_OPERATIONAL")]),
        "logistics_personal_events": len([event for event in events if has_domain(event, "LOGISTICS_PERSONAL")]),
        "personnel_events": len([event for event in events if has_domain(event, "PERSONNEL")]),
        "social_events": len([event for event in events if has_domain(event, "SOCIAL")]),
        "media_events": len([event for event in events if has_domain(event, "MEDIA_EVIDENCE")]),
    }


async def _save_domain_stats(project_id: str) -> None:
    events = await list_events(project_id)
    state = await load_state(project_id)
    state.domain_stats = _domain_stats(events)
    await save_state(project_id, state)


async def ingest_event(event: OperationalEvent) -> tuple[OperationalEvent, bool]:
    normalized = normalize_event(event)
    stored, created = await append_event(normalized)
    log(
        "OPERATIONAL_EVENT_INGESTED",
        project_id=stored.project_id,
        event_id=stored.event_id,
        created=created,
        type=stored.type,
    )
    return stored, created


async def ingest_events_batch(project_id: str, events: list[OperationalEvent]) -> dict:
    accepted = 0
    duplicates = 0
    failed = 0

    for event in events:
        try:
            if event.project_id and event.project_id != project_id:
                failed += 1
                continue
            event.project_id = project_id
            _stored, created = await ingest_event(event)
            if created:
                accepted += 1
            else:
                duplicates += 1
        except Exception as exc:
            failed += 1
            log(
                "OPERATIONAL_EVENT_BATCH_INGEST_ERROR",
                project_id=project_id,
                event_id=getattr(event, "event_id", ""),
                error=str(exc),
            )

    return {"accepted": accepted, "duplicates": duplicates, "failed": failed}


async def get_events(project_id: str) -> list[OperationalEvent]:
    return await list_events(project_id)


def event_to_extraction_message(event: OperationalEvent) -> str:
    if event.type == "text":
        return f"[{event.timestamp}] {event.sender}: {event.content}".strip()

    attachment = event.attachment_metadata or {}
    file_name = attachment.get("file_name") or attachment.get("name") or "attachment"
    extracted_text = (event.extracted_text or "").strip()
    caption = (event.content or "").strip()
    simulated_text = attachment.get("simulated_ocr") or attachment.get("simulated_text") or ""
    text_parts = []
    for candidate in (caption, extracted_text, simulated_text):
        candidate = (candidate or "").strip()
        if candidate and candidate not in text_parts:
            text_parts.append(candidate)
    useful_text = "\n".join(text_parts)
    if not useful_text:
        return ""
    source_bits = []
    if extracted_text:
        source_bits.append("testo OCR")
    if caption:
        source_bits.append("caption")
    if simulated_text and not extracted_text:
        source_bits.append("testo simulato")
    return (
        f"[{event.timestamp}] {event.sender} ha inviato {event.type} '{file_name}'. "
        f"Fonte media: {', '.join(source_bits)}. "
        f"Testo operativo: {useful_text}"
    ).strip()


async def process_pending_events(project_id: str) -> dict:
    events = await list_events(project_id)
    pending = [event for event in events if event.processed_status == "pending"]
    processed = 0
    failed = 0
    state: OperationalState | None = None

    for event in pending:
        try:
            if event.domain == "UNKNOWN" and event.operational_relevance_score == 0:
                event = normalize_event(event)
                events = [event if candidate.event_id == event.event_id else candidate for candidate in events]
                await save_events(project_id, events)

            if not should_extract_operationally(event):
                await mark_event_status(project_id, event.event_id, "processed")
                processed += 1
                continue

            message = event_to_extraction_message(event)
            event_index = next((idx for idx, candidate in enumerate(events) if candidate.event_id == event.event_id), -1)
            context_events = []
            if event_index >= 0:
                start = max(0, event_index - 2)
                end = min(len(events), event_index + 3)
                context_events = [
                    candidate
                    for candidate in events[start:end]
                    if candidate.event_id != event.event_id
                ]
            nearby_messages = [event_to_extraction_message(candidate) for candidate in context_events]
            if not message:
                await mark_event_status(project_id, event.event_id, "processed")
                processed += 1
                continue
            state = await ingest_messages(
                project_id,
                [message],
                source_event=event,
                nearby_messages=nearby_messages,
            )
            await mark_event_status(project_id, event.event_id, "processed")
            processed += 1
        except Exception as exc:
            failed += 1
            await mark_event_status(project_id, event.event_id, "failed")
            log(
                "OPERATIONAL_EVENT_PROCESS_ERROR",
                project_id=project_id,
                event_id=event.event_id,
                error=str(exc),
            )

    await _save_domain_stats(project_id)
    threads = await rebuild_project_threads(project_id)

    return {
        "project_id": project_id,
        "processed": processed,
        "failed": failed,
        "pending_remaining": len([event for event in await list_events(project_id) if event.processed_status == "pending"]),
        "threads": len(threads),
        "state": state,
    }
