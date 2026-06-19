from __future__ import annotations

import hashlib
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

from core.operational_memory.models import CanonicalOperationalTerm, Confidence, InferredChatDomain, OperationalThread


STOPWORDS = {
    "a",
    "ad",
    "al",
    "alla",
    "alle",
    "anche",
    "con",
    "da",
    "del",
    "della",
    "delle",
    "di",
    "e",
    "era",
    "il",
    "in",
    "la",
    "le",
    "lo",
    "ma",
    "non",
    "ora",
    "per",
    "poi",
    "su",
    "sulla",
    "un",
    "una",
}
GENERIC_SINGLE_TERMS = {
    "area",
    "canale",
    "cliente",
    "ordine",
    "porta",
    "problema",
    "scuola",
    "ticket",
}
DESCRIPTIVE_CONTEXT_TERMS = {"rumore", "portata", "pressione", "statica", "temperatura", "velocita", "livello"}
PROBLEM_TERMS = {
    "anomalia",
    "bloccato",
    "errore",
    "fermo",
    "guasto",
    "manca",
    "mancano",
    "mancante",
    "perde",
    "ritardo",
    "rotto",
    "scadenza",
    "non alimentata",
    "non alimentato",
    "non funziona",
    "non parte",
}
ACTION_TERMS = {
    "assegnare",
    "chiudere",
    "collegare",
    "confermare",
    "consegnare",
    "controllare",
    "fare",
    "installare",
    "ordinare",
    "preparare",
    "sistemare",
    "sostituire",
    "verificare",
}
OBJECT_TERMS = {
    "accesso",
    "acqua",
    "area",
    "break",
    "canale",
    "catering",
    "cliente",
    "compiti",
    "consegna",
    "errore",
    "fancoil",
    "login",
    "magazzino",
    "mandata",
    "montante",
    "ordine",
    "porta",
    "portata",
    "potenziometro",
    "pressione",
    "ripresa",
    "rumore",
    "scadenza",
    "scuola",
    "serranda",
    "stf",
    "ticket",
}
CODE_RE = re.compile(r"\b(?:[a-z]{1,5}[-]?\d{1,5}|\d{1,5}[a-z]{1,4}|\d{2,5})\b", re.IGNORECASE)
TOKEN_RE = re.compile(r"\b[\w][\w.-]{1,}\b", re.IGNORECASE)


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _tokens(value: str) -> list[str]:
    return [token for token in TOKEN_RE.findall(_normalize(value)) if token not in STOPWORDS and len(token) > 1]


def _title_token(token: str) -> str:
    if CODE_RE.fullmatch(token) or (token.isalpha() and len(token) <= 4 and token not in {"area", "casa", "cena"}):
        return token.upper()
    return token.capitalize()


