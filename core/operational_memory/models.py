from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field


EventType = Literal["text", "image", "pdf", "document"]
ProcessedStatus = Literal["pending", "processed", "failed"]


class OperationalItem(BaseModel):
    id: str = Field(default="")
    text: str
    source: str


class Decision(OperationalItem):
    pass


class OperationalTask(OperationalItem):
    owner: Optional[str] = None
    due: Optional[str] = None


class Issue(OperationalItem):
    pass


class Information(OperationalItem):
    pass


class OperationalQuestion(OperationalItem):
    pass


class OperationalState(BaseModel):
    project_id: Optional[str] = None
    updated_at: Optional[str] = None
    decisions: list[Decision] = Field(default_factory=list)
    tasks: list[OperationalTask] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    information: list[Information] = Field(default_factory=list)
    open_questions: list[OperationalQuestion] = Field(default_factory=list)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class OperationalEvent(BaseModel):
    event_id: str
    project_id: str
    source: str = Field(default="simulated")
    sender: str = Field(default="")
    timestamp: str = Field(default_factory=utc_now_iso)
    type: EventType = "text"
    content: str = Field(default="")
    attachment_metadata: dict = Field(default_factory=dict)
    processed_status: ProcessedStatus = "pending"
