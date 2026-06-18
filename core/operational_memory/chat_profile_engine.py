from __future__ import annotations

import re
from collections import Counter, defaultdict
from datetime import datetime, timezone

from core.operational_memory.models import AdaptiveChatProfile, Confidence, InferredChatDomain, OperationalEvent, OperationalThread


STOPWORDS = {
    "anche",
    "ancora",
    "bene",
    "ciao",
    "come",
    "con",
    "da",
    "dai",
    "davvero",
    "del",
    "della",
    "delle",
    "dello",
    "dentro",
    "disponibile",
    "dopo",
    "dove",
    "fare",
    "fatto",
    "fai",
    "grazie",
    "allegato",
    "adesso",
    "allora",
    "avere",
    "bisogno",
    "compagnia",
    "il",
    "in",
    "ieri",
    "immagine",
    "importato",
    "locale",
    "la",
    "le",
    "lo",
    "offline",
    "ocr",
    "oggi",
    "ok",
    "ora",
    "parte",
    "per",
    "poi",
    "proprio",
    "qualcosa",
    "qui",
    "questo",
    "quindi",
    "se",
    "si",
    "sono",
    "sulla",
    "tutto",
    "una",
    "uno",
    "whatsapp",
}

DOMAIN_HINTS: dict[InferredChatDomain, set[str]] = {
    "construction_site": {"cantiere", "posa", "materiale", "impianto", "piano", "porta", "montaggio", "canale"},
    "maintenance": {"guasto", "intervento", "riparare", "verifica", "sostituire", "funziona", "anomalia"},
    "engineering": {"schema", "collaudo", "configurazione", "test", "impianto", "sistema", "linea"},
    "logistics": {"consegna", "ritiro", "ordine", "magazzino", "corriere", "mezzo", "ritardo", "ddt"},
    "sales": {"cliente", "offerta", "preventivo", "contratto", "prezzo", "negoziazione", "lead"},
    "customer_support": {"ticket", "cliente", "assistenza", "problema", "diagnosi", "chiuso", "segnalazione"},
    "family_coordination": {"scuola", "spesa", "bambini", "casa", "cena", "bolletta", "nonna"},
    "school": {"classe", "compiti", "prof", "lezione", "scuola", "riunione"},
    "travel": {"treno", "volo", "hotel", "aeroporto", "stazione", "biglietto"},
    "event_planning": {"evento", "sala", "ospiti", "catering", "programma", "inviti"},
}
ACTION_TERMS = {
    "assegnare",
    "chiamare",
    "chiudere",
    "collegare",
    "confermare",
    "consegnare",
    "controllare",
    "fare",
    "installare",
    "ordinare",
    "portare",
    "preparare",
    "ritirare",
    "sistemare",
    "sostituire",
    "verificare",
}
OBJECT_TERMS = {
    "accesso",
    "acqua",
    "bolletta",
    "camion",
    "canale",
    "cliente",
    "compiti",
    "consegna",
    "errore",
    "fancoil",
    "griglia",
    "login",
    "magazzino",
    "montante",
    "ordine",
    "porta",
    "portata",
    "potenziometro",
    "pressione",
    "rumore",
    "scuola",
    "serranda",
    "spesa",
    "ticket",
    "visita",
}
PROBLEM_TERMS = {
    "anomalia",
    "bloccato",
    "errore",
    "guasto",
    "manca",
    "mancano",
    "problema",
    "ritardo",
    "rotto",
    "non funziona",
    "non parte",
}
COMPLETION_TERMS = {"chiuso", "completato", "confermato", "fatto", "funziona", "risolto", "sistemato", "verificato"}
LOCATION_HINT_RE = re.compile(r"\b(?:piano|porta|magazzino|scuola|casa|stazione|aeroporto|sala|ufficio)\s+\w+\b", re.IGNORECASE)
TOKEN_RE = re.compile(r"\b[\w][\w.-]{1,}\b", re.IGNORECASE)
CODE_RE = re.compile(r"\b(?:[a-z]{1,5}[-]?\d{1,5}|\d{1,5}[a-z]{1,4})\b", re.IGNORECASE)
BAD_EDGE_TERMS = STOPWORDS | {"avere", "era", "andando", "sta"}
BAD_CONNECTOR_TERMS = {"avere", "allora", "qualcosa", "proprio", "bisogno", "compagnia"}


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _event_text(event: OperationalEvent) -> str:
    metadata = event.attachment_metadata or {}
    parts = [
        event.content,
        event.extracted_text,
        event.media_description,
        str(metadata.get("description") or ""),
        str(metadata.get("simulated_ocr") or ""),
        str(metadata.get("simulated_text") or ""),
    ]
    text = " ".join(part for part in parts if part)
    lowered = _normalize(text)
    if "ha creato questo gruppo" in lowered or ("fai parte" in lowered and "gruppo" in lowered):
        return ""
    return text