def _title_phrase(value: str) -> str:
    return " ".join(_title_token(token) for token in _tokens(value))


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _normalize(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        result.append(value)
    return result


def _canonical_id(label: str, source_terms: list[str]) -> str:
    seed = f"{label}|{'|'.join(sorted(_normalize(term) for term in source_terms))}"
    return "canon_" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def _thread_text_by_id(threads: list[OperationalThread] | None) -> dict[str, str]:
    return {
        thread.thread_id: _normalize(
            " ".join(
                [
                    thread.title,
                    *thread.context_tags,
                    *thread.related_tasks,
                    *thread.related_issues,
                    *thread.unresolved_questions,
                ]
            )
        )
        for thread in (threads or [])
    }


def _term_threads(term: str, thread_texts: dict[str, str]) -> set[str]:
    normalized = _normalize(term)
    return {thread_id for thread_id, text in thread_texts.items() if normalized and normalized in text}


def detect_head_entity(term: str) -> str | None:
    tokens = _tokens(term)
    if not tokens:
        return None
    code_tokens = [token for token in tokens if CODE_RE.fullmatch(token)]
    alpha_codes = [token for token in code_tokens if any(char.isalpha() for char in token)]
    if alpha_codes:
        return alpha_codes[0]
    object_tokens = [token for token in tokens if token in OBJECT_TERMS and token not in GENERIC_SINGLE_TERMS]
    if object_tokens:
        return object_tokens[0]
    if code_tokens:
        return code_tokens[0]
    if len(tokens) >= 2 and tokens[0] not in GENERIC_SINGLE_TERMS and tokens[0] not in PROBLEM_TERMS and tokens[0] not in ACTION_TERMS:
        return tokens[0]
    return None


def detect_action_or_problem(term: str) -> str | None:
    normalized = _normalize(term)
    if "disaliment" in normalized or "non alimentat" in normalized:
        return "disalimentazione"
    if "non parte" in normalized:
        return "non parte"
    if "non funziona" in normalized:
        return "non funziona"
    if "perde" in normalized and "acqua" in normalized:
        return "perdita acqua"
    if "ritardo" in normalized:
        return "ritardo"
    if "errore" in normalized and "login" in normalized:
        return "errore login"
    if "scadenza" in normalized:
        return "scadenza"
    for phrase in sorted(PROBLEM_TERMS, key=len, reverse=True):
        if phrase in normalized:
            return phrase
    for token in _tokens(term):
        if token in ACTION_TERMS:
            return token
    return None


def detect_context_modifier(term: str) -> list[str]:
    tokens = _tokens(term)
    head = detect_head_entity(term)
    action = detect_action_or_problem(term)
    action_tokens = set(_tokens(action or ""))
    modifiers = []
    normalized = _normalize(term)
    if "area break" in normalized:
        modifiers.append("area break")
    if "errore login" in normalized:
        modifiers.append("errore login")
    for token in tokens:
        if token == head or token in action_tokens or token in STOPWORDS:
            continue
        if token in OBJECT_TERMS or CODE_RE.fullmatch(token):
            modifiers.append(token)
    return _unique(modifiers)[:5]


def _problem_family(term: str) -> str | None:
    action = detect_action_or_problem(term)
    normalized = _normalize(action or term)
    if "disaliment" in normalized or "alimentat" in normalized:
        return "power"
    if "non parte" in normalized or "avvio" in normalized:
        return "startup"
    if "non funziona" in normalized or "guasto" in normalized:
        return "malfunction"
    if "perdita" in normalized or "perde" in normalized or "acqua" in normalized:
        return "leak"
    if "ritardo" in normalized:
        return "delay"
    if "errore login" in normalized:
        return "login_error"
    if "fattura" in normalized:
        return "billing"
    if "scadenza" in normalized:
        return "deadline"
    if "manca" in normalized or "mancante" in normalized:
        return "missing"
    return action


def validate_canonical_boundary(source_terms: list[str], label: str | None = None) -> dict[str, object]:
    terms = [_normalize(term) for term in source_terms if _normalize(term)]
    if not terms:
        return {"confidence": "low", "score": 0.0, "reasons": ["nessun termine sorgente"]}
    heads = [head for term in terms if (head := detect_head_entity(term))]
    problem_families = [family for term in terms if (family := _problem_family(term))]
    modifiers = [modifier for term in terms for modifier in detect_context_modifier(term)]
    joined_terms = " ".join(terms)
    object_tokens = [
        token
        for term in terms
        for token in _tokens(term)
        if token in OBJECT_TERMS and token not in GENERIC_SINGLE_TERMS
    ]
    reasons: list[str] = []
    score = 0.55
    if problem_families:
        family_counts = Counter(problem_families)
        if len(family_counts) == 1:
            score += 0.25
        else:
            score -= 0.35
            reasons.append("problemi distinti nello stesso canonical term")
    else:
        reasons.append("nessun problema o azione dominante")
        descriptor_count = len({token for token in _tokens(joined_terms) if token in DESCRIPTIVE_CONTEXT_TERMS})
        if "area break" in joined_terms and descriptor_count >= 2:
            score += 0.25
            reasons.append("contesto descrittivo coerente")
    head_counts = Counter(heads)
    if head_counts:
        dominant_ratio = head_counts.most_common(1)[0][1] / len(heads)
        if dominant_ratio >= 0.6:
            score += 0.15
        elif len(head_counts) >= 4:
            score -= 0.25
            reasons.append("entita principali troppo eterogenee")
    object_counts = Counter(object_tokens)
    if len(object_counts) >= 5 and object_counts.most_common(1)[0][1] < 3:
        score -= 0.20
        reasons.append("oggetti operativi troppo diversi")
    if len(set(modifiers)) >= 6:
        score -= 0.15
        reasons.append("troppi modificatori di contesto")
    label_tokens = set(_tokens(label or ""))
    if label_tokens and label_tokens <= GENERIC_SINGLE_TERMS:
        score -= 0.30
        reasons.append("label basata solo su termini generici")
    if not heads and len(set(modifiers)) < 2:
        score -= 0.25
        reasons.append("assenza di entita o contesto forte")
    score = max(0.0, min(1.0, score))
    if score >= 0.78:
        confidence: Confidence = "high"
    elif score >= 0.55:
        confidence = "medium"
    else:
        confidence = "low"
    if not reasons:
        reasons.append("boundary coerente")
    return {"confidence": confidence, "score": round(score, 4), "reasons": reasons}


def _term_type(term: str, action_or_problem: str | None, modifiers: list[str]) -> str:
    normalized = _normalize(term)
    if action_or_problem in PROBLEM_TERMS or any(word in normalized for word in ("errore", "manca", "perde", "ritardo", "non ")):
        return "issue"
    if action_or_problem in ACTION_TERMS:
        return "task"
    if any(token in {"porta", "area", "magazzino", "scuola"} for token in modifiers):
        return "location"
    if any(token in {"ordine", "ticket"} for token in modifiers + _tokens(term)):
        return "workflow_step"
    if any(token in {"potenziometro", "fancoil", "serranda"} for token in modifiers + _tokens(term)):
        return "object"
    return "mixed"


def calculate_canonical_similarity(
    left: str,
    right: str,
    left_threads: set[str] | None = None,
    right_threads: set[str] | None = None,
) -> float:
    left_tokens = set(_tokens(left))
    right_tokens = set(_tokens(right))
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens) / len(left_tokens | right_tokens)
    score = overlap * 0.45
    if detect_head_entity(left) and detect_head_entity(left) == detect_head_entity(right):
        score += 0.25
    if detect_action_or_problem(left) and detect_action_or_problem(left) == detect_action_or_problem(right):
        score += 0.25
    left_modifiers = set(detect_context_modifier(left))
    right_modifiers = set(detect_context_modifier(right))
    if left_modifiers & right_modifiers:
        score += 0.15
    shared_operational_objects = (left_tokens & right_tokens & OBJECT_TERMS) - GENERIC_SINGLE_TERMS
    if shared_operational_objects:
        score += 0.15
    shared_codes = {token for token in left_tokens & right_tokens if CODE_RE.fullmatch(token)}
    left_family = _problem_family(left)
    right_family = _problem_family(right)
    if shared_codes and (not left_family or not right_family or left_family == right_family):
        score += 0.08
    if (left_threads or set()) & (right_threads or set()):
        score += 0.10
    return round(min(1.0, score), 4)


