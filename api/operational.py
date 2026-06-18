from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.operational_memory.importers.whatsapp_export import parse_whatsapp_export
from core.operational_memory.demo_runner import (
    OfflineWhatsAppDemoError,
    OfflineWhatsAppDemoRequest,
    OfflineWhatsAppDemoResponse,
    run_whatsapp_export_demo,
)
from core.operational_memory.extractor import (
    OperationalMemoryExtractionError,
    extract_state,
)
from core.operational_memory.daily_report import build_daily_report
from core.operational_memory.models import (
    DailyReport,
    OperationalEvent,
    OperationalSnapshot,
    OperationalState,
)
from core.operational_memory.snapshot_store import create_snapshot, list_snapshots
from core.operational_memory.state_engine import get_project_state, ingest_messages
from core.operational_memory.watcher_engine import (
    get_events,
    ingest_event,
    ingest_events_batch,
    process_pending_events,
)


router = APIRouter(tags=["operational-memory"])


class OperationalStateRequest(BaseModel):
    messages: list[str] = Field(default_factory=list)


class ProcessPendingResponse(BaseModel):
    project_id: str
    processed: int
    failed: int
    pending_remaining: int
    state: OperationalState | None = None


class OperationalEventsBatchRequest(BaseModel):
    events: list[OperationalEvent] = Field(default_factory=list)


class OperationalEventsBatchResponse(BaseModel):
    accepted: int = 0
    duplicates: int = 0
    failed: int = 0


class WhatsAppExportImportRequest(BaseModel):
    raw_text: str
    source_name: str = "whatsapp-export"
    timezone: str = "Europe/Rome"
    media_dir: str | None = None


class WhatsAppExportImportResponse(BaseModel):
    project_id: str
    source_name: str
    parsed: int = 0
    accepted: int = 0
    duplicates: int = 0
    ignored: int = 0
    failed: int = 0


@router.post("/operational-state", response_model=OperationalState)
async def operational_state_endpoint(request: OperationalStateRequest) -> OperationalState:
    messages = [m.strip() for m in request.messages if isinstance(m, str) and m.strip()]
    if not messages:
        raise HTTPException(status_code=400, detail="messages must contain at least one non-empty string")

    try:
        return await extract_state(messages)
    except OperationalMemoryExtractionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/operational-state/{project_id}", response_model=OperationalState)
async def get_operational_state_endpoint(project_id: str) -> OperationalState:
    return await get_project_state(project_id)


@router.post("/operational-state/{project_id}/ingest", response_model=OperationalState)
async def ingest_operational_messages_endpoint(
    project_id: str,
    request: OperationalStateRequest,
) -> OperationalState:
    messages = [m.strip() for m in request.messages if isinstance(m, str) and m.strip()]
    if not messages:
        raise HTTPException(status_code=400, detail="messages must contain at least one non-empty string")

    try:
        return await ingest_messages(project_id, messages)
    except OperationalMemoryExtractionError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/operational-events/{project_id}", response_model=OperationalEvent)
async def create_operational_event_endpoint(
    project_id: str,
    event: OperationalEvent,
) -> OperationalEvent:
    if event.project_id and event.project_id != project_id:
        raise HTTPException(status_code=400, detail="event project_id must match path project_id")
    event.project_id = project_id
    stored, _created = await ingest_event(event)
    return stored


@router.post("/operational-events/{project_id}/batch", response_model=OperationalEventsBatchResponse)
async def create_operational_events_batch_endpoint(
    project_id: str,
    request: OperationalEventsBatchRequest,
) -> OperationalEventsBatchResponse:
    result = await ingest_events_batch(project_id, request.events)
    return OperationalEventsBatchResponse(**result)


@router.post("/operational-events/{project_id}/import/whatsapp-export", response_model=WhatsAppExportImportResponse)
async def import_whatsapp_export_endpoint(
    project_id: str,
    request: WhatsAppExportImportRequest,
) -> WhatsAppExportImportResponse:
    parsed = parse_whatsapp_export(
        request.raw_text,
        project_id=project_id,
        source_name=request.source_name,
        timezone=request.timezone,
        media_dir=request.media_dir,
    )
    result = await ingest_events_batch(project_id, parsed.events)
    return WhatsAppExportImportResponse(
        project_id=project_id,
        source_name=request.source_name,
        parsed=len(parsed.events),
        accepted=result["accepted"],
        duplicates=result["duplicates"],
        ignored=parsed.ignored,
        failed=result["failed"],
    )


@router.get("/operational-events/{project_id}", response_model=list[OperationalEvent])
async def list_operational_events_endpoint(project_id: str) -> list[OperationalEvent]:
    return await get_events(project_id)


@router.post("/operational-events/{project_id}/process-pending", response_model=ProcessPendingResponse)
async def process_pending_operational_events_endpoint(project_id: str) -> ProcessPendingResponse:
    result = await process_pending_events(project_id)
    return ProcessPendingResponse(**result)


@router.post("/operational-state/{project_id}/snapshot", response_model=OperationalSnapshot)
async def create_operational_state_snapshot_endpoint(project_id: str) -> OperationalSnapshot:
    return await create_snapshot(project_id)


@router.get("/operational-state/{project_id}/snapshots", response_model=list[OperationalSnapshot])
async def list_operational_state_snapshots_endpoint(project_id: str) -> list[OperationalSnapshot]:
    return await list_snapshots(project_id)


@router.get("/operational-state/{project_id}/daily-report", response_model=DailyReport)
async def get_operational_daily_report_endpoint(project_id: str) -> DailyReport:
    return await build_daily_report(project_id)


@router.post("/operational-demo/{project_id}/whatsapp-export/run", response_model=OfflineWhatsAppDemoResponse)
async def run_offline_whatsapp_demo_endpoint(
    project_id: str,
    request: OfflineWhatsAppDemoRequest,
) -> OfflineWhatsAppDemoResponse:
    try:
        return await run_whatsapp_export_demo(project_id, request)
    except OfflineWhatsAppDemoError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
