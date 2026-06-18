from __future__ import annotations

from datetime import datetime, timezone

from core.operational_memory.event_store import list_events
from core.operational_memory.models import DailyReport, OperationalItem, OperationalState
from core.operational_memory.quality import (
    has_item_context,
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


def _next_actions(state: OperationalState) -> list[str]:
    prioritized: list[tuple[int, str]] = []
    seen: set[str] = set()

    def add(priority: int, action: str) -> None:
        key = action.strip().lower()
        if not key or key in seen:
            return
        seen.add(key)
        prioritized.append((priority, action))

    reportable_issues = [issue for issue in state.issues if should_include_in_report(issue)]
    reportable_tasks = [task for task in state.tasks if should_include_in_report(task)]
    reportable_questions = [question for question in state.open_questions if should_include_in_report(question)]

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


def _markdown(report: DailyReport) -> str:
    sections = [
        ("Decisioni", report.decisions),
        ("Task aperti", report.tasks_open),
        ("Task completati", report.tasks_completed),
        ("Problemi aperti", report.issues_open),
        ("Informazioni rilevanti", report.information),
        ("Domande aperte", report.open_questions),
        ("Elementi da verificare", report.items_to_verify),
        ("Prossime azioni suggerite", report.next_actions),
    ]
    lines = [f"# {report.title}", "", f"Data: {report.date}", ""]
    for title, items in sections:
        lines.append(f"## {title}")
        if items:
            lines.extend(f"- {item}" for item in items)
        else:
            lines.append("- Nessun elemento")
        lines.append("")
    return "\n".join(lines).strip()


async def build_daily_report(project_id: str) -> DailyReport:
    state = await load_state(project_id)
    events = await list_events(project_id)
    today = datetime.now(timezone.utc).date().isoformat()
    decisions = [item for item in state.decisions if should_include_in_report(item)]
    tasks = [task for task in state.tasks if should_include_in_report(task)]
    issues = [item for item in state.issues if should_include_in_report(item)]
    information = [item for item in state.information if should_include_in_report(item)]
    open_questions = [item for item in state.open_questions if should_include_in_report(item)]
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

    report = DailyReport(
        title=f"Aggiornamento giornaliero - {project_id}",
        date=today,
        project_id=project_id,
        decisions=[_item_label(item, "DECISION") for item in decisions],
        tasks_open=[_task_label(task) for task in tasks if getattr(task, "status", "open") == "open"],
        tasks_completed=[_task_label(task) for task in tasks if getattr(task, "status", "open") == "completed"],
        issues_open=[_item_label(item, "ISSUE") for item in issues],
        information=[item.text for item in information],
        open_questions=[item.text for item in open_questions],
        items_to_verify=[_item_label(item, "VERIFY") for item in items_to_verify],
        next_actions=_next_actions(state),
        metadata={
            "source_event_count": len(events),
            "state_updated_at": state.updated_at,
            "context_complete_items": context_complete,
            "context_total_items": context_total,
            "context_completeness": (context_complete / context_total) if context_total else 0,
        },
    )
    report.markdown = _markdown(report)
    return report