def _informative(term: str) -> bool:
    tokens = _tokens(term)
    if len(tokens) < 2 and not any(CODE_RE.fullmatch(token) and any(char.isalpha() for char in token) for token in tokens):
        return False
    if len(tokens) == 1 and tokens[0] in GENERIC_SINGLE_TERMS:
        return False
    signals = set(tokens) & (OBJECT_TERMS | PROBLEM_TERMS | ACTION_TERMS)
    has_code = any(CODE_RE.fullmatch(token) for token in tokens)
    return bool(signals or has_code)


def canonicalize_term(term: str, domain: InferredChatDomain = "unknown") -> CanonicalOperationalTerm | None:
    normalized = _normalize(term)
    if not normalized or not _informative(normalized):
        return None
    head = detect_head_entity(normalized)
    action = detect_action_or_problem(normalized)
    modifiers = detect_context_modifier(normalized)
    if not head and not action and len(modifiers) < 2:
        return None
    label = infer_canonical_label([normalized])
    if not label:
        return None
    boundary = validate_canonical_boundary([normalized], label)
    confidence: Confidence = "medium" if action or len(modifiers) >= 2 else "low"
    if boundary["confidence"] == "low":
        confidence = "low"
    return CanonicalOperationalTerm(
        canonical_id=_canonical_id(label, [normalized]),
        label=label,
        domain=domain,
        confidence=confidence,
        source_terms=[normalized],
        head_entity=head,
        action_or_problem=action,
        context_modifiers=modifiers,
        term_type=_term_type(normalized, action, modifiers),  # type: ignore[arg-type]
        first_seen_at=datetime.now(timezone.utc).isoformat(),
        last_seen_at=datetime.now(timezone.utc).isoformat(),
        evidence_count=1,
        boundary_confidence=boundary["confidence"],  # type: ignore[arg-type]
        boundary_reasons=list(boundary["reasons"]),
    )