def _tokenize(text: str) -> list[str]:
    tokens = []
    for token in TOKEN_RE.findall(_normalize(text)):
        if re.search(r"\.(?:jpg|jpeg|png|webp|pdf|docx?)$", token):
            continue
        if re.fullmatch(r"\d{3,5}x\d{3,5}", token):
            continue
        if len(token) > 30:
            continue
        if token in STOPWORDS or len(token) < 2:
            continue
        tokens.append(token)
    return tokens


def clean_candidate_term(term: str) -> str:
    tokens = _tokenize(term)
    while tokens and tokens[0] in BAD_EDGE_TERMS:
        tokens.pop(0)
    while tokens and tokens[-1] in BAD_EDGE_TERMS:
        tokens.pop()
    return " ".join(tokens)


def calculate_phrase_cohesion(term: str) -> float:
    tokens = clean_candidate_term(term).split()
    if not tokens:
        return 0.0
    if len(tokens) == 1:
        token = tokens[0]
        if token in STOPWORDS:
            return 0.0
        if CODE_RE.search(token) or token in OBJECT_TERMS or token in ACTION_TERMS or token in PROBLEM_TERMS:
            return 0.8
        return 0.45
    stopword_ratio = len([token for token in tokens if token in STOPWORDS]) / len(tokens)
    has_signal = any(token in OBJECT_TERMS or token in ACTION_TERMS or token in PROBLEM_TERMS or CODE_RE.search(token) for token in tokens)
    has_problem_or_action = any(token in ACTION_TERMS or token in PROBLEM_TERMS for token in tokens)
    score = 0.45
    if has_signal:
        score += 0.25
    if has_problem_or_action:
        score += 0.15
    if len(tokens) >= 3:
        score += 0.10
    score -= stopword_ratio * 0.5
    return round(max(0.0, min(1.0, score)), 4)


def is_operational_term(term: str) -> bool:
    cleaned = clean_candidate_term(term)
    if not cleaned:
        return False
    tokens = cleaned.split()
    if cleaned in STOPWORDS:
        return False
    if CODE_RE.search(cleaned):
        return True
    if any(token in OBJECT_TERMS for token in tokens):
        return True
    if any(token in ACTION_TERMS or token in PROBLEM_TERMS or token in COMPLETION_TERMS for token in tokens):
        return True
    return False


def is_linguistic_fragment(term: str) -> bool:
    raw_tokens = _normalize(term).split()
    if raw_tokens and (raw_tokens[0] in BAD_EDGE_TERMS or raw_tokens[-1] in BAD_EDGE_TERMS):
        return True
    cleaned = clean_candidate_term(term)
    tokens = cleaned.split()
    if not tokens:
        return True
    if cleaned in STOPWORDS or cleaned in {"non", "ok", "si", "ciao", "fatto"}:
        return True
    if len(tokens) == 1:
        token = tokens[0]
        if token.isdigit() and not CODE_RE.search(token):
            return True
        return not is_operational_term(token)
    if any(token in BAD_CONNECTOR_TERMS for token in _normalize(term).split()):
        return True
    if tokens[0] in BAD_EDGE_TERMS or tokens[-1] in BAD_EDGE_TERMS:
        return True
    if any(token.isdigit() for token in tokens) and any(token in STOPWORDS for token in tokens):
        return True
    return calculate_phrase_cohesion(cleaned) < 0.55


