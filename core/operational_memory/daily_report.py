from __future__ import annotations

from datetime import datetime, timezone

from core.operational_memory.event_store import list_events
from core.operational_memory.models import (
    AdaptiveChatProfile,
    DailyReport,
    Domain,
    OperationalEvent,
    OperationalItem,
    OperationalMacroThread,
    OperationalState,
    OperationalThread,
    ReportMode,
    ThreadRelationCandidate,
)
from core.operational_memory.lifecycle_engine import build_operational_snapshot
from core.operational_memory.project_impact import classify_impact_level
from core.operational_memory.quality import (
    has_item_context,
    is_technically_significant,
    next_action_priority,
    should_include_in_report,
    should_verify_item,
)
from core.operational_memory.state_store import load_state


def _format_timestamp(value: str | None) -> str:
    if not value:
        return "data non disponibile"
    try:
        normalized = value.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        return parsed.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return value


def _context_label(item: OperationalItem) -> str:
    parts = []
    if item.context_system:
        parts.append(item.context_system)
    if item.context_area:
        parts.append(item.context_area)
    if item.context_level:
        parts.append(item.context_level)
    if item.context_location:
        parts.append(item.context_location)
    for tag in item.context_tags:
        if tag not in parts:
            parts.append(tag)
    return " / ".join(parts) if parts else "contesto non rilevato"


def _origin_label(item: OperationalItem) -> str:
    sender = item.source_sender or "autore non disponibile"
    return f"{sender}, {_format_timestamp(item.source_timestamp)}"


def _excerpt_label(item: OperationalItem) -> str:
    excerpt = (item.source_excerpt or item.text).strip()
    if len(excerpt) > 180:
        excerpt = excerpt[:177].rstrip() + "..."
    return f'"{excerpt}"'


def _item_label(item: OperationalItem, kind: str) -> str:
    lines = [
        f"[{kind}] {item.text}",
        f"  Contesto: {_context_label(item)}",
        f"  Origine: {_origin_label(item)}",
        f"  Intent: {item.intent or 'non classificato'}",
        f"  Estratto: {_excerpt_label(item)}",
    ]
    owner = getattr(item, "owner", None)
    due = getattr(item, "due", None)
    if owner or due:
        task_bits = []
        if owner:
            task_bits.append(f"owner: {owner}")
        if due:
            task_bits.append(f"due: {due}")
        lines.insert(1, f"  Task: {' | '.join(task_bits)}")
    return "\n".join(lines)


def _task_label(task) -> str:
    return _item_label(task, "TASK")


def _thread_next_action(thread: OperationalThread) -> str:
    if thread.status == "waiting":
        return "sbloccare attesa o conferma tecnica"
    if thread.unresolved_questions:
        return f"rispondere a: {thread.unresolved_questions[0]}"
    if thread.related_issues and not thread.related_tasks:
        return "definire piano di risoluzione"
    if thread.related_tasks:
        return "verificare avanzamento task collegati"
    if thread.status == "stale":
        return "verificare se il tema e ancora aperto"
    return "monitorare prossimo aggiornamento operativo"