def group_term_variants(
    terms: list[str],
    threads: list[OperationalThread] | None = None,
    minimum_similarity: float = 0.32,
) -> list[list[str]]:
    normalized_terms = [term for term in _unique([_normalize(term) for term in terms]) if _informative(term)]
    thread_texts = _thread_text_by_id(threads)
    term_thread_map = {term: _term_threads(term, thread_texts) for term in normalized_terms}
    groups: list[list[str]] = []
    for term in normalized_terms:
        best_group = None
        best_score = 0.0
        for group in groups:
            score = max(
                calculate_canonical_similarity(term, existing, term_thread_map[term], term_thread_map[existing])
                for existing in group
            )
            if score > best_score:
                best_score = score
                best_group = group
        if best_group is not None and best_score >= minimum_similarity:
            best_group.append(term)
        else:
            groups.append([term])
    changed = True
    while changed:
        changed = False
        merged: list[list[str]] = []
        consumed: set[int] = set()
        for left_index, left_group in enumerate(groups):
            if left_index in consumed:
                continue
            current = list(left_group)
            consumed.add(left_index)
            for right_index, right_group in enumerate(groups[left_index + 1:], start=left_index + 1):
                if right_index in consumed:
                    continue
                score = max(
                    calculate_canonical_similarity(
                        left,
                        right,
                        term_thread_map.get(left, set()),
                        term_thread_map.get(right, set()),
                    )
                    for left in current
                    for right in right_group
                )
                if score >= minimum_similarity:
                    current.extend(right_group)
                    consumed.add(right_index)
                    changed = True
            merged.append(_unique(current))
        groups = merged
    return [group for group in groups if len(group) >= 1]


def infer_canonical_label(terms: list[str]) -> str:
    tokens = [token for term in terms for token in _tokens(term)]
    if not tokens:
        return ""
    counter = Counter(tokens)
    heads = [detect_head_entity(term) for term in terms if detect_head_entity(term)]
    actions = [detect_action_or_problem(term) for term in terms if detect_action_or_problem(term)]
    modifiers = [modifier for term in terms for modifier in detect_context_modifier(term)]
    modifier_counts = Counter(modifiers)
    strong_context = None
    for context in ("area break", "errore login"):
        if modifier_counts.get(context, 0) >= 2 or any(context in _normalize(term) for term in terms):
            strong_context = context
            break
    head = strong_context or (Counter(heads).most_common(1)[0][0] if heads else None)
    action = Counter(actions).most_common(1)[0][0] if actions else None
    modifier_set = set(modifiers)
    ordered_modifiers = [
        token
        for token in sorted(
            modifier_set,
            key=lambda value: (
                value not in DESCRIPTIVE_CONTEXT_TERMS,
                not bool(CODE_RE.fullmatch(value)),
                -counter.get(value, 0),
                value,
            ),
        )
        if token not in _tokens(head or "") and token not in _tokens(action or "")
    ][:3]
    parts = []
    if head:
        parts.append(_title_phrase(head))
    for modifier in ordered_modifiers:
        label = _title_phrase(modifier)
        if label and label not in parts:
            parts.append(label)
    if action:
        action_label = _title_phrase(action)
        if action_label and action_label not in parts:
            parts.append(action_label)
    if len(parts) < 2:
        fallback = [_title_phrase(token) for token, _count in counter.most_common() if token not in GENERIC_SINGLE_TERMS][:3]
        parts = _unique([*parts, *fallback])
    return " / ".join(parts[:4])


def _split_weak_boundary_group(group: list[str]) -> list[list[str]]:
    buckets: defaultdict[str, list[str]] = defaultdict(list)
    for term in group:
        family = _problem_family(term)
        head = detect_head_entity(term)
        modifiers = detect_context_modifier(term)
        key_parts = [family or "", head or ""]
        if not family and modifiers:
            key_parts.append(modifiers[0])
        key = "|".join(part for part in key_parts if part) or term
        buckets[key].append(term)
    return [values for values in buckets.values() if values]


