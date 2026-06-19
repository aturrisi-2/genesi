"""FASE 5 — Query & Retrieval Layer.

Answer operational questions over the lifecycle state with structured,
deterministic queries (no generative AI). Every answer item carries its
evidence_event_ids and a reason, so results stay explainable and traceable.

Domain-agnostic: queries operate on generic lifecycle statuses and item
metadata only — no profession/site/platform vocabulary, no hardcoded tokens.
The natural-language layer is a thin keyword/regex intent router (IT + EN) that
dispatches to the structured queries; it never invents content."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Callable

from core.operational_memory.lifecycle_engine import initial_status, is_active_status
from core.operational_memory.models import (
    LifecycleCategory,
    OperationalDigest,
    OperationalItem,
    OperationalState,
    QueryAnswerItem,
    QueryResult,
    utc_now_iso,
)


_CATEGORY_FIELDS: list[tuple[LifecycleCategory, str]] = [
    ("task", "tasks"),
    ("issue", "issues"),
    ("decision", "decisions"),
    ("question", "open_questions"),
    ("information", "information"),
]


def _status_of(item: OperationalItem, category: LifecycleCategory) -> str:
    if item.lifecycle is not None:
        return item.lifecycle.current_status
    return initial_status(category, item.text)


def _answer_item(item: OperationalItem, category: LifecycleCategory) -> QueryAnswerItem:
    lifecycle = item.lifecycle
    status = _status_of(item, category)
    evidence = list(lifecycle.evidence_event_ids) if lifecycle else (
        [item.source_event_id] if item.source_event_id else []
    )
    reason = lifecycle.status_reason if lifecycle and lifecycle.status_reason else "stato corrente"
    return QueryAnswerItem(
        item_id=item.id,
        category=category,
        status=status,
        text=item.text,
        confidence=lifecycle.confidence if lifecycle else item.confidence,
        evidence_event_ids=evidence,
        reason=reason,
    )


def _collect(state: OperationalState, category: LifecycleCategory, predicate: Callable[[str], bool]) -> list[QueryAnswerItem]:
    field_name = dict(_CATEGORY_FIELDS)[category]
    out: list[QueryAnswerItem] = []
    for item in getattr(state, field_name):
        if predicate(_status_of(item, category)):
            out.append(_answer_item(item, category))
    return out


# --------------------------------------------------------------------------- #
# Structured queries
# --------------------------------------------------------------------------- #


def open_tasks(state: OperationalState) -> list[QueryAnswerItem]:
    return _collect(state, "task", lambda s: is_active_status("task", s))


def open_issues(state: OperationalState) -> list[QueryAnswerItem]:
    return _collect(state, "issue", lambda s: is_active_status("issue", s))


def resolved_issues(state: OperationalState) -> list[QueryAnswerItem]:
    return _collect(state, "issue", lambda s: s == "resolved")


def active_decisions(state: OperationalState) -> list[QueryAnswerItem]:
    return _collect(state, "decision", lambda s: is_active_status("decision", s))


def unanswered_questions(state: OperationalState) -> list[QueryAnswerItem]:
    return _collect(state, "question", lambda s: s in {"open", "partially_answered"})


def superseded_items(state: OperationalState) -> list[QueryAnswerItem]:
    out: list[QueryAnswerItem] = []
    for category, _field in _CATEGORY_FIELDS:
        out.extend(_collect(state, category, lambda s: s in {"superseded", "revoked", "cancelled", "expired"}))
    return out


def attention_items(state: OperationalState) -> list[QueryAnswerItem]:
    """Active items that warrant attention: reopened, mitigated-but-open, or
    high-confidence active issues; plus aging items flagged by the snapshot."""
    out: list[QueryAnswerItem] = []
    aging_texts: set[str] = set()
    snapshot = state.lifecycle_snapshot
    if snapshot and snapshot.snapshot_delta:
        for label in snapshot.snapshot_delta.aging_attention_items:
            aging_texts.add(label)
    for category, field_name in _CATEGORY_FIELDS:
        for item in getattr(state, field_name):
            status = _status_of(item, category)
            if not is_active_status(category, status):
                continue
            flag = (
                status in {"reopened", "mitigated", "blocked", "partially_answered"}
                or (category == "issue" and item.confidence == "high")
                or f"[{category}] {item.text}" in aging_texts
            )
            if flag:
                out.append(_answer_item(item, category))
    return out


def changed_since(state: OperationalState) -> list[QueryAnswerItem]:
    snapshot = state.lifecycle_snapshot
    if snapshot is None or snapshot.snapshot_delta is None:
        return []
    delta = snapshot.snapshot_delta
    out: list[QueryAnswerItem] = []
    seen: set[str] = set()

    def _add(label: str, status: str) -> None:
        if label in seen:
            return
        seen.add(label)
        out.append(QueryAnswerItem(text=label, status=status, reason=f"cambiato dallo snapshot precedente ({status})"))

    for label in delta.newly_completed:
        _add(label, "completed")
    for label in delta.newly_resolved:
        _add(label, "resolved")
    for label in delta.newly_superseded:
        _add(label, "superseded")
    for label in delta.reopened_items:
        _add(label, "reopened")
    for label in delta.newly_opened:
        _add(label, "opened")
    for label in delta.newly_stale:
        _add(label, "stale")
    return out


def build_digest(state: OperationalState) -> OperationalDigest:
    ot = open_tasks(state)
    oi = open_issues(state)
    ri = resolved_issues(state)
    ad = active_decisions(state)
    uq = unanswered_questions(state)
    att = attention_items(state)
    changes = [item.text for item in changed_since(state)]
    headline = (
        f"{len(ot)} task aperti, {len(oi)} problemi aperti, {len(ri)} risolti, "
        f"{len(ad)} decisioni attive, {len(uq)} domande aperte, {len(att)} elementi da attenzionare"
    )
    return OperationalDigest(
        project_id=state.project_id or "",
        generated_at=utc_now_iso(),
        headline=headline,
        open_tasks=ot,
        open_issues=oi,
        resolved_issues=ri,
        active_decisions=ad,
        unanswered_questions=uq,
        attention_items=att,
        recent_changes=changes[:50],
    )


# --------------------------------------------------------------------------- #
# Natural-language intent routing (keyword/regex, no LLM)
# --------------------------------------------------------------------------- #

# Ordered: more specific intents first. Patterns are generic IT + EN.
_INTENT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("digest", re.compile(r"\b(digest|riass\w*|sommario|panoramica|summary|overview|stato\s+(del\s+)?(progetto|chat|lavori)|status)\b", re.IGNORECASE)),
    ("changed", re.compile(r"\b(cambiat\w*|cambia|da\s+ieri|novit[aà]|aggiornament\w*|changed|since\s+yesterday|what'?s\s+new|differenz\w*)\b", re.IGNORECASE)),
    ("resolved_issues", re.compile(r"\b(risolt\w*|resolved|fixed|chius\w*\s+problem\w*|problem\w*\s+chius\w*)\b", re.IGNORECASE)),
    ("superseded", re.compile(r"\b(superat\w*|sostituit\w*|superseded|revocat\w*|obsolet\w*|annullat\w*)\b", re.IGNORECASE)),
    ("unanswered", re.compile(r"\b(domand\w*|question\w*|senza\s+risposta|unanswered|da\s+rispondere|open\s+question\w*)\b", re.IGNORECASE)),
    ("attention", re.compile(r"\b(attenzion\w*|attention|urgent\w*|critic\w*|prioritar\w*|richiede\w*|da\s+attenzionare)\b", re.IGNORECASE)),
    ("active_decisions", re.compile(r"\b(decision\w*|decis\w*|deciso|decided)\b", re.IGNORECASE)),
    ("open_issues", re.compile(r"\b(problem\w*\s+apert\w*|issue\w*\s+apert\w*|open\s+issue\w*|problem\w*|guast\w*|anomal\w*|bug)\b", re.IGNORECASE)),
    ("open_tasks", re.compile(r"\b(da\s+fare|resta\w*|riman\w*|to\s*do|todo|task|attivit[aà]|pending|cosa\s+manca|cosa\s+resta)\b", re.IGNORECASE)),
]

_INTENT_DISPATCH: dict[str, Callable[[OperationalState], list[QueryAnswerItem]]] = {
    "open_tasks": open_tasks,
    "open_issues": open_issues,
    "resolved_issues": resolved_issues,
    "active_decisions": active_decisions,
    "unanswered": unanswered_questions,
    "superseded": superseded_items,
    "attention": attention_items,
    "changed": changed_since,
}

_INTENT_SUMMARY = {
    "open_tasks": "task ancora aperti",
    "open_issues": "problemi ancora aperti",
    "resolved_issues": "problemi risolti",
    "active_decisions": "decisioni attive",
    "unanswered": "domande senza risposta",
    "superseded": "elementi superati o sostituiti",
    "attention": "elementi che richiedono attenzione",
    "changed": "cambiamenti dallo snapshot precedente",
}


def classify_query_intent(text: str) -> str:
    cleaned = (text or "").strip()
    if not cleaned:
        return "unknown"
    for intent, pattern in _INTENT_PATTERNS:
        if pattern.search(cleaned):
            return intent
    return "unknown"


def answer_query(state: OperationalState, text: str) -> QueryResult:
    intent = classify_query_intent(text)
    if intent == "digest":
        digest = build_digest(state)
        return QueryResult(query=text, intent="digest", summary=digest.headline, count=0, items=[])
    if intent == "unknown" or intent not in _INTENT_DISPATCH:
        return QueryResult(
            query=text,
            intent="unknown",
            summary="Domanda non riconosciuta. Prova: cosa resta da fare, quali problemi aperti, "
                    "cosa risolto, decisioni attive, cosa cambiato, domande aperte, cosa superato, "
                    "cosa richiede attenzione, digest.",
            count=0,
            items=[],
        )
    items = _INTENT_DISPATCH[intent](state)
    return QueryResult(
        query=text,
        intent=intent,
        summary=f"{len(items)} {_INTENT_SUMMARY.get(intent, intent)}",
        count=len(items),
        items=items,
    )
