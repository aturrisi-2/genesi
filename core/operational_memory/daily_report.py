from __future__ import annotations

from datetime import datetime, timezone

from core.operational_memory.event_store import list_events
from core.operational_memory.models import DailyReport, OperationalState
from core.operational_memory.state_store import load_state


def _task_label(task) -> str:
    parts = [task.text]
    if task.owner:
        parts.append(f"owner: {task.owner}")
    if task.due:
        parts.append(f"due: {task.due}")
    return " | ".join(parts)


def _next_actions(state: OperationalState) -> list[str]:
    actions: list[str] = []
    for task in state.tasks:
        if getattr(task, "status", "open") != "open":
            continue
        if not task.owner:
            actions.append(f"Assegnare un responsabile: {task.text}")
        if not task.due:
            actions.append(f"Definire una scadenza: {task.text}")
    for issue in state.issues:
        actions.append(f"Chiarire piano di risoluzione: {issue.text}")
    for question in state.open_questions:
        actions.append(f"Rispondere alla domanda aperta: {question.text}")
    return actions


def _markdown(report: DailyReport) -> str:
    sections = [
        ("Decisioni", report.decisions),
        ("Task aperti", report.tasks_open),
        ("Task completati", report.tasks_completed),
        ("Problemi aperti", report.issues_open),
        ("Informazioni rilevanti", report.information),
        ("Domande aperte", report.open_questions),
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

    report = DailyReport(
        title=f"Aggiornamento giornaliero - {project_id}",
        date=today,
        project_id=project_id,
        decisions=[item.text for item in state.decisions],
        tasks_open=[_task_label(task) for task in state.tasks if getattr(task, "status", "open") == "open"],
        tasks_completed=[_task_label(task) for task in state.tasks if getattr(task, "status", "open") == "completed"],
        issues_open=[item.text for item in state.issues],
        information=[item.text for item in state.information],
        open_questions=[item.text for item in state.open_questions],
        next_actions=_next_actions(state),
        metadata={"source_event_count": len(events), "state_updated_at": state.updated_at},
    )
    report.markdown = _markdown(report)
    return report
