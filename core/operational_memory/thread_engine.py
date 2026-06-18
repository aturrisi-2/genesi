from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from core.operational_memory.context_extractor import extract_context
from core.operational_memory.chat_profile_engine import build_adaptive_chat_profile
from core.operational_memory.event_store import list_events, save_events
from core.operational_memory.macro_thread_engine import build_macro_threads
from core.operational_memory.models import OperationalEvent, OperationalItem, OperationalState, OperationalThread, ThreadStatus
from core.operational_memory.state_store import load_state, save_state


OPERATIVE_DOMAINS = {"TECHNICAL_OPERATION", "TECHNICAL_ISSUE", "TASK_ASSIGNMENT", "MEDIA_EVIDENCE"}
NON_THREAD_DOMAINS = {"LOGISTICS_PERSONAL", "PERSONNEL", "SOCIAL"}
DEFAULT_STALE_DAYS = 7
THREAD_WINDOW_HOURS = 36

_RESOLUTION_RE = re.compile(r"\b(?:risolto|sistemato|fatto|ok\s+sistemato|chiuso|completato|verificato|funziona)\b", re.IGNORECASE)
_IN_PROGRESS_RE = re.compile(r"\b(?:verifico|controllo|sostituisco|sistemiamo|intervengo|procedo|lo\s+faccio)\b", re.IGNORECASE)
_WAITING_RE = re.compile(r"\b(?:aspetto|attendo|domani\s+lo\s+porta|lo\s+porta|in\s+attesa|serve\s+conferma)\b", re.IGNORECASE)
_ISSUE_HINT_RE = re.compile(r"\b(?:non\s+parte|non\s+funziona|manca|blocc|guasto|errore|anomalia|disalimentat)\b", re.IGNORECASE)
_TECH_CODE_RE = re.compile(r"^(?:T\d{1,3}|M\d{1,3}|SS\d{1,3}|EWC\d{1,3}|ELS\d{1,3}|UTA|POL-\d{1,3}|IP|PD|BDF|[A-Z]{1,4}\d{1,4}|[A-Z]{1,4}-\d{1,4})$", re.IGNORECASE)
_COMPONENT_RE = re.compile(r"^(?:plenum|vela|scarpetta|serranda|fancoil|canale|potenziometro|servomotore|montante|mandata|ripresa)$", re.IGNORECASE)
_AREA_LOCATION_RE = re.compile(r"^(?:STF|STM|STA|B\d+\s+V\d+|Torre\s+\d+|porta\s+\d{1,4}|COPERTURA\s+T\d+|L\d{1,2}|piano\s+\d{1,2})$", re.IGNORECASE)


@dataclass
class BoundaryEvaluation:
    continuity_score: int = 0
    topic_shift_score: int = 100
    signals: list[str] = field(default_factory=list)
    resolution_signal: bool = False
    reopen_signal: bool = False
    evidence_strength: str = "none"
    should_attach: bool = False
    should_create_follow_up: bool = False
    related_past_thread_id: str | None = None


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


def _event_primary_text(event: OperationalEvent) -> str:
    return " ".join(part.strip() for part in [event.content or "", event.extracted_text or ""] if part and part.strip())


def _context_tags_for_event(
    event: OperationalEvent,
    nearby_texts: list[str] | None = None,
    include_nearby: bool = True,
) -> list[str]:
    context = extract_context(_event_text(event), nearby_texts=nearby_texts if include_nearby else [])
    return context.context_tags


def _has_resolution_signal(text: str) -> bool:
    lowered = text.lower()
    if "non funziona" in lowered:
        return False
    return bool(_RESOLUTION_RE.search(text))


