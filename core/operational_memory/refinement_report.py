"""Operational Refinement Report — a private, parallel report (NOT the operational
briefing) that answers a different question: *how well did Genesi understand the
chat?* It surfaces reliability, ambiguities, possible false positives, duplicates/
conflicts, people/roles, media/OCR outcomes, technical caveats and suggested human
checks.

Deterministic (no LLM): everything is derived from the persisted operational state
and the raw events. Generic and domain-agnostic — no chat/group/profession token is
hardcoded. It never emits secrets/tokens and never replaces the operational report.
"""

from __future__ import annotations

from typing import Iterable, Optional

from core.operational_memory.models import OperationalEvent, OperationalItem, OperationalState
from core.operational_memory.quality import is_non_operational_note, should_verify_item
from core.operational_memory.query_engine import (
    active_decisions,
    answered_questions,
    attention_items,
    completed_tasks,
    open_issues,
    open_tasks,
    reopened_issues,
    resolved_issues,
    stale_items,
    superseded_items,
    unanswered_questions,
)


_CATEGORY_FIELDS = [
    ("task", "tasks"),
    ("issue", "issues"),
    ("decision", "decisions"),
    ("question", "open_questions"),
    ("information", "information"),
]

_OCR_OK = {"text_extracted"}
_OCR_EMPTY = {"no_text_found", "pdf_text_unavailable", "unsupported", "ignored"}
_OCR_FAIL = {"file_missing", "rejected_path", "analysis_error"}


def _all_items(state: OperationalState) -> Iterable[tuple[str, OperationalItem]]:
    for category, field in _CATEGORY_FIELDS:
        for item in getattr(state, field):
            yield category, item


def _confidence_of(item: OperationalItem) -> str:
    if item.lifecycle is not None and item.lifecycle.confidence:
        return item.lifecycle.confidence
    return item.confidence or "medium"


def _short(text: str, limit: int = 80) -> str:
    cleaned = " ".join((text or "").split())
    return cleaned[: limit - 1] + "…" if len(cleaned) > limit else cleaned


def _event_status(event: OperationalEvent) -> str:
    meta = event.attachment_metadata or {}
    return str(meta.get("extraction_status") or event.extraction_status or "")


