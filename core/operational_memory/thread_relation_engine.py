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
DEFAULT_RELATION_WINDOW_DAYS = 21
DEFAULT_MAX_CANDIDATES_PER_THREAD = 40


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


def _canonical_distribution(threads: list[OperationalThread], profile: AdaptiveChatProfile) -> dict[str, int]:
    distribution: dict[str, int] = {}
    for thread in threads:
        for term in _canonical_terms(thread, profile):
            distribution[_norm(term)] = distribution.get(_norm(term), 0) + 1
    return distribution


def calculate_canonical_discriminative_power(
    canonical_label: str,
    profile: AdaptiveChatProfile,
    threads: list[OperationalThread] | None = None,
) -> float:
    label = _norm(canonical_label)
    canonical = next((term for term in profile.canonical_terms if _norm(term.label) == label), None)
    if canonical is None:
        return 0.0
    if canonical.boundary_confidence == "low":
        return 0.1
    if not threads or len(threads) < 8:
        return 1.0 if canonical.boundary_confidence == "high" else 0.75
    distribution = _canonical_distribution(threads, profile)
    coverage = distribution.get(label, 0) / max(1, len(threads))
    boundary_factor = {"high": 1.0, "medium": 0.75, "low": 0.35}.get(canonical.boundary_confidence, 0.35)
    confidence_factor = {"high": 1.0, "medium": 0.85, "low": 0.55}.get(canonical.confidence, 0.55)
    power = (1.0 - coverage) * boundary_factor * confidence_factor
    return round(max(0.0, min(1.0, power)), 4)


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
    all_threads: list[OperationalThread] | None = None,
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
        broad_terms = [
            term
            for term in shared_canonical_terms
            if calculate_canonical_discriminative_power(term, profile, all_threads) < 0.35
        ]
        if broad_terms:
            score -= 0.15
            rejection_reasons.append(f"canonical term troppo diffuso: {', '.join(broad_terms[:3])}")
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


def _blocking_keys(thread: OperationalThread, profile: AdaptiveChatProfile, all_threads: list[OperationalThread]) -> set[str]:
    keys: set[str] = set()
    for canonical in _canonical_terms(thread, profile):
        power = calculate_canonical_discriminative_power(canonical, profile, all_threads)
        if power >= 0.25:
            keys.add(f"canonical:{_norm(canonical)}")
    for tag in _meaningful_tags(thread, profile):
        keys.add(f"context:{tag}")
    for family in _problem_families(thread):
        keys.add(f"problem:{family}")
    for step in _workflow_steps(thread, profile):
        keys.add(f"workflow:{step}")
    return keys


def _has_strong_canonical_overlap(
    left: OperationalThread,
    right: OperationalThread,
    profile: AdaptiveChatProfile,
    all_threads: list[OperationalThread],
) -> bool:
    shared = _canonical_terms(left, profile) & _canonical_terms(right, profile)
    return any(calculate_canonical_discriminative_power(term, profile, all_threads) >= 0.45 for term in shared)


def _within_relation_window(left: OperationalThread, right: OperationalThread, relation_window_days: int | None) -> bool:
    if relation_window_days is None or relation_window_days <= 0:
        return True
    left_time = _parse_timestamp(left.last_updated_at or left.started_at)
    right_time = _parse_timestamp(right.last_updated_at or right.started_at)
    return abs((left_time - right_time).days) <= relation_window_days