def _thread_label(thread: OperationalThread, event_by_id: dict[str, OperationalEvent]) -> str:
    context = " / ".join(thread.context_tags[:8]) if thread.context_tags else "contesto non rilevato"
    event_lines = []
    for event_id in thread.related_event_ids[:8]:
        event = event_by_id.get(event_id)
        text = (event.content or event.extracted_text or event.media_description or event_id).strip() if event else event_id
        text = " ".join(text.split())
        if len(text) > 120:
            text = text[:117].rstrip() + "..."
        event_lines.append(f"    - {text}")
    if not event_lines:
        event_lines.append("    - Nessun evento collegato")
    return "\n".join(
        [
            f"[THREAD] {thread.title}",
            f"  Stato: {thread.status}",
            f"  Impatto: {classify_impact_level(thread.project_impact_score)} ({thread.project_impact_score})",
            f"  Contesto: {context}",
            f"  Creato per: {thread.creation_reason or 'evento operativo sopra soglia'}",
            f"  Confidenza raggruppamento: {thread.grouping_confidence}",
            f"  Segnali continuita: {'; '.join(thread.continuity_signals) if thread.continuity_signals else 'non disponibili'}",
            f"  Segnali chiusura: {'; '.join(thread.resolution_signals) if thread.resolution_signals else 'nessuno'}",
            f"  Thread passati collegati: {', '.join(thread.related_past_thread_ids) if thread.related_past_thread_ids else 'nessuno'}",
            f"  Prima segnalazione: {_format_timestamp(thread.started_at)}",
            f"  Ultimo aggiornamento: {_format_timestamp(thread.last_updated_at)}",
            f"  Eventi collegati: {len(thread.related_event_ids)}",
            *event_lines,
            f"  Task collegati: {len(thread.related_tasks)}",
            f"  Problemi collegati: {len(thread.related_issues)}",
            f"  Media collegati: {len(thread.related_media)}",
            f"  Prossima azione: {_thread_next_action(thread)}",
        ]
    )


def _macro_next_action(macro: OperationalMacroThread, child_threads: list[OperationalThread]) -> str:
    unresolved = [thread for thread in child_threads if thread.status in {"open", "in_progress", "waiting", "stale"}]
    if not unresolved:
        return "verificare chiusura finale del macro-tema"
    critical = [thread for thread in unresolved if thread.project_impact_score >= 80]
    if critical:
        return f"prioritizzare sottothread critico: {critical[0].title}"
    return f"verificare avanzamento sottothread: {unresolved[0].title}"


def _macro_label(macro: OperationalMacroThread, thread_by_id: dict[str, OperationalThread]) -> str:
    child_threads = [thread_by_id[thread_id] for thread_id in macro.child_thread_ids if thread_id in thread_by_id]
    context = " / ".join(macro.context_tags[:10]) if macro.context_tags else "contesto non rilevato"
    child_lines = [f"    - {thread.title} ({thread.status})" for thread in child_threads[:10]]
    if not child_lines:
        child_lines.append("    - Nessun sottothread collegato")
    return "\n".join(
        [
            f"[MACRO] {macro.title}",
            f"  Stato: {macro.status}",
            f"  Confidenza: {macro.confidence}",
            f"  Boundary macro: {macro.boundary_confidence}",
            f"  Contesto: {context}",
            f"  Creato per: {macro.creation_reason or 'pattern adattivo condiviso'}",
            f"  Pattern adattivi: {'; '.join(macro.adaptive_patterns) if macro.adaptive_patterns else 'non disponibili'}",
            f"  Motivi boundary: {'; '.join(macro.macro_boundary_reasons) if macro.macro_boundary_reasons else 'non disponibili'}",
            f"  Raccomandazione split: {macro.split_recommendation or 'nessuna'}",
            f"  Termini generici ignorati: {', '.join(macro.ignored_generic_terms) if macro.ignored_generic_terms else 'nessuno'}",
            f"  Sottothread: {len(macro.child_thread_ids)}",
            f"  Criticita: {macro.critical_items_count}",
            f"  Task aperti: {macro.open_items_count}",
            f"  Prima segnalazione: {_format_timestamp(macro.started_at)}",
            f"  Ultimo aggiornamento: {_format_timestamp(macro.last_updated_at)}",
            "  Sottothread collegati:",
            *child_lines,
            f"  Sintesi: {macro.summary}",
            f"  Prossima azione macro: {_macro_next_action(macro, child_threads)}",
        ]
    )


def _relation_status(relation: ThreadRelationCandidate) -> str:
    if relation.should_promote_to_macro:
        return "promosso a macro"
    if relation.should_remain_candidate:
        return "candidato, non promosso a macro"
    return "scartato"


def _relation_next_action(relation: ThreadRelationCandidate) -> str:
    if relation.should_promote_to_macro:
        return "verificare se la promozione macro resta coerente nel tempo"
    if relation.confidence == "medium":
        return "osservare prossimi aggiornamenti prima di fondere"
    return "nessuna azione: segnale insufficiente"


