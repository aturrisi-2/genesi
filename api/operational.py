from __future__ import annotations

from fastapi import APIRouter, Body, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, ValidationError

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
from core.operational_memory.chat_presence import handle_incoming
from core.operational_memory.models import (
    ChatMessage,
    ChatReply,
    DailyReport,
    InvocationConfig,
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
    StoredReport,
)
from core.operational_memory.report_store import list_reports, load_report
from core.operational_memory.report_viewer import render_report_page
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
    return Response(content=markdown, media_type="text/markdown")


@router.get(f"{_API}/report/download")
async def operational_report_download_endpoint(project_id: str) -> Response:
    state = await load_state(project_id)
    markdown = build_briefing(state).markdown
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in project_id).strip("._") or "project"
    return Response(
        content=markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="briefing_{safe}.md"'},
    )


@router.post(f"{_API}/ingest-test", response_model=OperationalEventsBatchResponse)
async def operational_ingest_test_endpoint(
    project_id: str,
    request: IngestTestRequest,
) -> OperationalEventsBatchResponse:
    result = await ingest_events_batch(project_id, request.events)
    return OperationalEventsBatchResponse(**result)


# --------------------------------------------------------------------------- #
# FASE 7 — Silent Chat Presence + Explicit Invocation + Report Storage
# --------------------------------------------------------------------------- #


class ChatIncomingRequest(BaseModel):
    """Nested chat request (documentation/back-compat). The endpoint also accepts
    a flat body where the message fields sit at the top level."""

    message: ChatMessage
    config: InvocationConfig | None = None


class ChatPresenceResponse(BaseModel):
    silent: bool
    reply: ChatReply | None = None


@router.post(f"{_API}/chat", response_model=ChatPresenceResponse)
async def operational_chat_endpoint(
    project_id: str,
    payload: dict = Body(...),
) -> ChatPresenceResponse:
    # Accept BOTH a nested body {"message": {...}, "config": {...}} and a flat
    # body {"message_id": ..., "text": ..., ...}. project_id is inherited from
    # the path when not supplied in the body.
    config_data = payload.get("config") if isinstance(payload.get("config"), dict) else None
    if isinstance(payload.get("message"), dict):
        raw = dict(payload["message"])
    else:
        raw = {key: value for key, value in payload.items() if key != "config"}

    body_project_id = raw.get("project_id")
    if body_project_id and body_project_id != project_id:
        raise HTTPException(status_code=400, detail="message project_id must match path project_id")
    raw["project_id"] = project_id
    if not str(raw.get("message_id") or "").strip():
        raise HTTPException(status_code=400, detail="message_id is required")

    try:
        message = ChatMessage(**raw)
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors()) from exc
    config = InvocationConfig(**config_data) if config_data is not None else None

    reply = await handle_incoming(message, config=config)
    return ChatPresenceResponse(silent=reply is None, reply=reply)


@router.get(f"{_API}/reports", response_model=list[StoredReport])
async def operational_reports_endpoint(project_id: str) -> list[StoredReport]:
    return list_reports(project_id)


@router.get(f"{_API}/reports/{{report_id}}", response_model=StoredReport)
async def operational_report_get_endpoint(project_id: str, report_id: str) -> StoredReport:
    report = load_report(project_id, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    return report


# GET + HEAD so link checkers / monitors / pre-deploy health checks can probe
# the report without downloading it. HEAD reuses the same handler; Starlette
# drops the body for HEAD requests.
@router.api_route(f"{_API}/reports/{{report_id}}/download", methods=["GET", "HEAD"])
async def operational_report_stored_download_endpoint(project_id: str, report_id: str) -> Response:
    report = load_report(project_id, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    return Response(
        content=report.markdown,
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="{report_id}.md"'},
    )


@router.api_route(f"{_API}/reports/{{report_id}}/view", methods=["GET", "HEAD"], response_class=HTMLResponse)
async def operational_report_view_endpoint(project_id: str, report_id: str) -> HTMLResponse:
    report = load_report(project_id, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="report not found")
    download_url = f"/api/operational/projects/{project_id}/reports/{report_id}/download"
    return HTMLResponse(content=render_report_page(report, download_url))


_HARNESS_HTML = """<!doctype html>
<html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Genesi — Test Harness</title>
<style>
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;max-width:680px;margin:1rem auto;padding:0 1rem;line-height:1.5}
input,textarea,button{font:inherit;width:100%;padding:.5rem;margin:.25rem 0;box-sizing:border-box}
button{cursor:pointer;width:auto;padding:.5rem 1rem}
pre{white-space:pre-wrap;background:#f5f5f5;padding:.75rem;border-radius:6px;overflow-x:auto}
.silent{color:#888}
</style></head>
<body>
<h1>Genesi — Test Harness</h1>
<p>Simula un messaggio di chat. Genesi resta silenziosa salvo invocazione esplicita
(es. "Genesi, fammi il punto").</p>
<label>project_id<input id="pid" value="demo-project"></label>
<label>message_id<input id="mid" value="m1"></label>
<label>messaggio<textarea id="text" rows="3">Genesi, fammi il punto</textarea></label>
<button onclick="send()">Invia</button>
<div id="out"></div>
<script>
async function send(){
  const pid=document.getElementById('pid').value.trim();
  const body={message:{project_id:pid,message_id:document.getElementById('mid').value.trim(),text:document.getElementById('text').value}};
  const r=await fetch(`/api/operational/projects/${pid}/chat`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
  const data=await r.json();
  const out=document.getElementById('out');
  if(data.silent){out.innerHTML='<p class="silent">Silent — nessuna risposta in chat (memoria aggiornata).</p>';return;}
  const rep=data.reply||{};
  let html='<h2>Risposta</h2><pre>'+(rep.reply_markdown||'')+'</pre>';
  if(rep.report_url){html+='<p><a href="'+rep.report_url+'">Apri report completo</a></p>';}
  out.innerHTML=html;
}
</script>
</body></html>"""


@router.get("/operational/harness", response_class=HTMLResponse)
async def operational_harness_endpoint() -> HTMLResponse:
    return HTMLResponse(content=_HARNESS_HTML)
