from __future__ import annotations

from datetime import datetime, timezone

from core.operational_memory.event_store import list_events
from core.operational_memory.models import DailyReport, OperationalState
from core.operational_memory.quality import next_action_priority, should_include_in_report
from core.operational_memory.state_store import load_state


def _task_label(task) -> str:
    parts = [task.text]
    if task.owner:
        parts.append(f"owner: {task.owner}")
    if task.due:
        parts.append(f"due: {task.due}")
    return " | ".join(parts)


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

    report = DailyReport(
        title=f"Aggiornamento giornaliero - {project_id}",
        date=today,
        project_id=project_id,
        decisions=[item.text for item in decisions],
        tasks_open=[_task_label(task) for task in tasks if getattr(task, "status", "open") == "open"],
        tasks_completed=[_task_label(task) for task in tasks if getattr(task, "status", "open") == "completed"],
        issues_open=[item.text for item in issues],
        information=[item.text for item in information],
        open_questions=[item.text for item in open_questions],
        next_actions=_next_actions(state),
        metadata={"source_event_count": len(events), "state_updated_at": state.updated_at},
    )
    report.markdown = _markdown(report)
    return report
