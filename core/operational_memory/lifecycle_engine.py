"""Operational State Memory / Lifecycle Engine (FASE 4).

Keeps a persistent, explainable lifecycle for every operational item (task,
issue, decision, question, information) and lets it evolve as new evidence
arrives. Everything here is domain-agnostic: statuses and the signal patterns
that drive transitions are generic operational concepts (open/resolved/
superseded/reopened/stale...), never tied to a profession, a site, a platform
or any specific token. The same engine works for a construction chat, a family
group, a logistics flow or a customer-support thread.

Transitions are driven by:
  * the item's own initial text,
  * later evidence in the same thread (text + media-extracted text),
  * temporal decay (stale_after_days).

Every transition records the evidence event ids and a human-readable reason, so
"this is resolved" can always be traced back to the messages that prove it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from core.operational_memory.models import (
    LifecycleCategory,
    LifecycleHistoryEntry,
    LifecycleState,
    LifecycleTransitionRecord,
    OperationalEvent,
    OperationalItem,
    OperationalLifecycleDelta,
    OperationalLifecycleSnapshot,
    OperationalState,
    OperationalThread,
    utc_now_iso,
)


DEFAULT_STALE_AFTER_DAYS = 14


# --------------------------------------------------------------------------- #
# Generic, multilingual operational signals (IT + EN). No domain vocabulary.
# --------------------------------------------------------------------------- #

_NEG_RESOLUTION_RE = re.compile(
    r"\b(non\s+funziona|non\s+risolt\w*|non\s+parte|non\s+va|not\s+working|not\s+fixed|"
    r"not\s+resolved|still\s+broken|ancora\s+rotto|ancora\s+ko|non\s+completat\w*)\b",
    re.IGNORECASE,
)
_RESOLUTION_RE = re.compile(
    r"\b(risolt\w*|sistemat\w*|completat\w*|fatt[oa]|chius[oa]|consegnat\w*|evas[oa]|"
    r"a\s+posto|funziona|resolved|fixed|done|completed|delivered|closed|solved|"
    r"works\s+now|working\s+now|fulfilled|sorted)\b",
    re.IGNORECASE,
)
_VERIFICATION_RE = re.compile(
    r"\b(verificat\w*|controllat\w*|collaudat\w*|validat\w*|verified|checked|validated|tested\s+ok)\b",
    re.IGNORECASE,
)
_REOPEN_RE = re.compile(
    r"\b(di\s+nuovo|riapert\w*|tornat[oa]|ricompars\w*|again|reopened|back\s+again|"
    r"regression|regressione|si\s+ripresenta)\b",
    re.IGNORECASE,
)
_BLOCKED_RE = re.compile(
    r"\b(bloccat\w*|in\s+attesa|ferm[oa]|blocked|on\s+hold|stuck|waiting\s+for)\b",
    re.IGNORECASE,
)
_IN_PROGRESS_RE = re.compile(
    r"\b(sto\s+\w+ndo|in\s+corso|procedo|sto\s+lavorando|working\s+on|in\s+progress|sto\s+facendo)\b",
    re.IGNORECASE,
)
_SUPERSEDE_RE = re.compile(
    r"\b(invece|aggiornament\w*|nuovo\s+valore|cambiat[oa]|sostituit[oa]|ultima\s+versione|"
    r"update[d]?|instead|new\s+value|changed|replaced|superseded|latest\s+version|"
    r"correzione|corretto\s+in)\b",
    re.IGNORECASE,
)
_REVOKE_RE = re.compile(
    r"\b(revocat[oa]|annullat[oa]|cancellat[oa]|revoked|cancell?ed|withdrawn|ritirat[oa])\b",
    re.IGNORECASE,
)
_QUESTION_RE = re.compile(r"\?\s*$|\b(come|quando|dove|chi|perch[eé]|quale|quanti|how|when|where|who|why|which)\b", re.IGNORECASE)


def detect_resolution_signal(text: str) -> bool:
    if not text:
        return False
    if _NEG_RESOLUTION_RE.search(text):
        return False
    return bool(_RESOLUTION_RE.search(text) or _VERIFICATION_RE.search(text))


def detect_verification_signal(text: str) -> bool:
    return bool(text) and not _NEG_RESOLUTION_RE.search(text) and bool(_VERIFICATION_RE.search(text))


def detect_reopen_signal(text: str) -> bool:
    if not text:
        return False
    if _NEG_RESOLUTION_RE.search(text):
        return True
    return bool(_REOPEN_RE.search(text))


def detect_supersession(text: str) -> bool:
    return bool(text) and bool(_SUPERSEDE_RE.search(text) or _REVOKE_RE.search(text))


def detect_revoke_signal(text: str) -> bool:
    return bool(text) and bool(_REVOKE_RE.search(text))


def detect_blocked_signal(text: str) -> bool:
    return bool(text) and bool(_BLOCKED_RE.search(text))


def _is_question_text(text: str) -> bool:
    return bool(text) and bool(_QUESTION_RE.search(text.strip()))


def detect_answer_signal(text: str) -> bool:
    """A later, substantive, non-question utterance answers an open question."""
    cleaned = (text or "").strip()
    if len(cleaned) < 2:
        return False
    return not _is_question_text(cleaned)


def _parse_ts(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.now(timezone.utc)


def detect_stale_state(last_evidence_at: str | None, reference_now: datetime, stale_after_days: int) -> bool:
    if stale_after_days <= 0 or not last_evidence_at:
        return False
    return (reference_now - _parse_ts(last_evidence_at)).days > stale_after_days


# --------------------------------------------------------------------------- #
# Evidence + transition result
# --------------------------------------------------------------------------- #


@dataclass
class Evidence:
    event_id: str
    text: str
    timestamp: str


@dataclass
class LifecycleTransition:
    new_status: str
    reason: str
    evidence_event_ids: list[str] = field(default_factory=list)
    confidence: str = "medium"
    superseded_by: Optional[str] = None
    reopened_by: Optional[str] = None
    last_evidence_at: Optional[str] = None


_ACTIVE_BY_CATEGORY = {
    "task": {"open", "in_progress", "blocked"},
    "issue": {"open", "confirmed", "investigating", "mitigated", "reopened"},
    "decision": {"proposed", "confirmed", "active"},
    "question": {"open", "partially_answered"},
    "information": {"current", "updated"},
}
_CLOSED_BY_CATEGORY = {
    "task": {"completed", "verified", "cancelled", "superseded"},
    "issue": {"resolved", "superseded"},
    "decision": {"superseded", "revoked", "expired"},
    "question": {"answered", "superseded"},
    "information": {"superseded", "historical"},
}
_STALE_STATUS = {
    "task": "stale",
    "issue": "stale",
    "decision": "expired",
    "question": "stale",
    "information": "stale",
}


def is_active_status(category: str, status: str) -> bool:
    return status in _ACTIVE_BY_CATEGORY.get(category, set())


def initial_status(category: LifecycleCategory, text: str) -> str:
    """Baseline status inferred from the item's own text — generic only."""
    if category == "task":
        if detect_verification_signal(text):
            return "verified"
        if detect_resolution_signal(text):
            return "completed"
        if detect_blocked_signal(text):
            return "blocked"
        if _IN_PROGRESS_RE.search(text or ""):
            return "in_progress"
        return "open"
    if category == "issue":
        if detect_resolution_signal(text) and not _NEG_RESOLUTION_RE.search(text or ""):
            return "resolved"
        return "open"
    if category == "decision":
        if detect_revoke_signal(text):
            return "revoked"
        return "confirmed"
    if category == "question":
        return "open"
    return "current"  # information


