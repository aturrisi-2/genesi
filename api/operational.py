from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.operational_memory.extractor import (
    OperationalMemoryExtractionError,
    extract_state,
)
from core.operational_memory.models import OperationalState
from core.operational_memory.state_engine import get_project_state, ingest_messages


router = APIRouter(tags=["operational-memory"])


class OperationalStateRequest(BaseModel):
    messages: list[str] = Field(default_factory=list)


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