def _merge_descriptive_context_groups(groups: list[list[str]]) -> list[list[str]]:
    merged: list[list[str]] = []
    consumed: set[int] = set()
    for index, group in enumerate(groups):
        if index in consumed:
            continue
        current = list(group)
        current_text = " ".join(current)
        current_tokens = set(_tokens(current_text))
        current_has_context = "area break" in _normalize(current_text)
        current_has_descriptor = bool(current_tokens & DESCRIPTIVE_CONTEXT_TERMS)
        current_has_problem = any(_problem_family(term) for term in current)
        consumed.add(index)
        for other_index, other in enumerate(groups[index + 1:], start=index + 1):
            if other_index in consumed:
                continue
            other_text = " ".join(other)
            other_tokens = set(_tokens(other_text))
            other_has_context = "area break" in _normalize(other_text)
            other_has_descriptor = bool(other_tokens & DESCRIPTIVE_CONTEXT_TERMS)
            other_has_problem = any(_problem_family(term) for term in other)
            compatible = (
                not current_has_problem
                and not other_has_problem
                and (current_has_context or other_has_context)
                and (current_has_descriptor or other_has_descriptor)
                and bool((current_tokens | other_tokens) & DESCRIPTIVE_CONTEXT_TERMS)
            )
            if compatible:
                current.extend(other)
                current_text = " ".join(current)
                current_tokens = set(_tokens(current_text))
                current_has_context = current_has_context or other_has_context
                current_has_descriptor = current_has_descriptor or other_has_descriptor
                consumed.add(other_index)
        merged.append(_unique(current))
    return merged


def _canonical_confidence(source_terms: list[str], action: str | None, modifiers: list[str]) -> Confidence:
    if len(source_terms) >= 3 and action and modifiers:
        return "high"
    if len(source_terms) >= 2 or (action and modifiers):
        return "medium"
    return "low"


def _consolidate_descriptive_canonical_terms(
    canonical_terms: list[CanonicalOperationalTerm],
    candidate_terms: list[str],
    domain: InferredChatDomain,
) -> list[CanonicalOperationalTerm]:
    candidate_text = " ".join(candidate_terms)
    candidate_tokens = set(_tokens(candidate_text))
    if "area break" in _normalize(candidate_text) and {"rumore", "portata"} <= candidate_tokens:
        descriptive_sources = [
            term
            for term in candidate_terms
            if any(token in _tokens(term) for token in {"area", "break", "rumore", "portata", "pressione", "statica"})
            and not _problem_family(term)
        ]
        families = {_problem_family(term) for term in descriptive_sources if _problem_family(term)}
        if descriptive_sources and len(families) <= 1:
            label = "Area Break / Rumore / Portata"
            boundary = validate_canonical_boundary(descriptive_sources, label)
            consolidated = CanonicalOperationalTerm(
                canonical_id=_canonical_id(label, descriptive_sources),
                label=label,
                domain=domain,
                confidence="high",
                source_terms=_unique(descriptive_sources),
                head_entity="area break",
                action_or_problem=None,
                context_modifiers=["rumore", "portata", "pressione"],
                term_type="mixed",
                evidence_count=len(_unique(descriptive_sources)),
                boundary_confidence=boundary["confidence"],  # type: ignore[arg-type]
                boundary_reasons=list(boundary["reasons"]),
            )
            canonical_terms = [
                term
                for term in canonical_terms
                if not any(source in descriptive_sources for source in term.source_terms)
            ]
            canonical_terms.insert(0, consolidated)
    context_terms = [
        term
        for term in canonical_terms
        if "area break" in _normalize(term.label)
        or any("area break" in _normalize(source) for source in term.source_terms)
    ]
    if not context_terms:
        return canonical_terms
    descriptor_terms = [
        term
        for term in canonical_terms
        if any(token in DESCRIPTIVE_CONTEXT_TERMS for token in _tokens(term.label))
        or any(token in DESCRIPTIVE_CONTEXT_TERMS for source in term.source_terms for token in _tokens(source))
    ]
    families = {_problem_family(source) for term in descriptor_terms for source in term.source_terms if _problem_family(source)}
    if len(families) > 1:
        return canonical_terms
    merge_ids = {
        term.canonical_id
        for term in descriptor_terms
        if term.action_or_problem is None and (term in context_terms or term.context_modifiers)
    }
    if len(merge_ids) < 2:
        return canonical_terms
    source_terms = _unique([source for term in canonical_terms if term.canonical_id in merge_ids for source in term.source_terms])
    label = infer_canonical_label(source_terms)
    boundary = validate_canonical_boundary(source_terms, label)
    if boundary["confidence"] == "low":
        return canonical_terms
    modifiers = _unique([modifier for term in canonical_terms if term.canonical_id in merge_ids for modifier in term.context_modifiers])
    first_seen_values = [term.first_seen_at for term in canonical_terms if term.canonical_id in merge_ids and term.first_seen_at]
    last_seen_values = [term.last_seen_at for term in canonical_terms if term.canonical_id in merge_ids and term.last_seen_at]
    consolidated = CanonicalOperationalTerm(
        canonical_id=_canonical_id(label, source_terms),
        label=label,
        domain=domain,
        confidence="high" if len(source_terms) >= 4 else "medium",
        source_terms=source_terms,
        head_entity="area break",
        action_or_problem=None,
        context_modifiers=modifiers[:8],
        term_type="mixed",
        first_seen_at=min(first_seen_values) if first_seen_values else None,
        last_seen_at=max(last_seen_values) if last_seen_values else None,
        evidence_count=len(source_terms),
        boundary_confidence=boundary["confidence"],  # type: ignore[arg-type]
        boundary_reasons=list(boundary["reasons"]),
    )
    remaining = [term for term in canonical_terms if term.canonical_id not in merge_ids]
    return [consolidated, *remaining]