def _confidence_for(evidence_confidence: str) -> str:
    return evidence_confidence


def _infer_generic(
    category: LifecycleCategory,
    current_status: str,
    evidence: list[Evidence],
    reference_now: datetime,
    stale_after_days: int,
) -> LifecycleTransition | None:
    """Walk evidence chronologically applying generic transitions."""
    status = current_status
    reason = ""
    ev_ids: list[str] = []
    confidence = "medium"
    superseded_by: Optional[str] = None
    reopened_by: Optional[str] = None
    last_evidence_at: Optional[str] = None
    changed = False

    ordered = sorted(evidence, key=lambda e: _parse_ts(e.timestamp))
    for ev in ordered:
        last_evidence_at = ev.timestamp
        text = ev.text or ""

        # Supersession / revocation applies to every category.
        if detect_supersession(text):
            new = "revoked" if (category == "decision" and detect_revoke_signal(text)) else "superseded"
            if status != new:
                status, reason, confidence = new, f"sostituito/aggiornato da evidenza successiva: '{_short(text)}'", "high"
                superseded_by = ev.event_id
                ev_ids = [ev.event_id]
                changed = True
            continue

        if category == "task":
            if detect_verification_signal(text) and status not in {"verified"}:
                status, reason, confidence = "verified", f"verifica esplicita: '{_short(text)}'", "high"
                ev_ids = [ev.event_id]; changed = True
            elif detect_resolution_signal(text) and status not in {"completed", "verified"}:
                status, reason, confidence = "completed", f"completamento: '{_short(text)}'", "high"
                ev_ids = [ev.event_id]; changed = True
            elif detect_reopen_signal(text) and status in {"completed", "verified"}:
                status, reason, confidence = "open", f"riaperto da nuova evidenza: '{_short(text)}'", "high"
                reopened_by = ev.event_id; ev_ids = [ev.event_id]; changed = True
            elif detect_blocked_signal(text) and status in {"open", "in_progress"}:
                status, reason, confidence = "blocked", f"bloccato: '{_short(text)}'", "medium"
                ev_ids = [ev.event_id]; changed = True

        elif category == "issue":
            if detect_reopen_signal(text) and status in {"resolved", "mitigated"}:
                status, reason, confidence = "reopened", f"regressione/anomalia tornata: '{_short(text)}'", "high"
                reopened_by = ev.event_id; ev_ids = [ev.event_id]; changed = True
            elif detect_resolution_signal(text) and status not in {"resolved"}:
                status, reason, confidence = "resolved", f"risoluzione confermata: '{_short(text)}'", "high"
                ev_ids = [ev.event_id]; changed = True

        elif category == "decision":
            # handled mostly by supersession/revoke above
            pass

        elif category == "question":
            if detect_answer_signal(text) and status in {"open", "partially_answered"}:
                status, reason, confidence = "answered", f"risposta coerente successiva: '{_short(text)}'", "medium"
                ev_ids = [ev.event_id]; changed = True

        elif category == "information":
            # superseded handled above; a plain newer info update does not auto-supersede
            pass

    # Temporal decay: still-active items with no fresh decisive evidence go stale.
    if is_active_status(category, status) and detect_stale_state(last_evidence_at, reference_now, stale_after_days):
        stale_status = _STALE_STATUS[category]
        if status != stale_status:
            status = stale_status
            reason = reason or f"nessun aggiornamento da oltre {stale_after_days} giorni"
            confidence = "low" if not changed else confidence
            changed = True

    if not changed and status == current_status:
        return None
    return LifecycleTransition(
        new_status=status,
        reason=reason or "transizione di stato",
        evidence_event_ids=ev_ids,
        confidence=confidence,
        superseded_by=superseded_by,
        reopened_by=reopened_by,
        last_evidence_at=last_evidence_at,
    )


