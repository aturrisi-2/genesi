from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from itertools import combinations

from core.operational_memory.chat_profile_engine import build_adaptive_chat_profile
from core.operational_memory.macro_thread_engine import calculate_macro_heterogeneity
from core.operational_memory.models import (
    AdaptiveChatProfile,
    GroupingConfidence,
    OperationalEvent,
    OperationalMacroThread,
    OperationalThread,
    ThreadRelationCandidate,
    ThreadRelationType,
)


_GENERIC_PROBLEM_TERMS = {"problema", "verifica", "controllo", "fare", "fatto", "ok", "manca"}
_LOCATION_HINT_RE = re.compile(r"\b(?:porta|area|zona|piano|magazzino|scuola|classe|cliente|torre|linea)\b", re.IGNORECASE)
_WORKFLOW_TERMS = {
    "aperto",
    "assegnato",
    "intervento",
    "verifica",
    "risolto",
    "chiuso",
    "consegna",
    "ritardo",
    "ordine",
    "compiti",
    "scadenza",
}
_PROBLEM_FAMILIES = {
    "login_error": {"login", "errore login", "accesso"},
    "billing": {"fattura", "fatturazione", "pagamento"},
    "delivery_delay": {"ritardo", "consegna in ritardo", "corriere"},
    "missing": {"manca", "mancante", "assenza"},
    "malfunction": {"non parte", "non funziona", "anomalia", "guasto"},
    "leak": {"perde", "perdita", "acqua"},
    "power": {"non alimentata", "disalimentata", "alimentazione"},
    "school_deadline": {"compiti", "scadenza", "scuola"},
}


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _relation_id(project_id: str, left_id: str, right_id: str) -> str:
    ordered = "|".join(sorted([left_id, right_id]))
    digest = hashlib.sha1(f"{project_id}:{ordered}".encode("utf-8")).hexdigest()[:12]
    return f"relation_{digest}"


def _thread_text(thread: OperationalThread) -> str:
    return " ".join(
        [
            thread.title,
            *thread.context_tags,
            *thread.related_tasks,
            *thread.related_issues,
            *thread.unresolved_questions,
        ]
    )


def _meaningful_tags(thread: OperationalThread, profile: AdaptiveChatProfile) -> set[str]:
    generic = {_norm(term) for term in profile.generic_terms}
    tags = {_norm(tag) for tag in thread.context_tags if _norm(tag) and _norm(tag) not in generic}
    return {
        tag
        for tag in tags
        if " " in tag or any(char.isdigit() for char in tag) or tag not in _GENERIC_PROBLEM_TERMS
    }


def _canonical_terms(thread: OperationalThread, profile: AdaptiveChatProfile) -> set[str]:
    text = _norm(_thread_text(thread))
    labels: set[str] = set()
    for canonical in profile.canonical_terms:
        if canonical.boundary_confidence == "low":
            continue
        label = _norm(canonical.label)
        sources = [_norm(term) for term in canonical.source_terms]
        head = _norm(canonical.head_entity or "")
        action = _norm(canonical.action_or_problem or "")
        modifiers = [_norm(modifier) for modifier in canonical.context_modifiers]
        if label and label in text:
            labels.add(canonical.label)
        elif any(source and source in text for source in sources):
            labels.add(canonical.label)
        elif action and action in text and (head and head in text or any(modifier in text for modifier in modifiers)):
            labels.add(canonical.label)
        else:
            parts = [part.strip() for part in label.split("/") if part.strip()]
            if len([part for part in parts if part in text]) >= 2:
                labels.add(canonical.label)
    return labels


def _problem_families(thread: OperationalThread) -> set[str]:
    text = _norm(_thread_text(thread))
    families = set()
    for family, terms in _PROBLEM_FAMILIES.items():
        if any(term in text for term in terms):
            families.add(family)
    return families


def _workflow_steps(thread: OperationalThread, profile: AdaptiveChatProfile) -> set[str]:
    text = _norm(_thread_text(thread))
    profile_steps = {_norm(term) for term in [*profile.workflow_patterns, *profile.recurring_actions, *profile.recurring_completion_terms]}
    return {term for term in [*profile_steps, *_WORKFLOW_TERMS] if term and term in text}