def _lifecycle_tags_for_event(event: OperationalEvent, nearby_texts: list[str]) -> list[str]:
    primary_tags = _context_tags_for_event(event, include_nearby=False)
    if primary_tags:
        return primary_tags
    text = _event_primary_text(event)
    word_count = len(text.split())
    if _is_media_event(event) or word_count <= 4 or _ISSUE_HINT_RE.search(text) or _has_resolution_signal(text):
        return _context_tags_for_event(event, nearby_texts, include_nearby=True)
    return []


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
    if _is_media_event(event) and _evidence_strength(event, event_tags) == "weak":
        return False
    if _is_media_event(event) and not event_tags and not _ISSUE_HINT_RE.search(_event_text(event)):
        return False
    if event.project_impact_score >= 50 and (
        event.domain in OPERATIVE_DOMAINS or any(domain in OPERATIVE_DOMAINS for domain in event.secondary_domains)
    ):
        return True
    return False


def _is_media_event(event: OperationalEvent) -> bool:
    return bool(event.attachment_path or event.type in {"image", "pdf", "document"})


def _has_media_text(event: OperationalEvent) -> bool:
    metadata = event.attachment_metadata or {}
    return bool((event.content or "").strip() or (event.extracted_text or "").strip() or metadata.get("simulated_ocr") or metadata.get("simulated_text"))


def _evidence_strength(event: OperationalEvent, event_tags: list[str]) -> str:
    if not _is_media_event(event):
        return "high" if event.project_impact_score >= 80 else "medium" if event.project_impact_score >= 50 else "none"
    text = _event_primary_text(event)
    metadata_text = " ".join(
        str((event.attachment_metadata or {}).get(key) or "")
        for key in ("simulated_ocr", "simulated_text")
    ).strip()
    if (event.extracted_text or "").strip() and event_tags:
        return "high"
    if (text or metadata_text) and event_tags:
        return "medium"
    return "weak"


def _tag_groups(tags: list[str]) -> dict[str, set[str]]:
    groups = {"code": set(), "component": set(), "area_location": set(), "other": set()}
    for tag in tags:
        key = tag.upper()
        if _TECH_CODE_RE.match(tag):
            groups["code"].add(key)
        elif _COMPONENT_RE.match(tag):
            groups["component"].add(key)
        elif _AREA_LOCATION_RE.match(tag):
            groups["area_location"].add(key)
        else:
            groups["other"].add(key)
    return groups


def _problem_signatures(text: str) -> set[str]:
    lowered = text.lower()
    signatures = set()
    for phrase in (
        "non parte",
        "non funziona",
        "manca potenziometro",
        "manca collegamento",
        "non alimentata",
        "disalimentata",
        "guasto",
        "anomalia",
    ):
        if phrase in lowered:
            signatures.add(phrase)
    if "manca" in lowered:
        signatures.add("manca")
    return signatures


def _strong_continuity_signals(event: OperationalEvent, event_tags: list[str], thread: OperationalThread) -> list[str]:
    event_groups = _tag_groups(event_tags)
    thread_groups = _tag_groups(thread.context_tags)
    signals: list[str] = []
    code_overlap = event_groups["code"] & thread_groups["code"]
    if code_overlap:
        signals.append("stesso codice tecnico specifico")
    if len(code_overlap) >= 2:
        signals.append("stesso impianto")
    if event_groups["component"] & thread_groups["component"]:
        signals.append("stesso componente")
    if event_groups["area_location"] & thread_groups["area_location"]:
        signals.append("stessa zona/posizione")
    problem_overlap = _problem_signatures(_event_text(event)) & _problem_signatures(" ".join([thread.title, *thread.related_issues]))
    if problem_overlap:
        signals.append("stesso problema")
    return signals


def _has_incompatible_new_code(event_tags: list[str], thread: OperationalThread) -> bool:
    event_codes = _tag_groups(event_tags)["code"]
    thread_codes = _tag_groups(thread.context_tags)["code"]
    if not event_codes or not thread_codes:
        return False
    return not bool(event_codes & thread_codes)


