from __future__ import annotations

from core.operational_memory.models import AdaptiveChatProfile, OperationalEvent


WORKFLOW_STAGE_HINTS = {
    "problem_report": {"anomalia", "guasto", "manca", "mancano", "non funziona", "non parte", "problema", "ritardo"},
    "verification": {"controllo", "controllare", "verifica", "verificare", "test", "diagnosi"},
    "request_or_assignment": {"assegnare", "chi", "deve", "porta", "portare", "ordine", "ordinare", "serve"},
    "intervention": {"collegare", "consegnare", "installare", "intervento", "ritirare", "sistemare", "sostituire"},
    "completion": {"chiuso", "completato", "confermato", "fatto", "risolto", "sistemato", "verificato"},
    "decision": {"deciso", "decisione", "confermiamo", "spostiamo", "approvato"},
}


def _event_text(event: OperationalEvent) -> str:
    metadata = event.attachment_metadata or {}
    return " ".join(
        part
        for part in [
            event.content,
            event.extracted_text,
            event.media_description,
            str(metadata.get("description") or ""),
            str(metadata.get("simulated_ocr") or ""),
            str(metadata.get("simulated_text") or ""),
        ]
        if part
    ).lower()


def infer_workflow_patterns(events: list[OperationalEvent], profile: AdaptiveChatProfile) -> tuple[list[str], float]:
    stage_counts: dict[str, int] = {stage: 0 for stage in WORKFLOW_STAGE_HINTS}
    for event in events:
        text = _event_text(event)
        for stage, hints in WORKFLOW_STAGE_HINTS.items():
            if any(hint in text for hint in hints):
                stage_counts[stage] += 1

    ordered = [stage for stage, count in stage_counts.items() if count > 0]
    if profile.recurring_problem_terms and "problem_report" not in ordered:
        ordered.insert(0, "problem_report")
    if profile.recurring_completion_terms and "completion" not in ordered:
        ordered.append("completion")

    if not ordered:
        return [], 0.0

    confidence = min(1.0, (len(ordered) / 5) * 0.6 + (sum(stage_counts.values()) / max(1, len(events))) * 0.4)
    readable = [stage.replace("_", " ") for stage in ordered[:6]]
    return readable, round(confidence, 4)