def build_refinement_report(state: OperationalState, events: Optional[list[OperationalEvent]] = None) -> str:
    """Return the refinement report as Markdown for a given operational state
    (+ optional raw events for the media/OCR section)."""
    events = events or []
    items = list(_all_items(state))
    total = len(items)

    conf_counts = {"high": 0, "medium": 0, "low": 0}
    for _cat, item in items:
        conf_counts[_confidence_of(item)] = conf_counts.get(_confidence_of(item), 0) + 1

    low_conf = [(c, it) for c, it in items if _confidence_of(it) == "low"]
    to_verify = [(c, it) for c, it in items if should_verify_item(it)]
    non_op = [(c, it) for c, it in items if is_non_operational_note(it.text)]
    ownerless = [it for it in state.tasks if not it.owner and not it.due]
    open_q = unanswered_questions(state)

    snap = state.lifecycle_snapshot
    contradictions = list(snap.contradictions) if snap else []
    superseded_pairs = list(snap.superseded_pairs) if snap else []
    mitigated = list(snap.mitigated_issues) if snap else []
    partial_q = list(snap.partially_answered_questions) if snap else []

    # Media/OCR from events
    media_events = [e for e in events if e.type in ("image", "pdf", "document")]
    ocr_ok = [e for e in media_events if _event_status(e) in _OCR_OK]
    ocr_empty = [e for e in media_events if _event_status(e) in _OCR_EMPTY]
    ocr_fail = [e for e in media_events if _event_status(e) in _OCR_FAIL]

    people = sorted({(it.source_sender or "").strip() for _c, it in items if (it.source_sender or "").strip()})

    L: list[str] = []
    L.append(f"# Report di Affinamento Operativo — {state.project_id or 'progetto'}")
    L.append("")
    L.append("> Report privato e parallelo. NON è il report operativo. Non inviare nel gruppo.")
    L.append("")

    L.append("## 1. Sintesi affidabilità")
    L.append(f"- Eventi grezzi visti: {len(events)} · Item operativi: {total}")
    L.append(f"- Confidenza: high {conf_counts['high']} · medium {conf_counts['medium']} · low {conf_counts['low']}")
    L.append(f"- Item a bassa confidenza: {len(low_conf)} · Da verificare (debole/senza contesto): {len(to_verify)}")
    L.append("")

    L.append("## 2. Avanzamenti interpretativi")
    L.append(f"- Task aperti {len(open_tasks(state))} · completati {len(completed_tasks(state))}")
    L.append(f"- Problemi aperti {len(open_issues(state))} · risolti {len(resolved_issues(state))} · riaperti {len(reopened_issues(state))}")
    L.append(f"- Decisioni attive {len(active_decisions(state))}")
    L.append(f"- Domande aperte {len(open_q)} · risposte {len(answered_questions(state))}")
    L.append(f"- Da attenzionare {len(attention_items(state))} · stale {len(stale_items(state))}")
    L.append("")

    L.append("## 3. Possibili incomprensioni")
    if not (to_verify or ownerless or open_q or non_op):
        L.append("- Nessuna incertezza rilevante rilevata.")
    for _c, it in to_verify[:10]:
        L.append(f"- Ambiguo/poco verificabile: \"{_short(it.text)}\"")
    for it in ownerless[:10]:
        L.append(f"- Task senza owner/scadenza: \"{_short(it.text)}\"")
    for it in open_q[:10]:
        L.append(f"- Domanda aperta: \"{_short(it.text)}\"")
    for _c, it in non_op[:10]:
        L.append(f"- Nota non operativa (esclusa dagli attivi): \"{_short(it.text)}\"")
    L.append("")

    L.append("## 4. Possibili duplicati o conflitti")
    if not (contradictions or superseded_pairs or mitigated):
        L.append("- Nessun conflitto/superamento rilevato.")
    for rec in contradictions[:10]:
        L.append(f"- Contraddizione: \"{_short(rec.text)}\" vs \"{_short(rec.related_text)}\"")
    for rec in superseded_pairs[:10]:
        L.append(f"- Superato: \"{_short(rec.text)}\" → {rec.new_status}")
    for txt in mitigated[:10]:
        L.append(f"- Mitigato (non risolto): \"{_short(txt)}\"")
    L.append("")

    L.append("## 5. Persone e ruoli")
    if people:
        L.append(f"- Persone riconosciute (mittenti): {', '.join(_short(p, 30) for p in people[:20])}")
    else:
        L.append("- Nessun mittente riconosciuto negli item.")
    L.append("- Ruoli inferiti: non derivati deterministicamente (richiede revisione umana).")
    L.append("")

    L.append("## 6. Media / OCR")
    L.append(f"- Media analizzati: {len(media_events)} · OCR riusciti: {len(ocr_ok)} · senza testo: {len(ocr_empty)} · falliti: {len(ocr_fail)}")
    for e in ocr_fail[:10]:
        L.append(f"- Fallito ({_event_status(e)}): media {e.type}")
    for e in ocr_empty[:5]:
        L.append(f"- Senza testo ({_event_status(e)}): media {e.type}")
    L.append("")

    L.append("## 7. Bug tecnici e caveat")
    caveats = []
    if ocr_fail:
        caveats.append(f"{len(ocr_fail)} media con errore analyzer (file_missing/rejected_path/analysis_error).")
    pdf_unavail = [e for e in media_events if _event_status(e) == "pdf_text_unavailable"]
    if pdf_unavail:
        caveats.append(f"{len(pdf_unavail)} PDF senza estrazione testo (dipendenza PDF assente).")
    if partial_q:
        caveats.append(f"{len(partial_q)} domande parzialmente risposte.")
    if not caveats:
        caveats.append("Nessun caveat tecnico rilevato in questo stato.")
    for c in caveats:
        L.append(f"- {c}")
    L.append("")

    L.append("## 8. Azioni consigliate per Alfio")
    actions = []
    if to_verify:
        actions.append(f"Verificare manualmente {len(to_verify)} item ambigui/poco verificabili.")
    if ownerless:
        actions.append(f"Assegnare owner/scadenza a {len(ownerless)} task.")
    if open_q:
        actions.append(f"Rispondere/chiarire {len(open_q)} domande aperte.")
    if contradictions:
        actions.append(f"Risolvere {len(contradictions)} contraddizioni.")
    if ocr_fail:
        actions.append(f"Re-inviare {len(ocr_fail)} media non analizzati.")
    if not actions:
        actions.append("Nessuna azione urgente: stato coerente.")
    for i, a in enumerate(actions, 1):
        L.append(f"{i}. {a}")
    L.append("")

    return "\n".join(L).strip()


async def build_refinement_report_for_project(project_id: str) -> str:
    """Load the persisted state + events for a project and render the report."""
    from core.operational_memory.event_store import list_events
    from core.operational_memory.state_store import load_state

    state = await load_state(project_id)
    try:
        events = await list_events(project_id)
    except Exception:
        events = []
    return build_refinement_report(state, events)