def _is_temporally_near(event_time: datetime, thread: OperationalThread) -> bool:
    return abs(event_time - _parse_timestamp(thread.last_updated_at)) <= timedelta(hours=THREAD_WINDOW_HOURS)


def _topic_shift_score(event_tags: list[str], thread: OperationalThread, signals: list[str]) -> int:
    if _has_incompatible_new_code(event_tags, thread):
        return 90
    if len(signals) >= 2:
        return 15
    if len(signals) == 1:
        return 55
    return 85


def _continuity_score(signals: list[str], event_time: datetime, thread: OperationalThread, evidence_strength: str) -> int:
    score = min(80, len(signals) * 35)
    if _is_temporally_near(event_time, thread) and signals:
        score += 10
    if evidence_strength == "high" and signals:
        score += 10
    if evidence_strength == "weak":
        score -= 15
    return max(0, min(100, score))


def _evaluate_boundary(event: OperationalEvent, event_tags: list[str], thread: OperationalThread, event_time: datetime) -> BoundaryEvaluation:
    signals = _strong_continuity_signals(event, event_tags, thread)
    evidence_strength = _evidence_strength(event, event_tags)
    resolution_signal = _has_resolution_signal(_event_text(event))
    reopen_signal = thread.status in {"resolved", "stale"} and bool(_ISSUE_HINT_RE.search(_event_text(event)))
    topic_shift = _topic_shift_score(event_tags, thread, signals)
    continuity = _continuity_score(signals, event_time, thread, evidence_strength)
    strong_signal_count = len(signals)
    is_media = _is_media_event(event)

    should_attach = (
        thread.status not in {"resolved", "stale"}
        and topic_shift < 70
        and strong_signal_count >= 2
        and continuity >= 55
    )
    if is_media and evidence_strength == "weak":
        should_attach = should_attach and strong_signal_count >= 2
    if resolution_signal:
        should_attach = thread.status not in {"resolved", "stale"} and strong_signal_count >= 2
    should_follow_up = thread.status in {"resolved", "stale"} and reopen_signal and strong_signal_count >= 2

    return BoundaryEvaluation(
        continuity_score=continuity,
        topic_shift_score=topic_shift,
        signals=signals,
        resolution_signal=resolution_signal,
        reopen_signal=reopen_signal,
        evidence_strength=evidence_strength,
        should_attach=should_attach,
        should_create_follow_up=should_follow_up,
        related_past_thread_id=thread.thread_id if should_follow_up else None,
    )


def _status_from_text(text: str, current: ThreadStatus = "open") -> ThreadStatus:
    if _has_resolution_signal(text):
        return "resolved"
    if _WAITING_RE.search(text):
        return "waiting"
    if _IN_PROGRESS_RE.search(text):
        return "in_progress"
    return current


