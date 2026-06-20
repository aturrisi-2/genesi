from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from core.operational_memory.daily_report import build_daily_report
from core.operational_memory.importers.whatsapp_export import parse_whatsapp_export
from core.operational_memory.models import DailyReport, OperationalSnapshot, ReportMode
from core.operational_memory.snapshot_store import create_snapshot
from core.operational_memory.watcher_engine import ingest_events_batch, process_pending_events


ReportFormat = Literal["markdown", "json"]


class OfflineWhatsAppDemoRequest(BaseModel):
    raw_text: str
    source_name: str = "whatsapp-export"
    timezone: str = "Europe/Rome"
    create_snapshot: bool = True
    report_format: ReportFormat = "markdown"
    media_dir: str | None = None
    report_mode: ReportMode = "OPERATIVE_ONLY"


class OfflineWhatsAppDemoImportSummary(BaseModel):
    parsed: int = 0
    accepted: int = 0
    duplicates: int = 0
    ignored: int = 0
    failed: int = 0
    media_detected: int = 0
    media_analyzed: int = 0
    media_text_extracted: int = 0
    media_ignored: int = 0


class OfflineWhatsAppDemoProcessingSummary(BaseModel):
    processed: int = 0
    failed: int = 0
    pending_after: int = 0


class OfflineWhatsAppDemoSnapshotSummary(BaseModel):
    created: bool = False
    snapshot_id: str | None = None


class OfflineWhatsAppDemoStateCounts(BaseModel):
    decisions: int = 0
    open_tasks: int = 0
    completed_tasks: int = 0
    issues: int = 0
    information: int = 0
    questions: int = 0


class OfflineWhatsAppDemoResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    project_id: str
    import_summary: OfflineWhatsAppDemoImportSummary = Field(alias="import")
    processing: OfflineWhatsAppDemoProcessingSummary
    snapshot: OfflineWhatsAppDemoSnapshotSummary
    state_counts: OfflineWhatsAppDemoStateCounts
    daily_report_markdown: str = ""
    daily_report_json: DailyReport | None = None


class OfflineWhatsAppDemoError(ValueError):
    pass


def _state_counts(report: DailyReport) -> OfflineWhatsAppDemoStateCounts:
    return OfflineWhatsAppDemoStateCounts(
        decisions=len(report.decisions),
        open_tasks=len(report.tasks_open),
        completed_tasks=len(report.tasks_completed),
        issues=len(report.issues_open),
        information=len(report.information),
        questions=len(report.open_questions),
    )


async def run_whatsapp_export_demo(
    project_id: str,
    request: OfflineWhatsAppDemoRequest,
) -> OfflineWhatsAppDemoResponse:
    if not request.raw_text.strip():
        raise OfflineWhatsAppDemoError("raw_text must contain a WhatsApp export")

    parsed = parse_whatsapp_export(
        request.raw_text,
        project_id=project_id,
        source_name=request.source_name or "whatsapp-export",
        timezone=request.timezone or "Europe/Rome",
        media_dir=request.media_dir,
    )
    import_result = await ingest_events_batch(project_id, parsed.events)
    processing_result = await process_pending_events(project_id)

    snapshot_summary = OfflineWhatsAppDemoSnapshotSummary()
    snapshot: OperationalSnapshot | None = None
    if request.create_snapshot:
        snapshot = await create_snapshot(project_id)
        snapshot_summary = OfflineWhatsAppDemoSnapshotSummary(
            created=True,
            snapshot_id=snapshot.snapshot_id,
        )

    report = await build_daily_report(project_id, report_mode=request.report_mode)
    include_json = request.report_format == "json"

    return OfflineWhatsAppDemoResponse(
        project_id=project_id,
        import_summary=OfflineWhatsAppDemoImportSummary(
            parsed=len(parsed.events),
            accepted=import_result["accepted"],
            duplicates=import_result["duplicates"],
            ignored=parsed.ignored,
            failed=import_result["failed"],
            media_detected=parsed.media_detected,
            media_analyzed=parsed.media_analyzed,
            media_text_extracted=parsed.media_text_extracted,
            media_ignored=parsed.media_ignored,
        ),
        processing=OfflineWhatsAppDemoProcessingSummary(
            processed=processing_result["processed"],
            failed=processing_result["failed"],
            pending_after=processing_result["pending_remaining"],
        ),
        snapshot=snapshot_summary,
        state_counts=_state_counts(report),
        daily_report_markdown=report.markdown,
        daily_report_json=report if include_json else None,
    )
