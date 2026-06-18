from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

from core.operational_memory.models import Domain, OperationalEvent


OPERATIVE_DOMAINS: set[Domain] = {
    "TECHNICAL_OPERATION",
    "TECHNICAL_ISSUE",
    "TASK_ASSIGNMENT",
}
DOMAIN_WEIGHTS: dict[Domain, int] = {
    "TECHNICAL_ISSUE": 95,
    "TASK_ASSIGNMENT": 85,
    "TECHNICAL_OPERATION": 75,
    "MEDIA_EVIDENCE": 65,
    "LOGISTICS": 45,
    "PERSONNEL": 25,
    "SOCIAL": 10,
    "UNKNOWN": 20,
}

_TECHNICAL_CODES_RE = re.compile(
    r"\b(?:T\d+|SS\d+|UTA|EWC\d+|ELS\d+|STF|STM|STA|IP|PD|POL-\d+|L\d+|B\d+\s*V\d+|V\d+)\b",
    re.IGNORECASE,
)
_TECHNICAL_COMPONENTS = {
    "potenziometro",
    "servomotore",
    "serranda",
    "fancoil",
    "canale",
    "plenum",
    "mandata",
    "quadro",
    "montante",
    "alimentata",
    "alimentato",
    "collegamento",
    "motore",
    "scheda",
    "sensore",
    "impianto",
    "porta",
    "scarpetta",
    "vela",
    "materiale",
    "materiali",
    "pannelli",
    "profili",
    "cartongesso",
    "stuccatura",
    "pareti",
    "vano scala",
    "posa",
    "ordine",
}
_ISSUE_TERMS = {
    "manca",
    "mancano",
    "mancante",
    "non parte",
    "non funziona",
    "non alimentata",
    "non alimentato",
    "bloccato",
    "bloccata",
    "guasto",
    "errore",
    "problema",
    "fermo",
    "rotta",
    "rotto",
}
_TASK_TERMS = {
    "iniziamo",
    "iniziare",
    "verifica",
    "verificare",
    "controlla",
    "controllare",
    "sostituire",
    "sostituiamo",
    "installare",
    "collegare",
    "configurare",
    "ripristinare",
    "assegnata",
    "assegnato",
    "chiude",
    "fare",
    "verifico",
    "confermo",
    "spostiamo",
    "spostare",
    "completata",
    "completato",
}
_LOGISTICS_TERMS = {
    "arrivo",
    "arriviamo",
    "parto",
    "partenza",
    "termini",
    "treno",
    "stazione",
    "roma",
    "viaggio",
    "consegna",
    "ritiro",
    "orario",
    "ore",
}
_PERSONNEL_TERMS = {
    "schiena",
    "salute",
    "malato",
    "malata",
    "febbre",
    "dottore",
    "ospedale",
    "personale",
    "permesso",
    "ferie",
    "bloccato con",
}
_SOCIAL_TERMS = {
    "ristorante",
    "mare",
    "battuta",
    "scherzo",
    "aperitivo",
    "cena",
    "pranzo",
    "grazie",
    "top",
    "buongiorno",
    "buonasera",
    "andiamo al mare",
    "ci vediamo",
}


@dataclass(frozen=True)
class _DomainScore:
    domain: Domain
    score: int


def _normalize(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_text).strip().lower()


def _contains_any(normalized: str, terms: set[str]) -> int:
    return sum(1 for term in terms if term in normalized)


def _event_text(event: OperationalEvent) -> str:
    parts = [
        event.content,
        event.extracted_text,
        event.media_description,
        event.attachment_metadata.get("description") if event.attachment_metadata else "",
        event.attachment_metadata.get("simulated_ocr") if event.attachment_metadata else "",
        event.attachment_metadata.get("simulated_text") if event.attachment_metadata else "",
    ]
    return " ".join(part for part in parts if part)


