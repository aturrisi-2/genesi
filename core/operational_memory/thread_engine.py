from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta, timezone

from core.operational_memory.context_extractor import extract_context
from core.operational_memory.event_store import list_events, save_events
from core.operational_memory.models import OperationalEvent, OperationalItem, OperationalState, OperationalThread, ThreadStatus
from core.operational_memory.state_store import load_state, save_state


OPERATIVE_DOMAINS = {"TECHNICAL_OPERATION", "TECHNICAL_ISSUE", "TASK_ASSIGNMENT", "MEDIA_EVIDENCE"}
NON_THREAD_DOMAINS = {"LOGISTICS_PERSONAL", "PERSONNEL", "SOCIAL"}
DEFAULT_STALE_DAYS = 7
THREAD_WINDOW_HOURS = 36

_RESOLUTION_RE = re.compile(r"\b(?:risolto|sistemato|fatto|ok\s+sistemato|chiuso|completato)\b", re.IGNORECASE)
_IN_PROGRESS_RE = re.compile(r"\b(?:verifico|controllo|sostituisco|sistemiamo|intervengo|procedo|lo\s+faccio)\b", re.IGNORECASE)
_WAITING_RE = re.compile(r"\b(?:aspetto|attendo|domani\s+lo\s+porta|lo\s+porta|in\s+attesa|serve\s+conferma)\b", re.IGNORECASE)
_ISSUE_HINT_RE = re.compile(r"\b(?:non\s+parte|non\s+funziona|manca|blocc|guasto|errore|anomalia|disalimentat)\b", re.IGNORECASE)


def _parse_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return datetime.now(timezone.utc)


def _event_text(event: OperationalEvent) -> str:
    parts = [event.content or "", event.extracted_text or "", event.media_description or ""]
    for value in ("simulated_ocr", "simulated_text", "description", "file_name"):
        candidate = str((event.attachment_metadata or {}).get(value) or "")
        if candidate:
            parts.append(candidate)
    return " ".join(part.strip() for part in parts if part and part.strip())


def _context_tags_for_event(event: OperationalEvent, nearby_texts: list[str] | None = None) -> list[str]:
    context = extract_context(_event_text(event), nearby_texts=nearby_texts or [])
    return context.context_tags


def _stable_thread_id(project_id: str, seed: str) -> str:
    digest = hashlib.sha1(f"{project_id}:{seed}".encode("utf-8")).hexdigest()[:12]
    return f"thread_{digest}"


def _title_from_event(event: OperationalEvent, tags: list[str]) -> str:
    text = " ".join(_event_text(event).split())
    if len(text) > 90:
        text = text[:87].rstrip() + "..."
    if text:
        return text
    if tags:
        return " / ".join(tags[:4])
    return f"Thread operativo {event.event_id}"


def _is_operational_thread_candidate(event: OperationalEvent, event_tags: list[str]) -> bool:
    if event.domain in NON_THREAD_DOMAINS:
        return False
    if any(domain in NON_THREAD_DOMAINS for domain in event.secondary_domains):
        return False
    if (event.attachment_path or event.type in {"image", "pdf", "document"}) and not event_tags and not _ISSUE_HINT_RE.search(_event_text(event)):
        return False
    if event.project_impact_score >= 50 and (
        event.domain in OPERATIVE_DOMAINS or any(domain in OPERATIVE_DOMAINS for domain in event.secondary_domains)
    ):
        return True
    return False


def _status_from_text(text: str, current: ThreadStatus = "open") -> ThreadStatus:
    if _RESOLUTION_RE.search(text):
        return "resolved"
    if _WAITING_RE.search(text):
        return "waiting"
    if _IN_PROGRESS_RE.search(text):
        return "in_progress"
    return current


def _event_can_attach_to_thread(
    event: OperationalEvent,
    event_tags: list[str],
    thread: OperationalThread,
    event_time: datetime,
) -> bool:
    if thread.status in {"resolved", "stale"} and not _RESOLUTION_RE.search(_event_text(event)):
        return False
    thread_time = _parse_timestamp(thread.last_updated_at)
    if abs(event_time - thread_time) > timedelta(hours=THREAD_WINDOW_HOURS):
        return False

    tag_overlap = {tag.upper() for tag in event_tags} & {tag.upper() for tag in thread.context_tags}
    if tag_overlap:
        return True

    text = _event_text(event)
    if _ISSUE_HINT_RE.search(text) and event.project_impact_score >= 50:
        return True

    return False


def _append_unique(values: list[str], additions: list[str]) -> list[str]:
    seen = {value for value in values}
    for value in additions:
        if value and value not in seen:
            values.append(value)
            seen.add(value)
    return values


