from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone

from core.operational_memory.chat_profile_engine import build_adaptive_chat_profile
from core.operational_memory.models import (
    AdaptiveChatProfile,
    GroupingConfidence,
    MacroRelation,
    OperationalEvent,
    OperationalMacroThread,
    OperationalThread,
)
from core.operational_memory.workflow_engine import infer_workflow_patterns


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


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


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _norm(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _macro_id(project_id: str, tags: list[str]) -> str:
    seed = "|".join(_norm(tag) for tag in tags[:6]) or "macro"
    digest = hashlib.sha1(f"{project_id}:{seed}".encode("utf-8")).hexdigest()[:12]
    return f"macro_{digest}"


def _profile_terms(profile: AdaptiveChatProfile, terms: list[str], source: str) -> set[str]:
    available = {_norm(term) for term in terms}
    return {_norm(term) for term in getattr(profile, source) if _norm(term) in available}


def _thread_text(thread: OperationalThread) -> str:
    return " ".join([thread.title, *thread.context_tags, *thread.related_tasks, *thread.related_issues, *thread.unresolved_questions])


def _thread_terms(thread: OperationalThread, profile: AdaptiveChatProfile) -> list[str]:
    text = _norm(_thread_text(thread))
    terms = []
    for term in [*profile.specific_terms, *profile.topic_candidates, *profile.recurring_actions, *profile.recurring_problem_terms]:
        normalized = _norm(term)
        if normalized and normalized in text and normalized not in {_norm(value) for value in profile.generic_terms}:
            terms.append(term)
    for tag in thread.context_tags:
        normalized = _norm(tag)
        if normalized not in {_norm(value) for value in profile.generic_terms}:
            terms.append(tag)
    return _unique(terms)


def _thread_canonical_terms(thread: OperationalThread, profile: AdaptiveChatProfile) -> list[str]:
    text = _norm(_thread_text(thread))
    labels: list[str] = []
    for canonical in profile.canonical_terms:
        if canonical.boundary_confidence == "low":
            continue
        label = _norm(canonical.label)
        sources = [_norm(term) for term in canonical.source_terms]
        if label and label in text:
            labels.append(canonical.label)
            continue
        if any(source and source in text for source in sources):
            labels.append(canonical.label)
            continue
        head = _norm(canonical.head_entity or "")
        action = _norm(canonical.action_or_problem or "")
        modifiers = [_norm(modifier) for modifier in canonical.context_modifiers]
        has_action = bool(action and action in text)
        has_anchor = bool(head and head in text) or len([modifier for modifier in modifiers if modifier and modifier in text]) >= 1
        if has_action and has_anchor:
            labels.append(canonical.label)
            continue
        if not action:
            label_parts = [part.strip() for part in label.split("/") if part.strip()]
            label_hits = len([part for part in label_parts if part and part in text])
            if label_hits >= 2:
                labels.append(canonical.label)
    return _unique(labels)


def detect_work_package(thread: OperationalThread, profile: AdaptiveChatProfile | None = None) -> list[str]:
    if profile is None:
        profile = build_adaptive_chat_profile(thread.project_id, [], [thread])
    terms = _thread_terms(thread, profile)
    action_terms = _profile_terms(profile, terms, "recurring_actions")
    problem_terms = _profile_terms(profile, terms, "recurring_problem_terms")
    topic_terms = _profile_terms(profile, terms, "topic_candidates")
    return _unique([*action_terms, *problem_terms, *topic_terms])


def _shared_canonical_terms(left: OperationalThread, right: OperationalThread, profile: AdaptiveChatProfile) -> set[str]:
    left_terms = {_norm(term) for term in _thread_canonical_terms(left, profile)}
    right_terms = {_norm(term) for term in _thread_canonical_terms(right, profile)}
    return left_terms & right_terms


def _canonical_by_label(profile: AdaptiveChatProfile) -> dict[str, object]:
    return {_norm(canonical.label): canonical for canonical in profile.canonical_terms}


def _strong_shared_canonical_terms(left: OperationalThread, right: OperationalThread, profile: AdaptiveChatProfile) -> set[str]:
    canonical_by_label = _canonical_by_label(profile)
    return {
        term
        for term in _shared_canonical_terms(left, right, profile)
        if getattr(canonical_by_label.get(term), "confidence", "low") in {"medium", "high"}
        and getattr(canonical_by_label.get(term), "boundary_confidence", "low") in {"medium", "high"}
    }


def _shared_specific_terms(left: OperationalThread, right: OperationalThread, profile: AdaptiveChatProfile) -> set[str]:
    left_terms = {_norm(term) for term in _thread_terms(left, profile)}
    right_terms = {_norm(term) for term in _thread_terms(right, profile)}
    generic = {_norm(term) for term in profile.generic_terms}
    specific = {_norm(term) for term in profile.specific_terms}
    shared = (left_terms & right_terms) - generic
    return {term for term in shared if term in specific or " " in term or any(char.isdigit() for char in term)}


def _shared_topic_terms(left: OperationalThread, right: OperationalThread, profile: AdaptiveChatProfile) -> set[str]:
    left_terms = {_norm(term) for term in _thread_terms(left, profile)}
    right_terms = {_norm(term) for term in _thread_terms(right, profile)}
    topics = {_norm(term) for term in profile.topic_candidates}
    generic = {_norm(term) for term in profile.generic_terms}
    return (left_terms & right_terms & topics) - generic


def _shared_workflow_terms(left: OperationalThread, right: OperationalThread, profile: AdaptiveChatProfile) -> set[str]:
    left_terms = {_norm(term) for term in _thread_terms(left, profile)}
    right_terms = {_norm(term) for term in _thread_terms(right, profile)}
    workflow = {_norm(term) for term in [*profile.recurring_actions, *profile.recurring_problem_terms, *profile.recurring_completion_terms]}
    generic = {_norm(term) for term in profile.generic_terms}
    return (left_terms & right_terms & workflow) - generic


def _relation_for_threads(left: OperationalThread, right: OperationalThread, profile: AdaptiveChatProfile) -> MacroRelation | None:
    if _strong_shared_canonical_terms(left, right, profile):
        return "same_work_package"
    if _shared_specific_terms(left, right, profile):
        return "same_system"
    if _shared_topic_terms(left, right, profile):
        return "same_work_package"
    if _shared_workflow_terms(left, right, profile):
        return "same_component_family"
    return None


def calculate_macro_similarity(
    left: OperationalThread,
    right: OperationalThread,
    profile: AdaptiveChatProfile | None = None,
) -> float:
    if profile is None:
        profile = build_adaptive_chat_profile(left.project_id, [], [left, right])
    score = 0.0
    canonical_overlap = _strong_shared_canonical_terms(left, right, profile)
    specific_overlap = _shared_specific_terms(left, right, profile)
    topic_overlap = _shared_topic_terms(left, right, profile)
    workflow_overlap = _shared_workflow_terms(left, right, profile)
    if canonical_overlap:
        score += 0.70
    if len(canonical_overlap) >= 2:
        score += 0.15
    if not canonical_overlap:
        return 0.0
    if specific_overlap:
        score += 0.10
    if len(specific_overlap) >= 2:
        score += 0.05
    if topic_overlap:
        score += 0.05
    if workflow_overlap and (specific_overlap or topic_overlap):
        score += 0.05
    return min(score, 1.0)


def calculate_macro_confidence(threads: list[OperationalThread], profile: AdaptiveChatProfile | None = None) -> GroupingConfidence:
    if len(threads) >= 3:
        return "high"
    if len(threads) == 2:
        return "medium"
    return "low"


def _group_common_canonical_terms(group: list[OperationalThread], profile: AdaptiveChatProfile) -> set[str]:
    if not group:
        return set()
    common = {_norm(term) for term in _thread_canonical_terms(group[0], profile)}
    for thread in group[1:]:
        common &= {_norm(term) for term in _thread_canonical_terms(thread, profile)}
    canonical_by_label = _canonical_by_label(profile)
    return {
        term
        for term in common
        if getattr(canonical_by_label.get(term), "boundary_confidence", "low") in {"medium", "high"}
    }


def calculate_macro_heterogeneity(child_threads: list[OperationalThread], profile: AdaptiveChatProfile) -> float:
    if len(child_threads) <= 1:
        return 0.0
    canonical_sets = [{_norm(term) for term in _thread_canonical_terms(thread, profile)} for thread in child_threads]
    union = set().union(*canonical_sets) if canonical_sets else set()
    common = set(canonical_sets[0]) if canonical_sets else set()
    for terms in canonical_sets[1:]:
        common &= terms
    canonical_diversity = 0.0 if not union else 1.0 - (len(common) / len(union))
    domain_diversity = len({thread.primary_domain for thread in child_threads}) / max(1, len(child_threads))
    context_diversity = len({_norm(tag) for thread in child_threads for tag in thread.context_tags}) / max(1, len(child_threads) * 4)
    score = (canonical_diversity * 0.55) + (domain_diversity * 0.25) + (context_diversity * 0.20)
    if common:
        score *= 0.65
    return round(min(1.0, score), 4)


def validate_macro_boundary(child_threads: list[OperationalThread], profile: AdaptiveChatProfile) -> dict[str, object]:
    if len(child_threads) < 2:
        return {"confidence": "low", "heterogeneity": 1.0, "reasons": ["meno di due sottothread"]}
    common_canonical = _group_common_canonical_terms(child_threads, profile)
    heterogeneity = calculate_macro_heterogeneity(child_threads, profile)
    reasons: list[str] = []
    score = 0.25
    if common_canonical:
        score += 0.45
        reasons.append("canonical term forte condiviso dal gruppo")
    else:
        reasons.append("nessun canonical term comune a tutti i sottothread")
    if heterogeneity <= 0.35:
        score += 0.25
    elif heterogeneity <= 0.55:
        score += 0.10
        reasons.append("eterogeneita moderata")
    else:
        score -= 0.30
        reasons.append("eterogeneita macro elevata")
    if len(child_threads) > 6:
        score -= 0.15
        reasons.append("macro con molti sottothread")
    score = max(0.0, min(1.0, score))
    if score >= 0.75:
        confidence: GroupingConfidence = "high"
    elif score >= 0.55:
        confidence = "medium"
    else:
        confidence = "low"
    return {"confidence": confidence, "heterogeneity": heterogeneity, "reasons": reasons}


def calculate_macro_adaptive_patterns(child_threads: list[OperationalThread], profile: AdaptiveChatProfile) -> list[str]:
    patterns = []
    for left_index, left in enumerate(child_threads):
        for right in child_threads[left_index + 1:]:
            for term in sorted(_strong_shared_canonical_terms(left, right, profile)):
                patterns.append(f"termine canonico condiviso: {term}")
            for term in sorted(_shared_specific_terms(left, right, profile)):
                patterns.append(f"termine specifico condiviso: {term}")
            for term in sorted(_shared_topic_terms(left, right, profile)):
                patterns.append(f"topic ricorrente condiviso: {term}")
            for term in sorted(_shared_workflow_terms(left, right, profile)):
                patterns.append(f"segnale workflow condiviso: {term}")
    return _unique(patterns)[:12]


def _macro_title(child_threads: list[OperationalThread], profile: AdaptiveChatProfile) -> str:
    canonical_terms = []
    for left_index, left in enumerate(child_threads):
        for right in child_threads[left_index + 1:]:
            canonical_terms.extend(sorted(_strong_shared_canonical_terms(left, right, profile)))
    readable_canonical = _unique(canonical_terms)
    if readable_canonical:
        return readable_canonical[0]
    shared_terms = []
    for left_index, left in enumerate(child_threads):
        for right in child_threads[left_index + 1:]:
            shared_terms.extend(sorted(_shared_specific_terms(left, right, profile)))
            shared_terms.extend(sorted(_shared_topic_terms(left, right, profile)))
    readable = _unique(shared_terms)
    if readable:
        return " / ".join(term for term in readable[:4])
    context = _unique([tag for thread in child_threads for tag in _thread_terms(thread, profile)])
    return " / ".join(context[:4]) if context else "Macro-thread operativo"


def summarize_macro_thread(macro: OperationalMacroThread, child_threads: list[OperationalThread]) -> str:
    open_count = len([thread for thread in child_threads if thread.status in {"open", "in_progress", "waiting", "stale"}])
    resolved_count = len([thread for thread in child_threads if thread.status == "resolved"])
    return (
        f"{macro.title}: {len(child_threads)} sottothread collegati, "
        f"{open_count} aperti/stale, {resolved_count} risolti."
    )


def _status_for_macro(child_threads: list[OperationalThread]) -> str:
    if any(thread.status in {"open", "in_progress", "waiting"} for thread in child_threads):
        return "open"
    if any(thread.status == "stale" for thread in child_threads):
        return "stale"
    return "resolved"


def _macro_from_threads(
    project_id: str,
    child_threads: list[OperationalThread],
    profile: AdaptiveChatProfile,
) -> OperationalMacroThread:
    context_tags = _unique(
        [
            tag
            for thread in child_threads
            for tag in [*_thread_canonical_terms(thread, profile), *_thread_terms(thread, profile)]
        ]
    )
    started_at = min(child_threads, key=lambda thread: _parse_timestamp(thread.started_at)).started_at
    last_updated_at = max(child_threads, key=lambda thread: _parse_timestamp(thread.last_updated_at)).last_updated_at
    patterns = calculate_macro_adaptive_patterns(child_threads, profile)
    boundary = validate_macro_boundary(child_threads, profile)
    ignored = [term for term in profile.generic_terms if any(_norm(term) in _norm(_thread_text(thread)) for thread in child_threads)]
    macro = OperationalMacroThread(
        macro_thread_id=_macro_id(project_id, context_tags),
        project_id=project_id,
        title=_macro_title(child_threads, profile),
        status=_status_for_macro(child_threads),
        started_at=started_at,
        last_updated_at=last_updated_at,
        context_tags=context_tags,
        child_thread_ids=[thread.thread_id for thread in child_threads],
        related_event_ids=_unique([event_id for thread in child_threads for event_id in thread.related_event_ids]),
        confidence=calculate_macro_confidence(child_threads, profile),
        open_items_count=sum(len(thread.related_tasks) + len(thread.unresolved_questions) for thread in child_threads if thread.status != "resolved"),
        critical_items_count=len([thread for thread in child_threads if thread.project_impact_score >= 80]),
        creation_reason="macro-thread creato da termini canonici del profilo adattivo",
        adaptive_patterns=patterns,
        ignored_generic_terms=_unique(ignored)[:10],
        boundary_confidence=boundary["confidence"],  # type: ignore[arg-type]
        split_recommendation=(
            "dividere o lasciare thread non assegnati"
            if boundary["confidence"] == "low"
            else None
        ),
        macro_boundary_reasons=list(boundary["reasons"]),
    )
    macro.summary = summarize_macro_thread(macro, child_threads)
    return macro


def assign_thread_to_macro(
    thread: OperationalThread,
    macro_threads: list[OperationalMacroThread],
    profile: AdaptiveChatProfile | None = None,
) -> OperationalMacroThread | None:
    if profile is None:
        profile = build_adaptive_chat_profile(thread.project_id, [], [thread])
    best_macro = None
    best_score = 0.0
    for macro in macro_threads:
        pseudo = OperationalThread(
            thread_id=macro.macro_thread_id,
            project_id=macro.project_id,
            title=macro.title,
            started_at=macro.started_at,
            last_updated_at=macro.last_updated_at,
            context_tags=macro.context_tags,
        )
        score = calculate_macro_similarity(thread, pseudo, profile)
        if score > best_score:
            best_macro = macro
            best_score = score
    return best_macro if best_score >= 0.55 else None


def _profile_events_from_threads(project_id: str, threads: list[OperationalThread]) -> list[OperationalEvent]:
    return [
        OperationalEvent(
            event_id=f"profile_{thread.thread_id}",
            project_id=project_id,
            source="thread-summary",
            sender="",
            timestamp=thread.last_updated_at,
            content=_thread_text(thread),
            processed_status="processed",
        )
        for thread in threads
    ]


def build_macro_threads(
    project_id: str,
    threads: list[OperationalThread],
    events: list[OperationalEvent] | None = None,
    profile: AdaptiveChatProfile | None = None,
) -> list[OperationalMacroThread]:
    candidates = [thread for thread in threads if thread.related_event_ids and thread.project_impact_score >= 50]
    profile = profile or build_adaptive_chat_profile(project_id, events or _profile_events_from_threads(project_id, candidates), candidates)
    workflow_patterns, _workflow_confidence = infer_workflow_patterns(events or [], profile)
    profile.workflow_patterns = workflow_patterns or profile.workflow_patterns
    groups: list[list[OperationalThread]] = []

    for thread in candidates:
        matched_group = None
        best_score = 0.0
        for group in groups:
            score = max(calculate_macro_similarity(thread, existing, profile) for existing in group)
            prospective_common = _group_common_canonical_terms([*group, thread], profile)
            if not prospective_common:
                continue
            if score > best_score:
                best_score = score
                matched_group = group
        if matched_group is not None and best_score >= 0.70:
            matched_group.append(thread)
        else:
            groups.append([thread])

    macro_threads = []
    for group in groups:
        if len(group) < 2:
            continue
        boundary = validate_macro_boundary(group, profile)
        if boundary["confidence"] == "low":
            continue
        macro_threads.append(_macro_from_threads(project_id, group, profile))
    macro_by_child: dict[str, OperationalMacroThread] = {}
    for macro in macro_threads:
        for child_id in macro.child_thread_ids:
            macro_by_child[child_id] = macro

    for thread in threads:
        macro = macro_by_child.get(thread.thread_id)
        if macro is None:
            thread.macro_thread_id = None
            thread.parent_thread_id = None
            thread.macro_title = None
            thread.macro_context_tags = []
            thread.macro_confidence = "low"
            thread.relation_to_macro = None
            continue
        thread.macro_thread_id = macro.macro_thread_id
        thread.parent_thread_id = macro.macro_thread_id
        thread.thread_level = "subthread"
        thread.macro_title = macro.title
        thread.macro_context_tags = list(macro.context_tags)
        thread.macro_confidence = macro.confidence
        siblings = [candidate for candidate in threads if candidate.thread_id != thread.thread_id and candidate.thread_id in macro.child_thread_ids]
        thread.relation_to_macro = (_relation_for_threads(thread, siblings[0], profile) if siblings else None) or "weak_relation"

    return macro_threads


def incremental_build_macro_threads(
    project_id: str,
    threads: list[OperationalThread],
    dirty_thread_ids: set[str],
    dirty_canonical_terms: set[str],
    existing_macros: list[OperationalMacroThread],
    events: list[OperationalEvent] | None = None,
    profile: AdaptiveChatProfile | None = None,
    stats: dict | None = None,
) -> list[OperationalMacroThread]:
    """Rebuild only the macros affected by dirty threads; reuse the rest.

    A macro is rebuilt when one of its children is dirty, when it shares a
    canonical term that changed, or when a new dirty thread is strongly linked
    to one of its children. Untouched macros (and their threads' macro_* fields)
    are kept verbatim."""
    candidates = [thread for thread in threads if thread.related_event_ids and thread.project_impact_score >= 50]
    profile = profile or build_adaptive_chat_profile(
        project_id, events or _profile_events_from_threads(project_id, candidates), candidates
    )
    thread_by_id = {thread.thread_id: thread for thread in candidates}
    dirty_norm_terms = {_norm(term) for term in dirty_canonical_terms}

    # Expand the affected frontier: dirty threads + anything strongly linked to them.
    affected: set[str] = {tid for tid in dirty_thread_ids if tid in thread_by_id}
    if affected:
        changed = True
        while changed:
            changed = False
            for thread in candidates:
                if thread.thread_id in affected:
                    continue
                for other_id in list(affected):
                    other = thread_by_id.get(other_id)
                    if other is None:
                        continue
                    if _strong_shared_canonical_terms(thread, other, profile):
                        affected.add(thread.thread_id)
                        changed = True
                        break

    def _macro_is_affected(macro: OperationalMacroThread) -> bool:
        if any(child_id in affected for child_id in macro.child_thread_ids):
            return True
        if dirty_norm_terms and {_norm(tag) for tag in macro.context_tags} & dirty_norm_terms:
            return True
        return False

    reused_macros = [macro for macro in existing_macros if not _macro_is_affected(macro)]
    # Children locked into reused macros must not be regrouped.
    locked_child_ids = {child_id for macro in reused_macros for child_id in macro.child_thread_ids}

    if not dirty_thread_ids:
        if stats is not None:
            stats.clear()
            stats.update({"mode": "incremental", "macros_rebuilt": 0, "macros_reused": len(existing_macros)})
        return list(existing_macros)

    recompute_threads = [thread for thread in candidates if thread.thread_id not in locked_child_ids]
    rebuilt_macros = build_macro_threads(project_id, recompute_threads, events, profile)

    if stats is not None:
        stats.clear()
        stats.update(
            {
                "mode": "incremental",
                "macros_rebuilt": len(rebuilt_macros),
                "macros_reused": len(reused_macros),
            }
        )
    return reused_macros + rebuilt_macros