def calculate_term_quality_score(term: str, specificity: float = 0.0, recurrence: int = 1) -> float:
    cleaned = clean_candidate_term(term)
    if not cleaned or is_linguistic_fragment(cleaned):
        return 0.0
    cohesion = calculate_phrase_cohesion(cleaned)
    recurrence_bonus = min(0.15, max(0, recurrence - 1) * 0.05)
    signal_bonus = 0.15 if is_operational_term(cleaned) else 0.0
    return round(min(1.0, (cohesion * 0.45) + (specificity * 0.35) + recurrence_bonus + signal_bonus), 4)


def _rejection_reason(term: str) -> str:
    cleaned = clean_candidate_term(term)
    if not cleaned:
        return "empty_after_cleaning"
    tokens = cleaned.split()
    if cleaned in STOPWORDS or cleaned in {"non", "ok", "si", "ciao", "fatto"}:
        return "stopword_or_social_fragment"
    if any(token.isdigit() for token in tokens) and any(token in STOPWORDS for token in tokens):
        return "numeric_stopword_fragment"
    if calculate_phrase_cohesion(cleaned) < 0.55:
        return "low_phrase_cohesion"
    return "low_operational_quality"


def extract_candidate_phrases(tokens: list[str]) -> list[str]:
    candidates: list[str] = []
    for size in (1, 2, 3):
        for idx in range(0, max(0, len(tokens) - size + 1)):
            phrase = clean_candidate_term(" ".join(tokens[idx: idx + size]))
            if phrase:
                candidates.append(phrase)
    return candidates


def _identifier_phrases(tokens: list[str]) -> list[str]:
    phrases = []
    for left, right in zip(tokens, tokens[1:]):
        if any(char.isdigit() for char in left) or any(char.isdigit() for char in right):
            phrase = clean_candidate_term(f"{left} {right}")
            if phrase:
                phrases.append(phrase)
    return phrases


def _thread_distribution(threads: list[OperationalThread]) -> dict[str, set[str]]:
    by_term: dict[str, set[str]] = defaultdict(set)
    for thread in threads:
        terms = set(_tokenize(" ".join([thread.title, *thread.context_tags, *thread.related_tasks, *thread.related_issues])))
        for term in terms:
            by_term[term].add(thread.thread_id)
    return by_term


def calculate_term_specificity(
    term: str,
    event_term_counts: Counter[str],
    total_events: int,
    thread_distribution: dict[str, set[str]] | None = None,
) -> float:
    if total_events <= 0:
        return 0.0
    frequency_ratio = event_term_counts.get(term, 0) / total_events
    thread_count = len((thread_distribution or {}).get(term, set()))
    if frequency_ratio <= 0:
        return 0.0
    rarity_score = max(0.0, 1.0 - frequency_ratio)
    thread_focus = 1.0 / thread_count if thread_count else 0.7
    length_bonus = 0.25 if len(term.split()) > 1 or any(char.isdigit() for char in term) else 0.0
    return round(min(1.0, (rarity_score * 0.65) + (thread_focus * 0.25) + length_bonus), 4)


def _infer_domain(tokens: list[str]) -> tuple[InferredChatDomain, Confidence]:
    token_set = set(tokens)
    scores = {
        domain: len(token_set & hints)
        for domain, hints in DOMAIN_HINTS.items()
    }
    best_domain, best_score = max(scores.items(), key=lambda item: item[1])
    if best_score <= 0:
        return "generic_group_chat" if len(tokens) >= 20 else "unknown", "low"
    if best_score >= 4:
        return best_domain, "high"
    if best_score >= 2:
        return best_domain, "medium"
    return best_domain, "low"


def _top(counter: Counter[str], limit: int = 12, minimum: int = 1) -> list[str]:
    return [value for value, count in counter.most_common() if count >= minimum][:limit]


def _people(events: list[OperationalEvent]) -> list[str]:
    counter = Counter(event.sender for event in events if event.sender)
    return _top(counter, limit=12, minimum=1)


