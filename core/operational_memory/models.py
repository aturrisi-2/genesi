from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


EventType = Literal["text", "image", "pdf", "document"]
ProcessedStatus = Literal["pending", "processed", "failed"]
TaskStatus = Literal["open", "completed"]
Confidence = Literal["high", "medium", "low"]
Domain = Literal[
    "TECHNICAL_OPERATION",
    "TECHNICAL_ISSUE",
    "TASK_ASSIGNMENT",
    "LOGISTICS_OPERATIONAL",
    "LOGISTICS_PERSONAL",
    "PERSONNEL",
    "SOCIAL",
    "MEDIA_EVIDENCE",
    "UNKNOWN",
]
ReportMode = Literal["OPERATIVE_ONLY", "OPERATIVE_PLUS_LOGISTICS", "FULL_CONTEXT"]
ThreadStatus = Literal["open", "in_progress", "waiting", "resolved", "stale"]


class OperationalItem(BaseModel):
    id: str = Field(default="")
    text: str
    source: str
    confidence: Confidence = "medium"
    source_event_id: Optional[str] = None
    source_timestamp: Optional[str] = None
    source_sender: Optional[str] = None
    source_excerpt: Optional[str] = None
    context_area: Optional[str] = None
    context_system: Optional[str] = None
    context_level: Optional[str] = None
    context_location: Optional[str] = None
    context_tags: list[str] = Field(default_factory=list)
    intent: Optional[str] = None


class Decision(OperationalItem):
    pass


class OperationalTask(OperationalItem):
    owner: Optional[str] = None
    due: Optional[str] = None
    status: TaskStatus = "open"


class Issue(OperationalItem):
    pass


class Information(OperationalItem):
    pass


class OperationalQuestion(OperationalItem):
    pass


class OperationalThread(BaseModel):
    thread_id: str
    project_id: str
    title: str
    status: ThreadStatus = "open"
    started_at: str
    last_updated_at: str
    closed_at: Optional[str] = None
    primary_domain: Domain = "UNKNOWN"
    project_impact_score: int = 0
    related_event_ids: list[str] = Field(default_factory=list)
    related_tasks: list[str] = Field(default_factory=list)
    related_issues: list[str] = Field(default_factory=list)
    related_media: list[str] = Field(default_factory=list)
    context_tags: list[str] = Field(default_factory=list)
    summary: str = ""
    unresolved_questions: list[str] = Field(default_factory=list)


class OperationalState(BaseModel):
    project_id: Optional[str] = None
    updated_at: Optional[str] = None
    decisions: list[Decision] = Field(default_factory=list)
    tasks: list[OperationalTask] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    information: list[Information] = Field(default_factory=list)
    open_questions: list[OperationalQuestion] = Field(default_factory=list)
    threads: list[OperationalThread] = Field(default_factory=list)
    domain_stats: dict[str, int] = Field(default_factory=dict)


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
    attachment_path: Optional[str] = None
    attachment_type: Optional[str] = None
    extracted_text: Optional[str] = None
    media_description: Optional[str] = None
    extraction_status: Optional[str] = None
    extraction_confidence: Optional[Confidence] = None
    domain: Domain = "UNKNOWN"
    domain_confidence: Confidence = "low"
    secondary_domains: list[Domain] = Field(default_factory=list)
    project_impact_score: int = 0
    operational_relevance_score: int = 0
    impact_reason: str = ""
    thread_id: Optional[str] = None
    processed_status: ProcessedStatus = "pending"


class OperationalSnapshot(BaseModel):
    snapshot_id: str
    project_id: str
    timestamp: str = Field(default_factory=utc_now_iso)
    state: OperationalState
    counts: dict[str, int] = Field(default_factory=dict)
    source_event_count: int = 0


class DailyReport(BaseModel):
    title: str
    date: str
    project_id: str
    report_mode: ReportMode = "OPERATIVE_ONLY"
    decisions: list[str] = Field(default_factory=list)
    tasks_open: list[str] = Field(default_factory=list)
    tasks_completed: list[str] = Field(default_factory=list)
    issues_open: list[str] = Field(default_factory=list)
    information: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    media_relevant: list[str] = Field(default_factory=list)
    operational_threads: list[str] = Field(default_factory=list)
    items_to_verify: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    conversational_noise_filtered: list[str] = Field(default_factory=list)
    impact_statistics: list[str] = Field(default_factory=list)
    markdown: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