def _relation_label(relation: ThreadRelationCandidate, thread_by_id: dict[str, OperationalThread]) -> str:
    source = thread_by_id.get(relation.source_thread_id)
    target = thread_by_id.get(relation.target_thread_id)
    evidence = relation.evidence or relation.rejection_reasons or ["nessuna evidenza leggibile"]
    return "\n".join(
        [
            "[RELATION CANDIDATE]",
            f"  Thread A: {source.title if source else relation.source_thread_id}",
            f"  Thread B: {target.title if target else relation.target_thread_id}",
            f"  Tipo: {relation.relation_type}",
            f"  Confidenza: {relation.confidence}",
            f"  Score: {relation.score:.2f}",
            f"  Motivo: {'; '.join(evidence)}",
            f"  Stato: {_relation_status(relation)}",
            f"  Prossima azione: {_relation_next_action(relation)}",
        ]
    )


def _profile_label(profile: AdaptiveChatProfile | None) -> list[str]:
    if profile is None:
        return ["Profilo non ancora disponibile"]
    workflow = " -> ".join(profile.workflow_patterns) if profile.workflow_patterns else "non rilevato"
    rejected = [
        f"{term} ({profile.rejection_reasons.get(term, 'rejected')})"
        for term in profile.rejected_terms[:10]
    ]
    canonical_lines = []
    for canonical in profile.canonical_terms[:8]:
        variants = ", ".join(canonical.source_terms[:5]) if canonical.source_terms else "nessuna variante"
        boundary = f"Boundary: {canonical.boundary_confidence}"
        canonical_lines.append(f"{canonical.label} | Varianti: {variants} | Confidenza: {canonical.confidence} | {boundary}")
    canonical_source_terms = {term for canonical in profile.canonical_terms for term in canonical.source_terms}
    non_canonical_raw = [
        term
        for term in profile.specific_terms[:20]
        if term not in canonical_source_terms and term not in profile.canonical_topic_candidates
    ][:10]
    normalization_examples = [
        f"{', '.join(canonical.source_terms[:3])} -> {canonical.label}"
        for canonical in profile.canonical_terms[:5]
        if canonical.source_terms
    ]
    return [
        f"Dominio inferito: {profile.inferred_domain} ({profile.domain_confidence})",
        f"Termini generici rilevati: {', '.join(profile.generic_terms[:12]) if profile.generic_terms else 'nessuno'}",
        f"Termini specifici rilevati: {', '.join(profile.specific_terms[:12]) if profile.specific_terms else 'nessuno'}",
        f"Termini canonici rilevati: {'; '.join(canonical_lines) if canonical_lines else 'nessuno'}",
        f"Confidenza canonicalizzazione: {profile.canonicalization_confidence}",
        f"Termini grezzi non canonizzati: {', '.join(non_canonical_raw) if non_canonical_raw else 'nessuno'}",
        f"Esempi normalizzazione: {'; '.join(normalization_examples) if normalization_examples else 'nessuno'}",
        f"Termini scartati principali: {', '.join(rejected) if rejected else 'nessuno'}",
        f"Workflow probabile: {workflow}",
        f"Pattern problema: {', '.join(profile.recurring_problem_terms[:10]) if profile.recurring_problem_terms else 'nessuno'}",
        f"Pattern completamento: {', '.join(profile.recurring_completion_terms[:10]) if profile.recurring_completion_terms else 'nessuno'}",
        f"Topic candidati: {', '.join(profile.topic_candidates[:10]) if profile.topic_candidates else 'nessuno'}",
    ]