def _pair_pruning_reason(
    left: OperationalThread,
    right: OperationalThread,
    profile: AdaptiveChatProfile,
    all_threads: list[OperationalThread],
    relation_window_days: int | None,
) -> str | None:
    shared_keys = _blocking_keys(left, profile, all_threads) & _blocking_keys(right, profile, all_threads)
    strong_canonical = _has_strong_canonical_overlap(left, right, profile, all_threads)
    if not shared_keys and not strong_canonical:
        return "nessuna blocking key adattiva condivisa"
    if not _within_relation_window(left, right, relation_window_days) and not strong_canonical:
        return "fuori finestra temporale relation"
    shared_canonical = _canonical_terms(left, profile) & _canonical_terms(right, profile)
    if shared_canonical and not strong_canonical and not (_meaningful_tags(left, profile) & _meaningful_tags(right, profile)) and not (_problem_families(left) & _problem_families(right)):
        return "solo canonical term a bassa discriminazione"
    return None


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
    relation_window_days: int | None = DEFAULT_RELATION_WINDOW_DAYS,
    relation_max_candidates_per_thread: int = DEFAULT_MAX_CANDIDATES_PER_THREAD,
    stats: dict | None = None,
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
    per_thread_kept: dict[str, int] = {}
    raw_pairs = 0
    pruned_pairs = 0
    pruning_reasons: dict[str, int] = {}
    penalized_terms: dict[str, int] = {}

    for left, right in combinations(operational_threads, 2):
        raw_pairs += 1
        reason = _pair_pruning_reason(left, right, profile, operational_threads, relation_window_days)
        if reason:
            pruned_pairs += 1
            pruning_reasons[reason] = pruning_reasons.get(reason, 0) + 1
            continue
        if relation_max_candidates_per_thread > 0:
            left_count = per_thread_kept.get(left.thread_id, 0)
            right_count = per_thread_kept.get(right.thread_id, 0)
            if (left_count >= relation_max_candidates_per_thread or right_count >= relation_max_candidates_per_thread) and not _has_strong_canonical_overlap(left, right, profile, operational_threads):
                pruned_pairs += 1
                pruning_reasons["max candidates per thread raggiunto"] = pruning_reasons.get("max candidates per thread raggiunto", 0) + 1
                continue
        relation = score_thread_relation(left, right, profile, operational_threads)
        for rejection in relation.rejection_reasons:
            if rejection.startswith("canonical term troppo diffuso:"):
                for term in rejection.split(":", 1)[1].split(","):
                    key = term.strip()
                    if key:
                        penalized_terms[key] = penalized_terms.get(key, 0) + 1
        if relation.confidence == "low" and not include_rejected:
            continue
        if not _relation_is_relevant(relation):
            continue
        relations.append(relation)
        per_thread_kept[left.thread_id] = per_thread_kept.get(left.thread_id, 0) + 1
        per_thread_kept[right.thread_id] = per_thread_kept.get(right.thread_id, 0) + 1
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

    if stats is not None:
        stats.clear()
        stats.update(
            {
                "raw_pairs": raw_pairs,
                "pruned_pairs": pruned_pairs,
                "kept_pairs": len(relations),
                "relation_window_days": relation_window_days,
                "relation_max_candidates_per_thread": relation_max_candidates_per_thread,
                "pruning_reasons": dict(sorted(pruning_reasons.items(), key=lambda item: item[1], reverse=True)),
                "penalized_canonical_terms": dict(sorted(penalized_terms.items(), key=lambda item: item[1], reverse=True)),
            }
        )
    return sorted(relations, key=lambda item: (item.should_promote_to_macro, item.score), reverse=True)


def pair_key(left_id: str, right_id: str) -> str:
    """Stable, order-independent key for a thread pair (A-B == B-A)."""
    return "|".join(sorted([left_id, right_id]))


def build_blocking_index(
    threads: list[OperationalThread],
    profile: AdaptiveChatProfile,
    all_threads: list[OperationalThread],
) -> dict[str, set[str]]:
    """Map every adaptive blocking key to the set of thread ids that carry it.

    Lets the incremental path find, for a dirty thread, only the threads it
    could plausibly relate to — instead of pairing it against everything."""
    index: dict[str, set[str]] = {}
    for thread in threads:
        for key in _blocking_keys(thread, profile, all_threads):
            index.setdefault(key, set()).add(thread.thread_id)
    return index