def _short(text: str, limit: int = 80) -> str:
    cleaned = " ".join((text or "").split())
    return cleaned[: limit - 3] + "..." if len(cleaned) > limit else cleaned


# Public per-category wrappers (thin, for explicit testing/readability).
def infer_task_transition(current_status, evidence, reference_now, stale_after_days=DEFAULT_STALE_AFTER_DAYS):
    return _infer_generic("task", current_status, evidence, reference_now, stale_after_days)


def infer_issue_transition(current_status, evidence, reference_now, stale_after_days=DEFAULT_STALE_AFTER_DAYS):
    return _infer_generic("issue", current_status, evidence, reference_now, stale_after_days)


def infer_decision_transition(current_status, evidence, reference_now, stale_after_days=DEFAULT_STALE_AFTER_DAYS):
    return _infer_generic("decision", current_status, evidence, reference_now, stale_after_days)


def infer_question_transition(current_status, evidence, reference_now, stale_after_days=DEFAULT_STALE_AFTER_DAYS):
    return _infer_generic("question", current_status, evidence, reference_now, stale_after_days)


def infer_information_transition(current_status, evidence, reference_now, stale_after_days=DEFAULT_STALE_AFTER_DAYS):
    return _infer_generic("information", current_status, evidence, reference_now, stale_after_days)


def explain_lifecycle_transition(state: LifecycleState) -> str:
    if not state.evidence_event_ids:
        return state.status_reason or f"stato {state.current_status} senza evidenza esplicita"
    return f"{state.current_status} (da {state.previous_status or 'iniziale'}): {state.status_reason} [evidenza: {', '.join(state.evidence_event_ids)}]"


# --------------------------------------------------------------------------- #
# State-level application (incremental-aware)
# --------------------------------------------------------------------------- #