def _next_actions(
    state: OperationalState,
    event_by_id: dict[str, OperationalEvent] | None = None,
    report_mode: ReportMode = "OPERATIVE_ONLY",
) -> list[str]:
    prioritized: list[tuple[int, str]] = []
    seen: set[str] = set()

    def add(priority: int, action: str) -> None:
        key = action.strip().lower()
        if not key or key in seen:
            return
        seen.add(key)
        prioritized.append((priority, action))

    event_by_id = event_by_id or {}
    reportable_issues = [
        issue for issue in state.issues if should_include_in_report(issue) and _item_allowed(issue, event_by_id, report_mode)
    ]
    reportable_tasks = [
        task for task in state.tasks if should_include_in_report(task) and _item_allowed(task, event_by_id, report_mode)
    ]
    reportable_questions = [
        question
        for question in state.open_questions
        if should_include_in_report(question) and _item_allowed(question, event_by_id, report_mode)
    ]

    for issue in reportable_issues:
        add(next_action_priority(issue), f"Chiarire piano di risoluzione: {issue.text}")

    for task in reportable_tasks:
        if getattr(task, "status", "open") != "open":
            continue
        if not task.due:
            add(next_action_priority(task), f"Definire una scadenza: {task.text}")
        if not task.owner:
            add(next_action_priority(task) + 10, f"Assegnare un responsabile: {task.text}")

    for question in reportable_questions:
        add(next_action_priority(question), f"Rispondere alla domanda tecnica aperta: {question.text}")

    return [action for _priority, action in sorted(prioritized, key=lambda item: item[0])[:10]]


def _allowed_domains(report_mode: ReportMode) -> set[Domain]:
    operative: set[Domain] = {"TECHNICAL_OPERATION", "TECHNICAL_ISSUE", "TASK_ASSIGNMENT"}
    if report_mode == "OPERATIVE_PLUS_LOGISTICS":
        return {*operative, "LOGISTICS_OPERATIONAL"}
    if report_mode == "FULL_CONTEXT":
        return {
            "TECHNICAL_OPERATION",
            "TECHNICAL_ISSUE",
            "TASK_ASSIGNMENT",
            "LOGISTICS_OPERATIONAL",
            "LOGISTICS_PERSONAL",
            "PERSONNEL",
            "SOCIAL",
            "MEDIA_EVIDENCE",
            "UNKNOWN",
        }
    return operative


def _event_domains(event: OperationalEvent) -> set[Domain]:
    return {event.domain, *event.secondary_domains}


def _item_allowed(item: OperationalItem, event_by_id: dict[str, OperationalEvent], report_mode: ReportMode) -> bool:
    if not item.source_event_id:
        if report_mode == "OPERATIVE_ONLY":
            return is_technically_significant(item.text)
        return True
    event = event_by_id.get(item.source_event_id)
    if event is None:
        if report_mode == "OPERATIVE_ONLY":
            return is_technically_significant(item.text)
        return True
    return _event_allowed(event, report_mode)


def _event_allowed(event: OperationalEvent, report_mode: ReportMode) -> bool:
    domains = _event_domains(event)
    if report_mode == "OPERATIVE_ONLY" and event.project_impact_score < 50:
        return False
    if report_mode == "OPERATIVE_ONLY" and event.operational_relevance_score < 50:
        return False
    if report_mode == "OPERATIVE_ONLY" and domains & {"LOGISTICS_PERSONAL", "PERSONNEL", "SOCIAL"}:
        if not domains & {"TECHNICAL_ISSUE", "TASK_ASSIGNMENT"}:
            return False
    if report_mode == "OPERATIVE_PLUS_LOGISTICS" and event.project_impact_score < 20:
        return False
    return bool(domains & _allowed_domains(report_mode))


def _thread_allowed(thread: OperationalThread, event_by_id: dict[str, OperationalEvent], report_mode: ReportMode) -> bool:
    if report_mode != "OPERATIVE_ONLY":
        return True
    return any(_event_allowed(event_by_id[event_id], report_mode) for event_id in thread.related_event_ids if event_id in event_by_id)


def _macro_allowed(
    macro: OperationalMacroThread,
    thread_by_id: dict[str, OperationalThread],
    event_by_id: dict[str, OperationalEvent],
    report_mode: ReportMode,
) -> bool:
    if report_mode != "OPERATIVE_ONLY":
        return True
    return any(
        thread_id in thread_by_id and _thread_allowed(thread_by_id[thread_id], event_by_id, report_mode)
        for thread_id in macro.child_thread_ids
    )


