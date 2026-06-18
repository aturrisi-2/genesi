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
    "dai",
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
    "ieri",
    "immagine",
    "importato",
    "locale",
    "offline",
    "ocr",
    "oggi",
    "ok",
    "ora",
    "parte",
    "per",
    "poi",
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


def _bigrams(tokens: list[str]) -> list[str]:
    return [f"{left} {right}" for left, right in zip(tokens, tokens[1:]) if left not in STOPWORDS and right not in STOPWORDS]


def _identifier_phrases(tokens: list[str]) -> list[str]:
    phrases = []
    for left, right in zip(tokens, tokens[1:]):
        if any(char.isdigit() for char in left) or any(char.isdigit() for char in right):
            phrases.append(f"{left} {right}")
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
    phrase_counter = Counter(phrase for tokens in tokenized for phrase in [*_bigrams(tokens), *_identifier_phrases(tokens)])
    event_term_counts: Counter[str] = Counter()
    for tokens in tokenized:
        for term in set([*tokens, *_bigrams(tokens), *_identifier_phrases(tokens)]):
            event_term_counts[term] += 1
    thread_terms = _thread_distribution(threads)
    specificity = {
        term: calculate_term_specificity(term, event_term_counts, len(events), thread_terms)
        for term in event_term_counts
        if event_term_counts[term] >= 1
    }
    recurring_terms = [term for term, count in event_term_counts.most_common() if count >= 2]
    generic_terms = [
        term
        for term in recurring_terms
        if specificity.get(term, 0) < 0.48 and event_term_counts[term] >= max(2, int(len(events) * 0.12))
    ][:20]
    specific_terms = [
        term
        for term, score in sorted(specificity.items(), key=lambda item: item[1], reverse=True)
        if score >= 0.72 and term not in generic_terms
    ][:25]
    domain, confidence = _infer_domain(all_tokens)
    lower_text = "\n".join(texts).lower()
    problem_terms = [term for term in PROBLEM_TERMS if term in lower_text]
    completion_terms = [term for term in COMPLETION_TERMS if term in lower_text]
    action_terms = [term for term in ACTION_TERMS if term in set(all_tokens) or term in lower_text]
    locations = _top(Counter(match.group(0).lower() for text in texts for match in LOCATION_HINT_RE.finditer(text)), limit=12)
    topic_candidates = _top(phrase_counter, limit=20, minimum=2)
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
        last_updated_at=datetime.now(timezone.utc).isoformat(),
    )