def _event_text(event: OperationalEvent) -> str:
    parts = [event.content or "", event.extracted_text or "", event.media_description or ""]
    meta = event.attachment_metadata or {}
    for key in ("simulated_ocr", "simulated_text", "description"):
        value = str(meta.get(key) or "")
        if value:
            parts.append(value)
    return " ".join(part.strip() for part in parts if part and part.strip())


def _item_category(item: OperationalItem, category: LifecycleCategory) -> LifecycleCategory:
    return category


def _thread_evidence_for_item(
    item: OperationalItem,
    category: LifecycleCategory,
    event_by_id: dict[str, OperationalEvent],
    thread_by_event: dict[str, str],
    thread_by_id: dict[str, OperationalThread],
) -> list[Evidence]:
    source_id = item.source_event_id
    if not source_id:
        return []
    thread_id = thread_by_event.get(source_id)
    if not thread_id:
        source_event = event_by_id.get(source_id)
        thread_id = source_event.thread_id if source_event else None
    if not thread_id:
        return []
    thread = thread_by_id.get(thread_id)
    if thread is None:
        return []
    item_ts = _parse_ts(item.source_timestamp)
    evidence: list[Evidence] = []
    for event_id in thread.related_event_ids:
        if event_id == source_id:
            continue
        event = event_by_id.get(event_id)
        if event is None:
            continue
        if _parse_ts(event.timestamp) <= item_ts:
            continue
        text = _event_text(event)
        if not text:
            continue
        evidence.append(Evidence(event_id=event_id, text=text, timestamp=event.timestamp))
    return evidence


_CATEGORY_FIELDS: list[tuple[LifecycleCategory, str]] = [
    ("task", "tasks"),
    ("issue", "issues"),
    ("decision", "decisions"),
    ("question", "open_questions"),
    ("information", "information"),
]


def apply_lifecycle_transitions(
    state: OperationalState,
    events: list[OperationalEvent],
    threads: Optional[list[OperationalThread]] = None,
    event_thread_map: Optional[dict[str, str]] = None,
    dirty_item_ids: Optional[set[str]] = None,
    reference_now: Optional[datetime] = None,
    stale_after_days: int = DEFAULT_STALE_AFTER_DAYS,
) -> list[LifecycleTransitionRecord]:
    """Update lifecycle for every (or only dirty) operational item in `state`.

    Returns the list of transitions performed this run. Items keep their
    LifecycleState; unchanged items are reused as-is (incremental friendly)."""
    reference_now = reference_now or datetime.now(timezone.utc)
    threads = threads if threads is not None else state.threads
    event_by_id = {event.event_id: event for event in events}
    thread_by_id = {thread.thread_id: thread for thread in threads}
    thread_by_event = dict(event_thread_map or {})
    if not thread_by_event:
        for thread in threads:
            for event_id in thread.related_event_ids:
                thread_by_event.setdefault(event_id, thread.thread_id)

    transitions: list[LifecycleTransitionRecord] = []
    for category, field_name in _CATEGORY_FIELDS:
        for item in getattr(state, field_name):
            if dirty_item_ids is not None and item.id not in dirty_item_ids and item.lifecycle is not None:
                continue  # untouched: reuse existing lifecycle

            evidence = _thread_evidence_for_item(item, category, event_by_id, thread_by_event, thread_by_id)

            if item.lifecycle is None:
                base_status = initial_status(category, item.text)
                item.lifecycle = LifecycleState(
                    category=category,
                    current_status=base_status,
                    status_changed_at=item.source_timestamp or utc_now_iso(),
                    status_reason="stato iniziale dedotto dal testo",
                    confidence=item.confidence,
                    evidence_event_ids=[item.source_event_id] if item.source_event_id else [],
                    last_evidence_at=item.source_timestamp,
                    stale_after_days=stale_after_days,
                    lifecycle_history=[
                        LifecycleHistoryEntry(
                            status=base_status,
                            changed_at=item.source_timestamp or utc_now_iso(),
                            reason="stato iniziale",
                            evidence_event_ids=[item.source_event_id] if item.source_event_id else [],
                        )
                    ],
                )

            lifecycle = item.lifecycle
            lifecycle.stale_after_days = stale_after_days
            transition = _infer_generic(
                category, lifecycle.current_status, evidence, reference_now, stale_after_days
            )
            if transition is None:
                continue
            if transition.new_status == lifecycle.current_status:
                continue

            previous = lifecycle.current_status
            lifecycle.previous_status = previous
            lifecycle.current_status = transition.new_status
            lifecycle.status_changed_at = utc_now_iso()
            lifecycle.status_reason = transition.reason
            lifecycle.confidence = transition.confidence  # type: ignore[assignment]
            if transition.evidence_event_ids:
                lifecycle.evidence_event_ids = transition.evidence_event_ids
            if transition.last_evidence_at:
                lifecycle.last_evidence_at = transition.last_evidence_at
            lifecycle.superseded_by = transition.superseded_by
            lifecycle.reopened_by = transition.reopened_by
            lifecycle.lifecycle_history.append(
                LifecycleHistoryEntry(
                    status=transition.new_status,
                    changed_at=lifecycle.status_changed_at,
                    reason=transition.reason,
                    evidence_event_ids=transition.evidence_event_ids,
                )
            )
            transitions.append(
                LifecycleTransitionRecord(
                    item_id=item.id,
                    category=category,
                    text=item.text,
                    previous_status=previous,
                    new_status=transition.new_status,
                    reason=transition.reason,
                    confidence=transition.confidence,  # type: ignore[arg-type]
                    evidence_event_ids=transition.evidence_event_ids,
                )
            )
    return transitions