def _noise_summary(events: list[OperationalEvent], report_mode: ReportMode) -> list[str]:
    allowed = _allowed_domains(report_mode)
    excluded = [event for event in events if not (_event_domains(event) & allowed)]

    def count(domain: Domain) -> int:
        return len([event for event in excluded if domain in _event_domains(event)])

    return [
        f"Eventi social esclusi: {count('SOCIAL')}",
        f"Eventi logistici personali esclusi: {count('LOGISTICS_PERSONAL')}",
        f"Eventi logistici operativi esclusi: {count('LOGISTICS_OPERATIONAL')}",
        f"Eventi personali esclusi: {count('PERSONNEL')}",
    ]


def _impact_statistics(events: list[OperationalEvent], report_mode: ReportMode) -> list[str]:
    low_impact_excluded = len(
        [
            event
            for event in events
            if event.project_impact_score < 50 and not _event_allowed(event, report_mode)
        ]
    )
    levels = [classify_impact_level(event.project_impact_score) for event in events]
    return [
        f"Eventi esclusi per basso impatto: {low_impact_excluded}",
        f"Eventi operativi: {levels.count('operative')}",
        f"Eventi critici: {levels.count('critical')}",
        (
            "Distribuzione impatto: "
            f"rumore={levels.count('noise')}, "
            f"contesto={levels.count('context')}, "
            f"operativo={levels.count('operative')}, "
            f"critico={levels.count('critical')}"
        ),
    ]


def _lifecycle_sections(state: OperationalState) -> tuple[list[str], list[str], list[str]]:
    snapshot = state.lifecycle_snapshot
    if snapshot is None:
        snapshot = build_operational_snapshot(state)
    delta = snapshot.delta

    changes: list[str] = []

    def _add_change(title: str, items: list[str]) -> None:
        if items:
            changes.append(f"{title}:")
            changes.extend(f"  - {item}" for item in items)

    _add_change("Nuovi task", delta.newly_opened)
    _add_change("Task completati", delta.newly_completed)
    _add_change("Problemi risolti", delta.newly_resolved)
    _add_change("Problemi riaperti", delta.reopened)
    _add_change("Decisioni/informazioni superate", delta.superseded)
    _add_change("Elementi diventati stale", delta.newly_stale)
    if not changes:
        changes.append("Nessun cambiamento rilevato dall'ultimo aggiornamento")

    current: list[str] = []

    def _add_state(title: str, items: list[str]) -> None:
        current.append(f"{title}: {len(items)}")
        current.extend(f"  - {item}" for item in items[:20])

    _add_state("Criticita/Problemi aperti", snapshot.active_issues)
    _add_state("Problemi risolti", snapshot.resolved_issues)
    _add_state("Task aperti", snapshot.active_tasks)
    _add_state("Task completati/verificati", snapshot.completed_tasks)
    _add_state("Decisioni attive", snapshot.decisions_active)
    _add_state("Decisioni superate", snapshot.decisions_superseded)
    _add_state("Domande aperte", snapshot.open_questions)
    _add_state("Domande risposte", snapshot.answered_questions)
    _add_state("Elementi stale da verificare", snapshot.stale_items)
    if snapshot.high_attention_items:
        _add_state("Elementi ad alta attenzione", snapshot.high_attention_items)

    transitions: list[str] = []
    for record in snapshot.transitions:
        transitions.append(
            f"[{record.category}] {record.text}: {record.previous_status or 'iniziale'} -> {record.new_status} "
            f"| motivo: {record.reason} | confidence: {record.confidence} "
            f"| evidenza: {', '.join(record.evidence_event_ids) if record.evidence_event_ids else 'n/d'}"
        )
    if not transitions:
        transitions.append("Nessuna transizione di stato in questo aggiornamento")

    superseded: list[str] = []
    for record in snapshot.superseded_pairs:
        superseded.append(
            f"[{record.category}] precedente: '{record.text}' -> {record.new_status} "
            f"| sostituito da: '{record.related_text}' | motivo: {record.reason} "
            f"| confidence: {record.confidence} | evidenza: {', '.join(record.evidence_event_ids) or 'n/d'}"
        )
    if not superseded:
        superseded.append("Nessun elemento superato o sostituito")

    contradictions: list[str] = []
    for record in snapshot.contradictions:
        contradictions.append(
            f"[{record.category}] A: '{record.text}' vs B: '{record.related_text}' "
            f"| risoluzione: A -> {record.new_status} | motivo: {record.reason} "
            f"| confidence: {record.confidence} | evidenza: {', '.join(record.evidence_event_ids) or 'n/d'}"
        )
    if not contradictions:
        contradictions.append("Nessuna contraddizione risolta")

    partially = [f"{text}" for text in snapshot.partially_answered_questions] or ["Nessuna domanda parzialmente risposta"]
    mitigated = [f"{text}" for text in snapshot.mitigated_issues] or ["Nessun problema mitigato"]

    return changes, current, transitions, superseded, contradictions, partially, mitigated