def _items_by_event_id(items: list[OperationalItem]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for item in items:
        if item.source_event_id:
            grouped.setdefault(item.source_event_id, []).append(item.text)
    return grouped


def _link_event_to_thread(
    thread: OperationalThread,
    event: OperationalEvent,
    event_tags: list[str],
    task_texts: list[str],
    issue_texts: list[str],
    question_texts: list[str],
) -> None:
    event.thread_id = thread.thread_id
    thread.related_event_ids = _append_unique(thread.related_event_ids, [event.event_id])
    thread.related_tasks = _append_unique(thread.related_tasks, task_texts)
    thread.related_issues = _append_unique(thread.related_issues, issue_texts)
    thread.unresolved_questions = _append_unique(thread.unresolved_questions, question_texts)
    if event.attachment_path or event.type in {"image", "pdf", "document"}:
        media_name = event.attachment_path or event.attachment_metadata.get("file_name") or event.event_id
        thread.related_media = _append_unique(thread.related_media, [media_name])
    thread.context_tags = _append_unique(thread.context_tags, event_tags)
    thread.project_impact_score = max(thread.project_impact_score, event.project_impact_score)
    if event.domain != "UNKNOWN" and thread.primary_domain == "UNKNOWN":
        thread.primary_domain = event.domain
    event_time = _parse_timestamp(event.timestamp)
    if event_time > _parse_timestamp(thread.last_updated_at):
        thread.last_updated_at = event.timestamp
    next_status = _status_from_text(_event_text(event), thread.status)
    if next_status == "resolved":
        thread.status = "resolved"
        thread.closed_at = event.timestamp
    elif thread.status not in {"resolved", "stale"}:
        thread.status = next_status
    thread.summary = _build_summary(thread)


def _build_summary(thread: OperationalThread) -> str:
    bits = []
    if thread.related_issues:
        bits.append(f"Problemi: {len(thread.related_issues)}")
    if thread.related_tasks:
        bits.append(f"Task: {len(thread.related_tasks)}")
    if thread.related_media:
        bits.append(f"Media: {len(thread.related_media)}")
    if thread.unresolved_questions:
        bits.append(f"Domande aperte: {len(thread.unresolved_questions)}")
    return "; ".join(bits) if bits else "Thread operativo in osservazione"


def build_threads_from_events(
    project_id: str,
    events: list[OperationalEvent],
    state: OperationalState,
    stale_days: int = DEFAULT_STALE_DAYS,
    now: datetime | None = None,
) -> tuple[list[OperationalThread], list[OperationalEvent]]:
    now = now or datetime.now(timezone.utc)
    sorted_events = sorted(events, key=lambda event: _parse_timestamp(event.timestamp))
    task_by_event = _items_by_event_id(state.tasks)
    issue_by_event = _items_by_event_id(state.issues)
    question_by_event = _items_by_event_id(state.open_questions)
    threads: list[OperationalThread] = []

    for idx, event in enumerate(sorted_events):
        event.thread_id = None
        nearby_texts = [
            _event_text(candidate)
            for candidate in sorted_events[max(0, idx - 2): min(len(sorted_events), idx + 3)]
            if candidate.event_id != event.event_id
        ]
        event_tags = _context_tags_for_event(event, nearby_texts)
        event_time = _parse_timestamp(event.timestamp)
        matched = next(
            (
                thread
                for thread in reversed(threads)
                if _event_can_attach_to_thread(event, event_tags, thread, event_time)
            ),
            None,
        )

        if matched is None and _is_operational_thread_candidate(event, event_tags):
            seed = event_tags[0] if event_tags else event.event_id
            matched = OperationalThread(
                thread_id=_stable_thread_id(project_id, seed),
                project_id=project_id,
                title=_title_from_event(event, event_tags),
                status=_status_from_text(_event_text(event), "open"),
                started_at=event.timestamp,
                last_updated_at=event.timestamp,
                primary_domain=event.domain,
                project_impact_score=event.project_impact_score,
                context_tags=list(event_tags),
                summary="Thread operativo in osservazione",
            )
            threads.append(matched)

        if matched is not None:
            _link_event_to_thread(
                matched,
                event,
                event_tags,
                task_by_event.get(event.event_id, []),
                issue_by_event.get(event.event_id, []),
                question_by_event.get(event.event_id, []),
            )

    stale_delta = timedelta(days=stale_days)
    for thread in threads:
        if thread.status not in {"resolved", "stale"} and now - _parse_timestamp(thread.last_updated_at) > stale_delta:
            thread.status = "stale"

    return threads, sorted_events


async def rebuild_project_threads(project_id: str, stale_days: int = DEFAULT_STALE_DAYS) -> list[OperationalThread]:
    events = await list_events(project_id)
    state = await load_state(project_id)
    threads, updated_events = build_threads_from_events(project_id, events, state, stale_days=stale_days)
    state.threads = threads
    await save_events(project_id, updated_events)
    await save_state(project_id, state)
    return threads