def canonicalize_terms(
    terms: list[str],
    domain: InferredChatDomain = "unknown",
    threads: list[OperationalThread] | None = None,
    term_quality_scores: dict[str, float] | None = None,
    term_timestamps: dict[str, list[str]] | None = None,
) -> list[CanonicalOperationalTerm]:
    scores = term_quality_scores or {}
    candidate_terms = [
        _normalize(term)
        for term in terms
        if _informative(term) and scores.get(term, scores.get(_normalize(term), 0.7)) >= 0.45
    ]
    groups = group_term_variants(candidate_terms, threads=threads)
    refined_groups: list[list[str]] = []
    for group in groups:
        label = infer_canonical_label(group)
        boundary = validate_canonical_boundary(group, label)
        if boundary["confidence"] == "low" and len(group) > 1:
            refined_groups.extend(_split_weak_boundary_group(group))
        else:
            refined_groups.append(group)
    groups = _merge_descriptive_context_groups(refined_groups)
    canonical_terms: list[CanonicalOperationalTerm] = []
    for group in groups:
        if len(group) == 1:
            single = canonicalize_term(group[0], domain)
            if single is None or single.confidence == "low":
                continue
            canonical_terms.append(single)
            continue
        label = infer_canonical_label(group)
        if not label:
            continue
        boundary = validate_canonical_boundary(group, label)
        if boundary["confidence"] == "low":
            continue
        heads = [detect_head_entity(term) for term in group if detect_head_entity(term)]
        actions = [detect_action_or_problem(term) for term in group if detect_action_or_problem(term)]
        modifiers = _unique([modifier for term in group for modifier in detect_context_modifier(term)])
        head = Counter(heads).most_common(1)[0][0] if heads else None
        action = Counter(actions).most_common(1)[0][0] if actions else None
        timestamps = [stamp for term in group for stamp in (term_timestamps or {}).get(term, [])]
        canonical_terms.append(
            CanonicalOperationalTerm(
                canonical_id=_canonical_id(label, group),
                label=label,
                domain=domain,
                confidence=_canonical_confidence(group, action, modifiers),
                source_terms=_unique(group),
                head_entity=head,
                action_or_problem=action,
                context_modifiers=modifiers[:8],
                term_type=_term_type(" ".join(group), action, modifiers),  # type: ignore[arg-type]
                first_seen_at=min(timestamps) if timestamps else None,
                last_seen_at=max(timestamps) if timestamps else None,
                evidence_count=len(group),
                boundary_confidence=boundary["confidence"],  # type: ignore[arg-type]
                boundary_reasons=list(boundary["reasons"]),
            )
        )
    canonical_terms = _consolidate_descriptive_canonical_terms(canonical_terms, candidate_terms, domain)
    return sorted(canonical_terms, key=lambda item: (item.confidence != "high", -item.evidence_count, item.label))[:30]