def _markdown(report: DailyReport) -> str:
    sections = [
        ("Decisioni", report.decisions),
        ("Task aperti", report.tasks_open),
        ("Task completati", report.tasks_completed),
        ("Problemi aperti", report.issues_open),
        ("Informazioni rilevanti", report.information),
        ("Domande aperte", report.open_questions),
        ("Media rilevanti", report.media_relevant),
        ("Profilo adattivo della chat", report.adaptive_chat_profile_report),
        ("Macro-thread operativi", report.operational_macro_threads),
        ("Relazioni candidate tra thread", report.thread_relation_candidates),
        ("Thread operativi aperti", report.operational_threads),
        ("Cambiamenti da ultimo aggiornamento", report.lifecycle_changes),
        ("Stato operativo attuale", report.lifecycle_current_state),
        ("Transizioni rilevate", report.lifecycle_transitions),
        ("Elementi superati o sostituiti", report.lifecycle_superseded),
        ("Contraddizioni risolte", report.lifecycle_contradictions),
        ("Domande parzialmente risposte", report.lifecycle_partially_answered),
        ("Problemi mitigati", report.lifecycle_mitigated),
        ("Elementi da verificare", report.items_to_verify),
        ("Prossime azioni suggerite", report.next_actions),
        ("Rumore Conversazionale Filtrato", report.conversational_noise_filtered),
        ("Statistiche Impatto Progetto", report.impact_statistics),
    ]
    lines = [f"# {report.title}", "", f"Data: {report.date}", f"Modalita report: {report.report_mode}", ""]
    for title, items in sections:
        lines.append(f"## {title}")
        if items:
            lines.extend(f"- {item}" for item in items)
        else:
            lines.append("- Nessun elemento")
        lines.append("")
    return "\n".join(lines).strip()


def _media_label(
    event: OperationalEvent,
    nearby_context: str = "",
    operational_items: list[OperationalItem] | None = None,
) -> str:
    file_name = None
    if event.attachment_path:
        file_name = event.attachment_path.replace("\\", "/").split("/")[-1]
    file_name = file_name or event.attachment_metadata.get("file_name") or "media"
    extracted = (event.extracted_text or "").strip()
    if len(extracted) > 180:
        extracted = extracted[:177].rstrip() + "..."
    description = event.media_description or event.attachment_metadata.get("description") or ""
    context_parts = []
    if event.sender:
        context_parts.append(f"autore: {event.sender}")
    if event.timestamp:
        context_parts.append(f"data: {_format_timestamp(event.timestamp)}")
    item_lines = []
    for item in operational_items or []:
        item_lines.append(f"{item.__class__.__name__}: {item.text}")
    return "\n".join(
        [
            f"{file_name} ({event.attachment_type or event.type})",
            f"  Contesto collegato: {' | '.join(context_parts) if context_parts else 'non disponibile'}",
            f"  Contesto messaggi vicini: {nearby_context or 'non disponibile'}",
            f"  Testo OCR: {extracted or 'non rilevato'}",
            f"  Stato OCR: {event.extraction_status or 'non analizzato'}",
            f"  Descrizione sintetica: {description or 'media collegato alla conversazione'}",
            f"  Elementi operativi dal media: {'; '.join(item_lines) if item_lines else 'nessuno'}",
        ]
    )