# --------------------------------------------------------------------------- #
# Snapshot + delta
# --------------------------------------------------------------------------- #


def _status(item: OperationalItem, category: LifecycleCategory) -> str:
    if item.lifecycle is not None:
        return item.lifecycle.current_status
    return initial_status(category, item.text)


def build_operational_snapshot(
    state: OperationalState,
    transitions: Optional[list[LifecycleTransitionRecord]] = None,
    generated_at: Optional[str] = None,
) -> OperationalLifecycleSnapshot:
    transitions = transitions or []
    snapshot = OperationalLifecycleSnapshot(
        project_id=state.project_id or "",
        generated_at=generated_at or utc_now_iso(),
        transitions=list(transitions),
    )
    for task in state.tasks:
        status = _status(task, "task")
        (snapshot.active_tasks if is_active_status("task", status) else snapshot.completed_tasks).append(task.text)
        if status == "stale":
            snapshot.stale_items.append(f"[task] {task.text}")
    for issue in state.issues:
        status = _status(issue, "issue")
        if status == "resolved":
            snapshot.resolved_issues.append(issue.text)
        elif status == "stale":
            snapshot.stale_items.append(f"[issue] {issue.text}")
        else:
            snapshot.active_issues.append(issue.text)
            if issue.confidence == "high" or status in {"confirmed", "reopened"}:
                snapshot.high_attention_items.append(f"[issue] {issue.text}")
    for decision in state.decisions:
        status = _status(decision, "decision")
        if status in {"superseded", "revoked", "expired"}:
            snapshot.decisions_superseded.append(decision.text)
        else:
            snapshot.decisions_active.append(decision.text)
    for question in state.open_questions:
        status = _status(question, "question")
        if status in {"answered", "superseded"}:
            snapshot.answered_questions.append(question.text)
        elif status == "stale":
            snapshot.stale_items.append(f"[question] {question.text}")
        else:
            snapshot.open_questions.append(question.text)
    for info in state.information:
        status = _status(info, "information")
        if status == "stale":
            snapshot.stale_items.append(f"[information] {info.text}")

    delta = OperationalLifecycleDelta()
    for record in transitions:
        label = f"[{record.category}] {record.text}"
        if record.new_status in {"completed", "verified"}:
            delta.newly_completed.append(label)
        elif record.new_status == "resolved":
            delta.newly_resolved.append(label)
        elif record.new_status == "reopened" or (record.new_status == "open" and record.previous_status in {"completed", "verified"}):
            delta.reopened.append(label)
        elif record.new_status in {"superseded", "revoked", "expired"}:
            delta.superseded.append(label)
        elif record.new_status == "stale":
            delta.newly_stale.append(label)
        elif record.new_status in {"open", "confirmed"}:
            delta.newly_opened.append(label)
        snapshot.changed_since_last_snapshot.append(label)
    delta.unchanged_active = [
        text
        for text in [*snapshot.active_tasks, *snapshot.active_issues]
        if f"[task] {text}" not in snapshot.changed_since_last_snapshot
        and f"[issue] {text}" not in snapshot.changed_since_last_snapshot
    ]
    snapshot.delta = delta
    return snapshot