def _question_patterns(texts: list[str]) -> list[str]:
    patterns = []
    joined = "\n".join(texts).lower()
    for phrase in ("quando", "chi", "dove", "confermi", "serve", "possiamo", "quanto"):
        if phrase in joined:
            patterns.append(phrase)
    if any("?" in text for text in texts):
        patterns.append("domanda esplicita")
    return patterns[:8]


def build_adaptive_chat_profile(
    project_id: str,
    events: list[OperationalEvent],
    threads: list[OperationalThread] | None = None,
) -> AdaptiveChatProfile:
    threads = threads or []
    texts = [_event_text(event) for event in events]
    tokenized = [_tokenize(text) for text in texts]
    all_tokens = [token for tokens in tokenized for token in tokens]
    token_counter = Counter(all_tokens)
    phrase_counter = Counter(phrase for tokens in tokenized for phrase in extract_candidate_phrases(tokens))
    event_term_counts: Counter[str] = Counter()
    for tokens in tokenized:
        for term in set([*extract_candidate_phrases(tokens), *_identifier_phrases(tokens)]):
            event_term_counts[term] += 1
    thread_terms = _thread_distribution(threads)
    specificity = {
        term: calculate_term_specificity(term, event_term_counts, len(events), thread_terms)
        for term in event_term_counts
        if event_term_counts[term] >= 1
    }
    term_quality_scores = {
        term: calculate_term_quality_score(term, specificity.get(term, 0), event_term_counts[term])
        for term in event_term_counts
    }
    rejected_terms = [
        term
        for term, quality in sorted(term_quality_scores.items(), key=lambda item: (item[1], item[0]))
        if quality <= 0 or is_linguistic_fragment(term)
    ][:40]
    rejection_reasons = {term: _rejection_reason(term) for term in rejected_terms}
    recurring_terms = [
        term
        for term, count in event_term_counts.most_common()
        if count >= 2 and term_quality_scores.get(term, 0) > 0
    ]
    generic_terms = [
        term
        for term in recurring_terms
        if term not in STOPWORDS
        and term_quality_scores.get(term, 0) >= 0.45
        and specificity.get(term, 0) < 0.48
        and event_term_counts[term] >= max(2, int(len(events) * 0.12))
    ][:20]
    specific_terms = [
        term
        for term, score in sorted(specificity.items(), key=lambda item: item[1], reverse=True)
        if score >= 0.72 and term not in generic_terms and term_quality_scores.get(term, 0) >= 0.62
    ][:25]
    domain, confidence = _infer_domain(all_tokens)
    lower_text = "\n".join(texts).lower()
    problem_terms = [term for term in PROBLEM_TERMS if term in lower_text]
    completion_terms = [term for term in COMPLETION_TERMS if term in lower_text]
    action_terms = [term for term in ACTION_TERMS if term in set(all_tokens) or term in lower_text]
    locations = _top(Counter(match.group(0).lower() for text in texts for match in LOCATION_HINT_RE.finditer(text)), limit=12)
    topic_candidates = [
        phrase
        for phrase, count in phrase_counter.most_common()
        if count >= 2 and term_quality_scores.get(phrase, 0) >= 0.55 and not is_linguistic_fragment(phrase)
    ][:20]
    objects = [term for term in specific_terms if any(char.isdigit() for char in term) or len(term.split()) > 1][:15]
    return AdaptiveChatProfile(
        project_id=project_id,
        inferred_domain=domain,
        domain_confidence=confidence,
        recurring_entities=_top(token_counter, limit=20, minimum=2),
        recurring_locations=locations,
        recurring_people=_people(events),
        recurring_objects=objects,
        recurring_actions=action_terms[:15],
        recurring_problem_terms=problem_terms[:15],
        recurring_completion_terms=completion_terms[:15],
        recurring_question_patterns=_question_patterns(texts),
        generic_terms=generic_terms,
        specific_terms=specific_terms,
        topic_candidates=topic_candidates,
        workflow_patterns=[],
        term_specificity=specificity,
        term_quality_scores=term_quality_scores,
        rejected_terms=rejected_terms,
        rejection_reasons=rejection_reasons,
        last_updated_at=datetime.now(timezone.utc).isoformat(),
    )
    "area",
    "break",