def apply_relations_to_threads(
    threads: list[OperationalThread],
    relations: list[ThreadRelationCandidate],
) -> None:
    """Recompute the per-thread candidate_* fields from a final relation set
    without rescoring anything. Used so the incremental path leaves thread
    objects in the same shape the full rebuild would."""
    _reset_thread_relation_fields(threads)
    thread_by_id = {thread.thread_id: thread for thread in threads}
    for relation in relations:
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
            thread.relation_confidence_summary[relation.confidence] = (
                thread.relation_confidence_summary.get(relation.confidence, 0) + 1
            )


def incremental_thread_relation_candidates(
    project_id: str,
    threads: list[OperationalThread],
    dirty_thread_ids: set[str],
    existing_relations: list[ThreadRelationCandidate],
    events: list[OperationalEvent] | None = None,
    profile: AdaptiveChatProfile | None = None,
    include_rejected: bool = True,
    relation_window_days: int | None = DEFAULT_RELATION_WINDOW_DAYS,
    relation_max_candidates_per_thread: int = DEFAULT_MAX_CANDIDATES_PER_THREAD,
    stats: dict | None = None,
) -> list[ThreadRelationCandidate]:
    """Recompute relation candidates only for pairs touching a dirty thread.

    Pairs where neither endpoint changed are reused verbatim from
    ``existing_relations``. Stale relations whose endpoints no longer exist are
    dropped. Scoring is identical to :func:`build_thread_relation_candidates`."""
    operational_threads = [
        thread
        for thread in threads
        if thread.related_event_ids and thread.project_impact_score >= 50
    ]
    profile = profile or build_adaptive_chat_profile(project_id, events or [], operational_threads)
    op_ids = {thread.thread_id for thread in operational_threads}
    thread_by_id = {thread.thread_id: thread for thread in operational_threads}
    dirty_op_ids = dirty_thread_ids & op_ids

    # 1. Reuse every relation whose pair is fully intact and untouched.
    reused: dict[str, ThreadRelationCandidate] = {}
    for relation in existing_relations:
        src, tgt = relation.source_thread_id, relation.target_thread_id
        if src not in op_ids or tgt not in op_ids:
            continue  # stale: endpoint gone / demoted below threshold
        if src in dirty_op_ids or tgt in dirty_op_ids:
            continue  # touched: will be recomputed below
        reused[pair_key(src, tgt)] = relation

    # 2. Enumerate candidate pairs that involve a dirty thread, via blocking buckets.
    blocking_index = build_blocking_index(operational_threads, profile, operational_threads)
    candidate_pairs: set[tuple[str, str]] = set()
    for dirty_id in dirty_op_ids:
        thread = thread_by_id.get(dirty_id)
        if thread is None:
            continue
        neighbors: set[str] = set()
        for key in _blocking_keys(thread, profile, operational_threads):
            neighbors |= blocking_index.get(key, set())
        neighbors.discard(dirty_id)
        for other in neighbors:
            left, right = sorted([dirty_id, other])
            candidate_pairs.add((left, right))

    recalculated = 0
    pruning_reasons: dict[str, int] = {}
    penalized_terms: dict[str, int] = {}
    per_thread_kept: dict[str, int] = {}
    for relation in reused.values():
        per_thread_kept[relation.source_thread_id] = per_thread_kept.get(relation.source_thread_id, 0) + 1
        per_thread_kept[relation.target_thread_id] = per_thread_kept.get(relation.target_thread_id, 0) + 1

    recomputed: dict[str, ThreadRelationCandidate] = {}
    for left_id, right_id in candidate_pairs:
        left = thread_by_id[left_id]
        right = thread_by_id[right_id]
        recalculated += 1
        reason = _pair_pruning_reason(left, right, profile, operational_threads, relation_window_days)
        if reason:
            pruning_reasons[reason] = pruning_reasons.get(reason, 0) + 1
            continue
        if relation_max_candidates_per_thread > 0:
            left_count = per_thread_kept.get(left_id, 0)
            right_count = per_thread_kept.get(right_id, 0)
            if (
                left_count >= relation_max_candidates_per_thread
                or right_count >= relation_max_candidates_per_thread
            ) and not _has_strong_canonical_overlap(left, right, profile, operational_threads):
                pruning_reasons["max candidates per thread raggiunto"] = (
                    pruning_reasons.get("max candidates per thread raggiunto", 0) + 1
                )
                continue
        relation = score_thread_relation(left, right, profile, operational_threads)
        for rejection in relation.rejection_reasons:
            if rejection.startswith("canonical term troppo diffuso:"):
                for term in rejection.split(":", 1)[1].split(","):
                    key = term.strip()
                    if key:
                        penalized_terms[key] = penalized_terms.get(key, 0) + 1
        if relation.confidence == "low" and not include_rejected:
            continue
        if not _relation_is_relevant(relation):
            continue
        recomputed[pair_key(left_id, right_id)] = relation
        per_thread_kept[left_id] = per_thread_kept.get(left_id, 0) + 1
        per_thread_kept[right_id] = per_thread_kept.get(right_id, 0) + 1

    # 3. Merge reused + recomputed (recomputed wins on key collision).
    merged: dict[str, ThreadRelationCandidate] = dict(reused)
    merged.update(recomputed)
    relations = list(merged.values())
    apply_relations_to_threads(threads, relations)

    if stats is not None:
        stats.clear()
        stats.update(
            {
                "mode": "incremental",
                "raw_pairs": len(candidate_pairs),
                "kept_pairs": len(relations),
                "pruned_pairs": sum(pruning_reasons.values()),
                "relation_pairs_recalculated": recalculated,
                "relation_pairs_reused": len(reused),
                "dirty_threads_in_relations": len(dirty_op_ids),
                "relation_window_days": relation_window_days,
                "relation_max_candidates_per_thread": relation_max_candidates_per_thread,
                "pruning_reasons": dict(sorted(pruning_reasons.items(), key=lambda item: item[1], reverse=True)),
                "penalized_canonical_terms": dict(sorted(penalized_terms.items(), key=lambda item: item[1], reverse=True)),
            }
        )
    return sorted(relations, key=lambda item: (item.should_promote_to_macro, item.score), reverse=True)


