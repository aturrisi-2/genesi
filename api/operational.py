from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.operational_memory.extractor import (
    OperationalMemoryExtractionError,
    extract_state,
)
from core.operational_memory.models import OperationalState


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
