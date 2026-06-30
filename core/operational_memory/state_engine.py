from __future__ import annotations

import re
from typing import TypeVar

from core.log import log
from core.operational_memory.extractor import extract_state
from core.operational_memory.models import OperationalEvent, OperationalItem, OperationalState, ReviewItem, utc_now_iso
from core.operational_memory.quality import classify_ingest
from core.operational_memory.state_store import load_state, save_state


T = TypeVar("T", bound=OperationalItem)

# OperationalState list field → category name used by classify_ingest.
_CATEGORY = {
    "tasks": "task", "issues": "issue", "decisions": "decision",
    "information": "information", "open_questions": "question",
}


def _triage_incoming(items: list[T], category: str, project_id: str, review: list[ReviewItem]) -> list[T]:
    """Keep only `accepted` items; route `needs_review` to the queue; drop `ignored`.
    Applied to INCOMING items only — existing state is never retroactively filtered."""
    kept: list[T] = []
    for it in items:
        decision, reason = classify_ingest(it, category)
        if decision == "accepted":
            kept.append(it)
        elif decision == "needs_review":
            review.append(ReviewItem(
                proposed_type=category, reason=reason,
                confidence=getattr(it, "confidence", "low"),
                evidence_event_id=(it.source_event_id or ""),
                timestamp=(it.source_timestamp or utc_now_iso()),
                snippet=(it.text or "")[:200],
                source=(it.source or ""), project_id=project_id or "",
            ))
        # ignored → dropped
    return kept


def _dedup_review(items: list[ReviewItem]) -> list[ReviewItem]:
    seen: set[tuple[str, str]] = set()
    out: list[ReviewItem] = []
    for r in items:
        key = (r.snippet.strip().lower(), r.reason)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def _item_key(item: OperationalItem) -> tuple[str, str]:
    return (item.text.strip().lower(), item.source.strip().lower())


def _merge_items(existing: list[T], incoming: list[T]) -> list[T]:
    merged = list(existing)
    seen = {_item_key(item): item for item in merged}
    for item in incoming:
        key = _item_key(item)
        if key in seen:
            current = seen[key]
            if getattr(item, "status", None) == "completed" and hasattr(current, "status"):
                current.status = "completed"
            continue
        merged.append(item)
        seen[key] = item
    return merged


# --- Issue dedup by technical object (G5) ---------------------------------
# Several messages about the SAME technical object (e.g. "Pompa P1") must
# evolve ONE issue, not spawn duplicates. Object identity is keyed on an
# *identifier* token (one carrying a digit, e.g. p1, dn32, fg16) plus a shared
# noun, so "Pompa P1" != "Pompa P2" and generic words ("quadro", "materiale")
# without an identifier never merge. Fail-safe: when in doubt, do NOT merge.
_OBJ_STOP = {
    "non", "che", "del", "della", "dello", "dei", "delle", "lo", "la", "le",
    "gli", "un", "una", "uno", "per", "con", "ma", "da", "si", "in", "al",
    "alla", "allo", "the", "and", "ancora", "stato", "stata",
}


def _object_signature(text: str) -> tuple[frozenset[str], frozenset[str]]:
    """(identifier-tokens with a digit, plain noun tokens) for a piece of text."""
    toks = [
        t for t in re.findall(r"[a-zà-ÿ0-9]+", (text or "").lower())
        if (len(t) >= 3 or any(c.isdigit() for c in t)) and t not in _OBJ_STOP
    ]
    ids = frozenset(t for t in toks if any(c.isdigit() for c in t))
    nouns = frozenset(t for t in toks if not any(c.isdigit() for c in t))
    return ids, nouns


def _same_strong_object(a_text: str, b_text: str) -> bool:
    ai, an = _object_signature(a_text)
    bi, bn = _object_signature(b_text)
    if not ai or ai != bi:          # need a non-empty, identical identifier set
        return False
    return bool(an & bn)            # and at least one shared object noun


def _fold_issue_evidence(target: OperationalItem, incoming: OperationalItem) -> None:
    """Attach the incoming issue's evidence/event to the existing one — keep the
    history, never lose events. Status transitions stay with the lifecycle engine."""
    lc = getattr(target, "lifecycle", None)
    src = getattr(incoming, "source_event_id", None)
    if lc is not None and src:
        ev = getattr(lc, "evidence_event_ids", None)
        if isinstance(ev, list) and src not in ev:
            ev.append(src)


def _merge_issues(existing: list[T], incoming: list[T]) -> list[T]:
    """Like _merge_items but folds incoming issues onto an existing issue that
    refers to the same strong technical object (G5)."""
    merged = list(existing)
    seen = {_item_key(item): item for item in merged}
    for item in incoming:
        folded = False
        for ex in merged:
            if _same_strong_object(getattr(ex, "text", ""), getattr(item, "text", "")):
                _fold_issue_evidence(ex, item)
                folded = True
                break
        if folded:
            continue
        key = _item_key(item)
        if key in seen:
            continue
        merged.append(item)
        seen[key] = item
    return merged


def merge_state(existing: OperationalState, incoming: OperationalState) -> OperationalState:
    pid = existing.project_id or ""
    review = list(existing.review_queue)
    # Triage INCOMING items: only accepted reach the active lists; needs_review →
    # queue; ignored dropped. Existing accepted items are preserved untouched.
    inc_tasks = _triage_incoming(incoming.tasks, "task", pid, review)
    inc_issues = _triage_incoming(incoming.issues, "issue", pid, review)
    inc_decisions = _triage_incoming(incoming.decisions, "decision", pid, review)
    inc_information = _triage_incoming(incoming.information, "information", pid, review)
    inc_questions = _triage_incoming(incoming.open_questions, "question", pid, review)
    return OperationalState(
        project_id=existing.project_id,
        updated_at=utc_now_iso(),
        decisions=_merge_items(existing.decisions, inc_decisions),
        tasks=_merge_items(existing.tasks, inc_tasks),
        issues=_merge_issues(existing.issues, inc_issues),
        information=_merge_items(existing.information, inc_information),
        open_questions=_merge_items(existing.open_questions, inc_questions),
        review_queue=_dedup_review(review),
        threads=list(existing.threads),
        macro_threads=list(existing.macro_threads),
        thread_relation_candidates=list(existing.thread_relation_candidates),
        adaptive_chat_profile=existing.adaptive_chat_profile,
        domain_stats=dict(existing.domain_stats),
        lifecycle_snapshot=existing.lifecycle_snapshot,
    )


async def get_project_state(project_id: str) -> OperationalState:
    return await load_state(project_id)


async def ingest_messages(
    project_id: str,
    messages: list[str],
    source_event: OperationalEvent | None = None,
    nearby_messages: list[str] | None = None,
) -> OperationalState:
    existing = await load_state(project_id)
    incoming = await extract_state(messages, source_event=source_event, nearby_messages=nearby_messages)
    merged = merge_state(existing, incoming)
    saved = await save_state(project_id, merged)
    log(
        "OPERATIONAL_MEMORY_STATE_UPDATED",
        project_id=project_id,
        decisions=len(saved.decisions),
        tasks=len(saved.tasks),
        issues=len(saved.issues),
        information=len(saved.information),
        open_questions=len(saved.open_questions),
    )
    return saved
