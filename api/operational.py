from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
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
    OperationalBriefing,
    OperationalDigest,
    OperationalEvent,
    OperationalLifecycleSnapshot,
    OperationalSnapshot,
    OperationalState,
    OperationalThread,
    QueryAnswerItem,
    QueryResult,
    ReportMode,
    SnapshotDelta,
)
from core.operational_memory.query_engine import (
    answer_query,
    build_briefing,
    build_digest,
    list_items,
)
from core.operational_memory.snapshot_delta import compute_snapshot_delta
from core.operational_memory.snapshot_store import (
    create_snapshot,
    list_snapshots,
    load_latest_lifecycle_snapshot,
)
from core.operational_memory.state_engine import get_project_state, ingest_messages
from core.operational_memory.state_store import load_state
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
async def get_operational_daily_report_endpoint(
    project_id: str,
    report_mode: ReportMode = "OPERATIVE_ONLY",
) -> DailyReport:
    return await build_daily_report(project_id, report_mode=report_mode)


@router.post("/operational-demo/{project_id}/whatsapp-export/run", response_model=OfflineWhatsAppDemoResponse)
async def run_offline_whatsapp_demo_endpoint(
    project_id: str,
    request: OfflineWhatsAppDemoRequest,
) -> OfflineWhatsAppDemoResponse:
    try:
        return await run_whatsapp_export_demo(project_id, request)
    except OfflineWhatsAppDemoError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# --------------------------------------------------------------------------- #
# FASE 6 — Operational Runtime MVP (briefing / report / digest / ask / delta /
# snapshot / items / threads). Read-only over the persisted operational state;
# generic and explainable; no domain-specific logic.
# --------------------------------------------------------------------------- #

_API = "/api/operational/projects/{project_id}"


class AskRequest(BaseModel):
    query: str = ""


class IngestTestRequest(BaseModel):
    events: list[OperationalEvent] = Field(default_factory=list)


@router.get(f"{_API}/briefing", response_model=OperationalBriefing)
async def operational_briefing_endpoint(project_id: str) -> OperationalBriefing:
    state = await load_state(project_id)
    return build_briefing(state)


@router.get(f"{_API}/digest", response_model=OperationalDigest)
async def operational_digest_endpoint(project_id: str) -> OperationalDigest:
    state = await load_state(project_id)
    return build_digest(state)


@router.get(f"{_API}/snapshot", response_model=OperationalLifecycleSnapshot)
async def operational_snapshot_endpoint(project_id: str) -> OperationalLifecycleSnapshot:
    state = await load_state(project_id)
    if state.lifecycle_snapshot is None:
        raise HTTPException(status_code=404, detail="no lifecycle snapshot for this project yet")
    return state.lifecycle_snapshot


@router.get(f"{_API}/delta", response_model=SnapshotDelta)
async def operational_delta_endpoint(project_id: str) -> SnapshotDelta:
    state = await load_state(project_id)
    if state.lifecycle_snapshot is not None and state.lifecycle_snapshot.snapshot_delta is not None:
        return state.lifecycle_snapshot.snapshot_delta
    previous = load_latest_lifecycle_snapshot(project_id)
    return compute_snapshot_delta(
        previous.item_states if previous else None,
        state,
        previous_snapshot_id=previous.snapshot_id if previous else None,
        previous_generated_at=previous.generated_at if previous else None,
    )


@router.post(f"{_API}/ask", response_model=QueryResult)
async def operational_ask_endpoint(project_id: str, request: AskRequest) -> QueryResult:
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="query must not be empty")
    state = await load_state(project_id)
    return answer_query(state, request.query)


@router.get(f"{_API}/items", response_model=list[QueryAnswerItem])
async def operational_items_endpoint(
    project_id: str,
    category: str | None = None,
    status: str | None = None,
) -> list[QueryAnswerItem]:
    state = await load_state(project_id)
    return list_items(state, category=category, status=status)


@router.get(f"{_API}/threads", response_model=list[OperationalThread])
async def operational_threads_endpoint(project_id: str) -> list[OperationalThread]:
    state = await load_state(project_id)
    return state.threads


@router.get(f"{_API}/report")
async def operational_report_endpoint(project_id: str) -> Response:
    state = await load_state(project_id)
    markdown = build_briefing(state).markdown
    return Response(content=markdown, media_type="text/markdown; charset=utf-8")


@router.get(f"{_API}/report/download")
async def operational_report_download_endpoint(project_id: str) -> Response:
    state = await load_state(project_id)
    markdown = build_briefing(state).markdown
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in project_id).strip("._") or "project"
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="briefing_{safe}.md"'},
    )


@router.post(f"{_API}/ingest-test", response_model=OperationalEventsBatchResponse)
async def operational_ingest_test_endpoint(
    project_id: str,
    request: IngestTestRequest,
) -> OperationalEventsBatchResponse:
    result = await ingest_events_batch(project_id, request.events)
    return OperationalEventsBatchResponse(**result)