def _best_thread_match(
    event: OperationalEvent,
    event_tags: list[str],
    threads: list[OperationalThread],
    event_time: datetime,
) -> tuple[OperationalThread | None, BoundaryEvaluation | None]:
    if event.domain in NON_THREAD_DOMAINS or any(domain in NON_THREAD_DOMAINS for domain in event.secondary_domains):
        return None, None
    best_thread: OperationalThread | None = None
    best_evaluation: BoundaryEvaluation | None = None
    best_score = -1
    for thread in reversed(threads):
        evaluation = _evaluate_boundary(event, event_tags, thread, event_time)
        if evaluation.should_create_follow_up and best_evaluation is None:
            best_evaluation = evaluation
        if not evaluation.should_attach:
            continue
        if evaluation.continuity_score > best_score:
            best_thread = thread
            best_evaluation = evaluation
            best_score = evaluation.continuity_score
    return best_thread, best_evaluation


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
    evaluation: BoundaryEvaluation,
    task_texts: list[str],
    issue_texts: list[str],
    question_texts: list[str],
) -> None:
    event.thread_id = thread.thread_id
    event.thread_continuity_score = evaluation.continuity_score
    event.topic_shift_score = evaluation.topic_shift_score
    event.resolution_signal = evaluation.resolution_signal
    event.reopen_signal = evaluation.reopen_signal
    event.evidence_strength = evaluation.evidence_strength
    event.thread_link_reason = "; ".join(evaluation.signals) if evaluation.signals else "thread creato da evento operativo"
    thread.related_event_ids = _append_unique(thread.related_event_ids, [event.event_id])
    thread.related_tasks = _append_unique(thread.related_tasks, task_texts)
    thread.related_issues = _append_unique(thread.related_issues, issue_texts)
    thread.unresolved_questions = _append_unique(thread.unresolved_questions, question_texts)
    if event.attachment_path or event.type in {"image", "pdf", "document"}:
        media_name = event.attachment_path or event.attachment_metadata.get("file_name") or event.event_id
        thread.related_media = _append_unique(thread.related_media, [media_name])
    if not (_is_media_event(event) and evaluation.evidence_strength == "weak"):
        thread.context_tags = _append_unique(thread.context_tags, event_tags)
        thread.continuity_signals = _append_unique(thread.continuity_signals, evaluation.signals)
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
        thread.resolution_signals = _append_unique(thread.resolution_signals, [event.thread_link_reason])
    elif thread.status not in {"resolved", "stale"}:
        thread.status = next_status
    if evaluation.related_past_thread_id:
        thread.related_past_thread_ids = _append_unique(thread.related_past_thread_ids, [evaluation.related_past_thread_id])
    if event.thread_continuity_score >= 80:
        thread.grouping_confidence = "high"
    elif event.thread_continuity_score >= 55 and thread.grouping_confidence == "low":
        thread.grouping_confidence = "medium"
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
        event.thread_continuity_score = 0
        event.topic_shift_score = 100
        event.resolution_signal = False
        event.reopen_signal = False
        event.thread_link_reason = ""
        nearby_texts = [
            _event_text(candidate)
            for candidate in sorted_events[max(0, idx - 2): min(len(sorted_events), idx + 3)]
            if candidate.event_id != event.event_id
        ]
        event_tags = _lifecycle_tags_for_event(event, nearby_texts)
        event.evidence_strength = _evidence_strength(event, event_tags)
        event_time = _parse_timestamp(event.timestamp)
        matched, evaluation = _best_thread_match(event, event_tags, threads, event_time)

        if matched is None and _is_operational_thread_candidate(event, event_tags):
            related_past_thread_ids = []
            if evaluation and evaluation.related_past_thread_id:
                related_past_thread_ids.append(evaluation.related_past_thread_id)
            seed = f"{event_tags[0] if event_tags else 'event'}:{event.event_id}"
            creation_reason = (
                "nuovo thread: evento operativo senza continuita forte"
                if not related_past_thread_ids
                else "follow-up: tema simile a thread storico chiuso/stale"
            )
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
                creation_reason=creation_reason,
                related_past_thread_ids=related_past_thread_ids,
                grouping_confidence="medium" if event_tags else "low",
            )
            threads.append(matched)
            evaluation = BoundaryEvaluation(
                continuity_score=0,
                topic_shift_score=100,
                signals=["evento operativo iniziale"],
                resolution_signal=_has_resolution_signal(_event_text(event)),
                reopen_signal=bool(related_past_thread_ids),
                evidence_strength=event.evidence_strength,
            )

        if matched is not None:
            _link_event_to_thread(
                matched,
                event,
                event_tags,
                evaluation or BoundaryEvaluation(evidence_strength=event.evidence_strength),
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
    profile = build_adaptive_chat_profile(project_id, updated_events, threads)
    macro_threads = build_macro_threads(project_id, threads, updated_events, profile)
    state.threads = threads
    state.macro_threads = macro_threads
    state.adaptive_chat_profile = profile
    await save_events(project_id, updated_events)
    await save_state(project_id, state)
    return threads