def _owner_signal(left: OperationalThread, right: OperationalThread) -> bool:
    left_text = _norm(_thread_text(left))
    right_text = _norm(_thread_text(right))
    for issue in [*left.related_tasks, *left.related_issues]:
        words = [word for word in re.findall(r"\b[A-ZÀ-Ý][a-zà-ÿ]{2,}\b", issue)]
        if any(_norm(word) in right_text for word in words):
            return True
    for issue in [*right.related_tasks, *right.related_issues]:
        words = [word for word in re.findall(r"\b[A-ZÀ-Ý][a-zà-ÿ]{2,}\b", issue)]
        if any(_norm(word) in left_text for word in words):
            return True
    return False


def _has_location_shape(term: str) -> bool:
    return bool(_LOCATION_HINT_RE.search(term)) or bool(re.search(r"\b[A-Z]{0,4}\d{1,4}\b", term, re.IGNORECASE))


def classify_relation_type(
    shared_canonical_terms: list[str],
    shared_context_tags: list[str],
    shared_workflow_steps: list[str],
    left: OperationalThread,
    right: OperationalThread,
) -> ThreadRelationType:
    left_families = _problem_families(left)
    right_families = _problem_families(right)
    if left_families and left_families & right_families:
        return "same_problem"
    if shared_canonical_terms and shared_workflow_steps:
        return "same_work_package"
    if shared_canonical_terms and any(_has_location_shape(term) for term in shared_canonical_terms):
        return "same_location"
    if shared_canonical_terms:
        return "same_work_package"
    if shared_workflow_steps and shared_context_tags:
        return "same_workflow_sequence"
    if shared_context_tags and any(_has_location_shape(tag) for tag in shared_context_tags):
        return "same_location"
    if shared_context_tags:
        return "same_object"
    if _owner_signal(left, right):
        return "same_owner"
    return "weak_context"


def _has_incompatible_problem(left: OperationalThread, right: OperationalThread) -> bool:
    left_families = _problem_families(left)
    right_families = _problem_families(right)
    return bool(left_families and right_families and not (left_families & right_families))


def _confidence(score: float) -> GroupingConfidence:
    if score >= 0.78:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def should_promote_relation_to_macro(
    relation: ThreadRelationCandidate,
    left: OperationalThread,
    right: OperationalThread,
    profile: AdaptiveChatProfile,
) -> bool:
    if relation.confidence != "high":
        return False
    if relation.relation_type not in {"same_problem", "same_work_package", "same_workflow_sequence"}:
        return False
    if _has_incompatible_problem(left, right):
        return False
    return calculate_macro_heterogeneity([left, right], profile) <= 0.35


def should_keep_relation_as_candidate(relation: ThreadRelationCandidate) -> bool:
    return relation.confidence == "medium" or (
        relation.confidence == "high" and not relation.should_promote_to_macro
    )


def explain_thread_relation(relation: ThreadRelationCandidate) -> str:
    if relation.evidence:
        return "; ".join(relation.evidence)
    if relation.rejection_reasons:
        return "; ".join(relation.rejection_reasons)
    return "relazione debole non spiegata"