def _score_text(text: str, event_type: str = "text") -> list[_DomainScore]:
    normalized = _normalize(text)
    scores: Counter[str] = Counter()

    technical_code_hits = len(_TECHNICAL_CODES_RE.findall(text or ""))
    technical_component_hits = _contains_any(normalized, _TECHNICAL_COMPONENTS)
    issue_hits = _contains_any(normalized, _ISSUE_TERMS)
    task_hits = _contains_any(normalized, _TASK_TERMS)
    logistics_hits = _contains_any(normalized, _LOGISTICS_TERMS)
    personnel_hits = _contains_any(normalized, _PERSONNEL_TERMS)
    social_hits = _contains_any(normalized, _SOCIAL_TERMS)

    if technical_code_hits or technical_component_hits:
        scores["TECHNICAL_OPERATION"] += 35 + (technical_code_hits * 15) + (technical_component_hits * 8)
    if issue_hits and not personnel_hits and (technical_code_hits or technical_component_hits or issue_hits >= 1):
        scores["TECHNICAL_ISSUE"] += 55 + (issue_hits * 15) + (technical_code_hits * 10) + (technical_component_hits * 8)
    if task_hits and (technical_code_hits or technical_component_hits or "domani" in normalized or "oggi" in normalized):
        scores["TASK_ASSIGNMENT"] += 45 + (task_hits * 12) + (technical_code_hits * 8)
    if logistics_hits:
        scores["LOGISTICS"] += 30 + (logistics_hits * 12)
    if re.search(r"\b\d{1,2}[:.]\d{2}\b", normalized):
        scores["LOGISTICS"] += 18
    if personnel_hits:
        scores["PERSONNEL"] += 35 + (personnel_hits * 12)
    if social_hits:
        scores["SOCIAL"] += 20 + (social_hits * 10)
    if event_type in {"image", "pdf", "document"}:
        scores["MEDIA_EVIDENCE"] += 55

    if not scores:
        scores["UNKNOWN"] = 20

    return [
        _DomainScore(domain=domain, score=score)
        for domain, score in sorted(scores.items(), key=lambda item: item[1], reverse=True)
    ]


def classify_domains(text: str, event_type: str = "text") -> list[Domain]:
    scores = _score_text(text, event_type=event_type)
    domains = [score.domain for score in scores if score.score >= 35]
    return domains or [scores[0].domain]


def classify_domain(text: str, event_type: str = "text") -> Domain:
    return classify_domains(text, event_type=event_type)[0]


def confidence_score(text: str, domain: Domain | None = None, event_type: str = "text") -> str:
    scores = _score_text(text, event_type=event_type)
    target = domain or scores[0].domain
    score = next((item.score for item in scores if item.domain == target), 0)
    if score >= 80:
        return "high"
    if score >= 45:
        return "medium"
    return "low"


def operational_relevance_score(domain: Domain, secondary_domains: list[Domain] | None = None) -> int:
    domains = [domain, *(secondary_domains or [])]
    return min(100, max(DOMAIN_WEIGHTS.get(item, 0) for item in domains))


def classify_event(event: OperationalEvent) -> OperationalEvent:
    text = _event_text(event)
    domains = classify_domains(text, event_type=event.type)
    primary = domains[0]
    if primary == "MEDIA_EVIDENCE" and len(domains) > 1:
        primary = domains[1]
    secondary: list[Domain] = []
    if event.type in {"image", "pdf", "document"}:
        secondary.append("MEDIA_EVIDENCE")
    for domain in domains:
        if domain != primary and domain not in secondary:
            secondary.append(domain)

    event.domain = primary
    event.secondary_domains = secondary
    event.domain_confidence = confidence_score(text, primary, event_type=event.type)
    event.operational_relevance_score = operational_relevance_score(primary, secondary)
    return event


def should_extract_operationally(event: OperationalEvent) -> bool:
    domains = {event.domain, *event.secondary_domains}
    if domains & OPERATIVE_DOMAINS:
        return True
    if event.domain == "UNKNOWN":
        return True
    if event.operational_relevance_score >= 70:
        return True
    return False