def canonical_term_distribution_report(
    threads: list[OperationalThread],
    profile: AdaptiveChatProfile,
    broad_coverage_ratio: float = 0.4,
    discriminative_floor: float = 0.35,
) -> list[dict]:
    """Generic diagnostics on how wide each canonical term spreads.

    Terms that touch a large share of threads and generate many pairs while
    scoring low discriminative power surface here as ``broad`` — emergent, not
    hardcoded against any specific token."""
    operational_threads = [
        thread
        for thread in threads
        if thread.related_event_ids and thread.project_impact_score >= 50
    ]
    total = max(1, len(operational_threads))
    distribution = _canonical_distribution(operational_threads, profile)
    rows: list[dict] = []
    label_by_norm = {_norm(term.label): term for term in profile.canonical_terms}
    for norm_label, coverage in distribution.items():
        canonical = label_by_norm.get(norm_label)
        label = canonical.label if canonical else norm_label
        power = calculate_canonical_discriminative_power(label, profile, operational_threads)
        coverage_ratio = coverage / total
        pair_generation_count = coverage * (coverage - 1) // 2
        is_broad = coverage_ratio >= broad_coverage_ratio and power < discriminative_floor
        is_weak_context = bool(
            canonical
            and (canonical.boundary_confidence == "low" or canonical.confidence == "low")
        )
        rows.append(
            {
                "label": label,
                "thread_coverage": coverage,
                "coverage_ratio": round(coverage_ratio, 4),
                "pair_generation_count": pair_generation_count,
                "discriminative_power": power,
                "broad_canonical_term": is_broad,
                "weak_context_term": is_weak_context,
            }
        )
    rows.sort(key=lambda row: (row["pair_generation_count"], row["thread_coverage"]), reverse=True)
    return rows


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