def _nearby_context_for_event(event: OperationalEvent, events: list[OperationalEvent], report_mode: ReportMode = "OPERATIVE_ONLY") -> str:
    event_index = next((idx for idx, candidate in enumerate(events) if candidate.event_id == event.event_id), -1)
    if event_index < 0:
        return ""
    snippets = []
    start = max(0, event_index - 2)
    end = min(len(events), event_index + 3)
    for candidate in events[start:end]:
        if candidate.event_id == event.event_id:
            continue
        if not _event_allowed(candidate, report_mode):
            continue
        text = (candidate.content or candidate.extracted_text or "").strip()
        if not text:
            continue
        text = " ".join(text.split())
        if len(text) > 90:
            text = text[:87].rstrip() + "..."
        snippets.append(text)
    return " | ".join(snippets[:3])


async def build_daily_report(project_id: str, report_mode: ReportMode = "OPERATIVE_ONLY") -> DailyReport:
    state = await load_state(project_id)
    events = await list_events(project_id)
    event_by_id = {event.event_id: event for event in events}
    today = datetime.now(timezone.utc).date().isoformat()
    decisions = [item for item in state.decisions if should_include_in_report(item) and _item_allowed(item, event_by_id, report_mode)]
    tasks = [task for task in state.tasks if should_include_in_report(task) and _item_allowed(task, event_by_id, report_mode)]
    issues = [item for item in state.issues if should_include_in_report(item) and _item_allowed(item, event_by_id, report_mode)]
    information = [item for item in state.information if should_include_in_report(item) and _item_allowed(item, event_by_id, report_mode)]
    open_questions = [
        item for item in state.open_questions if should_include_in_report(item) and _item_allowed(item, event_by_id, report_mode)
    ]
    items_to_verify = [
        item
        for item in [
            *state.decisions,
            *state.tasks,
            *state.issues,
            *state.information,
            *state.open_questions,
        ]
        if should_verify_item(item)
    ]
    operational_items = [*decisions, *tasks, *issues]
    context_complete = len([item for item in operational_items if has_item_context(item)])
    context_total = len(operational_items)

    media_events = [
        event
        for event in events
        if event.attachment_path and event.attachment_type in {"image", "pdf", "document"}
        and _event_allowed(event, report_mode)
    ]
    items_by_event_id: dict[str, list[OperationalItem]] = {}
    for item in [*state.decisions, *state.tasks, *state.issues, *state.information, *state.open_questions]:
        if item.source_event_id:
            items_by_event_id.setdefault(item.source_event_id, []).append(item)
    open_threads = [
        thread
        for thread in state.threads
        if thread.status in {"open", "in_progress", "waiting", "stale"}
        and thread.project_impact_score >= 50
        and _thread_allowed(thread, event_by_id, report_mode)
    ]
    thread_by_id = {thread.thread_id: thread for thread in state.threads}
    macro_threads = [
        macro
        for macro in state.macro_threads
        if macro.child_thread_ids and _macro_allowed(macro, thread_by_id, event_by_id, report_mode)
    ]
    relation_candidates = [
        relation
        for relation in state.thread_relation_candidates
        if relation.should_promote_to_macro or relation.should_remain_candidate
    ][:30]
    events_linked_to_threads = len({event_id for thread in state.threads for event_id in thread.related_event_ids})

    (
        lifecycle_changes,
        lifecycle_current_state,
        lifecycle_transitions,
        lifecycle_superseded,
        lifecycle_contradictions,
        lifecycle_partially_answered,
        lifecycle_mitigated,
    ) = _lifecycle_sections(state)

    report = DailyReport(
        title=f"Aggiornamento giornaliero - {project_id}",
        date=today,
        project_id=project_id,
        report_mode=report_mode,
        lifecycle_changes=lifecycle_changes,
        lifecycle_current_state=lifecycle_current_state,
        lifecycle_transitions=lifecycle_transitions,
        lifecycle_superseded=lifecycle_superseded,
        lifecycle_contradictions=lifecycle_contradictions,
        lifecycle_partially_answered=lifecycle_partially_answered,
        lifecycle_mitigated=lifecycle_mitigated,
        decisions=[_item_label(item, "DECISION") for item in decisions],
        tasks_open=[_task_label(task) for task in tasks if getattr(task, "status", "open") == "open"],
        tasks_completed=[_task_label(task) for task in tasks if getattr(task, "status", "open") == "completed"],
        issues_open=[_item_label(item, "ISSUE") for item in issues],
        information=[item.text for item in information],
        open_questions=[item.text for item in open_questions],
        media_relevant=[
            _media_label(
                event,
                nearby_context=_nearby_context_for_event(event, events, report_mode),
                operational_items=items_by_event_id.get(event.event_id, []),
            )
            for event in media_events
        ],
        adaptive_chat_profile_report=_profile_label(state.adaptive_chat_profile),
        operational_macro_threads=[_macro_label(macro, thread_by_id) for macro in macro_threads],
        thread_relation_candidates=[_relation_label(relation, thread_by_id) for relation in relation_candidates],
        operational_threads=[_thread_label(thread, event_by_id) for thread in open_threads],
        items_to_verify=[_item_label(item, "VERIFY") for item in items_to_verify],
        next_actions=_next_actions(state, event_by_id, report_mode),
        conversational_noise_filtered=_noise_summary(events, report_mode),
        impact_statistics=_impact_statistics(events, report_mode),
        metadata={
            "source_event_count": len(events),
            "state_updated_at": state.updated_at,
            "report_mode": report_mode,
            "domain_stats": state.domain_stats,
            "adaptive_chat_profile": state.adaptive_chat_profile.model_dump() if state.adaptive_chat_profile else None,
            "impact_distribution": {
                "noise": len([event for event in events if classify_impact_level(event.project_impact_score) == "noise"]),
                "context": len([event for event in events if classify_impact_level(event.project_impact_score) == "context"]),
                "operative": len([event for event in events if classify_impact_level(event.project_impact_score) == "operative"]),
                "critical": len([event for event in events if classify_impact_level(event.project_impact_score) == "critical"]),
            },
            "context_complete_items": context_complete,
            "context_total_items": context_total,
            "context_completeness": (context_complete / context_total) if context_total else 0,
            "threads_total": len(state.threads),
            "threads_open": len(open_threads),
            "threads_resolved": len([thread for thread in state.threads if thread.status == "resolved"]),
            "events_linked_to_threads": events_linked_to_threads,
            "macro_threads_total": len(macro_threads),
            "threads_linked_to_macro_threads": len([thread for thread in state.threads if thread.macro_thread_id]),
            "threads_without_macro_thread": len([thread for thread in state.threads if not thread.macro_thread_id]),
            "candidate_relation_count": len([relation for relation in state.thread_relation_candidates if relation.should_remain_candidate]),
            "promoted_relation_count": len([relation for relation in state.thread_relation_candidates if relation.should_promote_to_macro]),
            "rejected_relation_count": len([relation for relation in state.thread_relation_candidates if not relation.should_promote_to_macro and not relation.should_remain_candidate]),
            "related_past_thread_ids": len({thread_id for thread in state.threads for thread_id in thread.related_past_thread_ids}),
            "low_confidence_threads": len([thread for thread in state.threads if thread.grouping_confidence == "low"]),
            "isolated_issues": len([issue for issue in issues if not issue.source_event_id or not event_by_id.get(issue.source_event_id) or not event_by_id[issue.source_event_id].thread_id]),
        },
    )
    report.markdown = _markdown(report)
    return report