def score_thread_relation(
    left: OperationalThread,
    right: OperationalThread,
    profile: AdaptiveChatProfile | None = None,
) -> ThreadRelationCandidate:
    profile = profile or build_adaptive_chat_profile(left.project_id, [], [left, right])
    shared_canonical_terms = sorted(_canonical_terms(left, profile) & _canonical_terms(right, profile))
    shared_context_tags = sorted(_meaningful_tags(left, profile) & _meaningful_tags(right, profile))
    shared_workflow_steps = sorted(_workflow_steps(left, profile) & _workflow_steps(right, profile))
    same_problem = bool(_problem_families(left) & _problem_families(right))
    owner_signal = _owner_signal(left, right)
    evidence: list[str] = []
    rejection_reasons: list[str] = []
    score = 0.0

    if shared_canonical_terms:
        score += 0.45
        evidence.append(f"termini canonici condivisi: {', '.join(shared_canonical_terms[:3])}")
    if shared_context_tags:
        score += 0.20
        evidence.append(f"contesto condiviso: {', '.join(shared_context_tags[:4])}")
    if same_problem:
        score += 0.25
        evidence.append("famiglia problema condivisa")
    if shared_workflow_steps and (shared_canonical_terms or shared_context_tags or same_problem):
        score += 0.12
        evidence.append(f"sequenza workflow compatibile: {', '.join(shared_workflow_steps[:3])}")
    if owner_signal and (shared_canonical_terms or shared_context_tags or same_problem):
        score += 0.08
        evidence.append("owner/responsabile ricorrente con altro segnale")
    elif owner_signal:
        rejection_reasons.append("stesso owner non sufficiente da solo")
    if _has_incompatible_problem(left, right):
        if shared_context_tags or any(_has_location_shape(term) for term in shared_canonical_terms):
            score -= 0.05
            rejection_reasons.append("problemi diversi nello stesso contesto")
        else:
            score -= 0.25
            rejection_reasons.append("problemi incompatibili")
    if not shared_canonical_terms and not shared_context_tags and not same_problem:
        rejection_reasons.append("nessun segnale operativo condiviso forte")
    if shared_context_tags and all(tag in _GENERIC_PROBLEM_TERMS for tag in shared_context_tags):
        score = min(score, 0.25)
        rejection_reasons.append("solo termini generici condivisi")

    score = round(max(0.0, min(1.0, score)), 4)
    relation = ThreadRelationCandidate(
        relation_id=_relation_id(left.project_id, left.thread_id, right.thread_id),
        project_id=left.project_id,
        source_thread_id=left.thread_id,
        target_thread_id=right.thread_id,
        relation_type=classify_relation_type(shared_canonical_terms, shared_context_tags, shared_workflow_steps, left, right),
        confidence=_confidence(score),
        score=score,
        shared_canonical_terms=shared_canonical_terms,
        shared_context_tags=shared_context_tags,
        shared_workflow_steps=shared_workflow_steps,
        evidence=evidence,
        rejection_reasons=rejection_reasons,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    if relation.relation_type == "same_location" and relation.score < 0.45 and (shared_context_tags or shared_canonical_terms):
        relation.score = 0.45
        relation.confidence = "medium"
    relation.should_promote_to_macro = should_promote_relation_to_macro(relation, left, right, profile)
    relation.should_remain_candidate = should_keep_relation_as_candidate(relation)
    if relation.confidence == "low" and not relation.rejection_reasons:
        relation.rejection_reasons.append("score sotto soglia candidate")
    return relation


def _relation_is_relevant(relation: ThreadRelationCandidate) -> bool:
    if relation.confidence != "low":
        return True
    return bool(relation.evidence)


def _reset_thread_relation_fields(threads: list[OperationalThread]) -> None:
    for thread in threads:
        thread.candidate_relation_ids = []
        thread.candidate_parent_ids = []
        thread.candidate_child_ids = []
        thread.relation_confidence_summary = {"low": 0, "medium": 0, "high": 0}


def _append_unique(values: list[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def build_thread_relation_candidates(
    project_id: str,
    threads: list[OperationalThread],
    events: list[OperationalEvent] | None = None,
    profile: AdaptiveChatProfile | None = None,
    include_rejected: bool = True,
) -> list[ThreadRelationCandidate]:
    operational_threads = [
        thread
        for thread in threads
        if thread.related_event_ids and thread.project_impact_score >= 50
    ]
    profile = profile or build_adaptive_chat_profile(project_id, events or [], operational_threads)
    _reset_thread_relation_fields(threads)
    relations: list[ThreadRelationCandidate] = []
    thread_by_id = {thread.thread_id: thread for thread in threads}

    for left, right in combinations(operational_threads, 2):
        relation = score_thread_relation(left, right, profile)
        if relation.confidence == "low" and not include_rejected:
            continue
        if not _relation_is_relevant(relation):
            continue
        relations.append(relation)
        for thread_id, opposite_id in (
            (relation.source_thread_id, relation.target_thread_id),
            (relation.target_thread_id, relation.source_thread_id),
        ):
            thread = thread_by_id.get(thread_id)
            if thread is None:
                continue
            _append_unique(thread.candidate_relation_ids, relation.relation_id)
            if relation.should_remain_candidate:
                _append_unique(thread.candidate_child_ids, opposite_id)
            if relation.should_promote_to_macro:
                _append_unique(thread.candidate_parent_ids, opposite_id)
            thread.relation_confidence_summary[relation.confidence] = thread.relation_confidence_summary.get(relation.confidence, 0) + 1

    return sorted(relations, key=lambda item: (item.should_promote_to_macro, item.score), reverse=True)


def promoted_relation_groups(relations: list[ThreadRelationCandidate]) -> list[set[str]]:
    groups: list[set[str]] = []
    for relation in relations:
        if not relation.should_promote_to_macro:
            continue
        pair = {relation.source_thread_id, relation.target_thread_id}
        merged = False
        for group in groups:
            if group & pair:
                group |= pair
                merged = True
                break
        if not merged:
            groups.append(set(pair))
    return groups
