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
InferredChatDomain = Literal[
    "construction_site",
    "maintenance",
    "engineering",
    "logistics",
    "sales",
    "customer_support",
    "family_coordination",
    "school",
    "travel",
    "event_planning",
    "generic_group_chat",
    "unknown",
]
ReportMode = Literal["OPERATIVE_ONLY", "OPERATIVE_PLUS_LOGISTICS", "FULL_CONTEXT"]
ThreadStatus = Literal["open", "in_progress", "waiting", "resolved", "stale"]
EvidenceStrength = Literal["none", "weak", "medium", "high"]
GroupingConfidence = Literal["low", "medium", "high"]
ThreadLevel = Literal["macro", "subthread"]
MacroRelation = Literal[
    "same_system",
    "same_area",
    "same_work_package",
    "same_component_family",
    "temporal_sequence",
    "weak_relation",
]


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
    creation_reason: str = ""
    continuity_signals: list[str] = Field(default_factory=list)
    resolution_signals: list[str] = Field(default_factory=list)
    related_past_thread_ids: list[str] = Field(default_factory=list)
    grouping_confidence: GroupingConfidence = "low"
    macro_thread_id: Optional[str] = None
    parent_thread_id: Optional[str] = None
    child_thread_ids: list[str] = Field(default_factory=list)
    thread_level: ThreadLevel = "subthread"
    macro_title: Optional[str] = None
    macro_context_tags: list[str] = Field(default_factory=list)
    macro_confidence: GroupingConfidence = "low"
    relation_to_macro: Optional[MacroRelation] = None


class OperationalMacroThread(BaseModel):
    macro_thread_id: str
    project_id: str
    title: str
    status: ThreadStatus = "open"
    started_at: str
    last_updated_at: str
    context_tags: list[str] = Field(default_factory=list)
    child_thread_ids: list[str] = Field(default_factory=list)
    related_event_ids: list[str] = Field(default_factory=list)
    summary: str = ""
    confidence: GroupingConfidence = "low"
    open_items_count: int = 0
    critical_items_count: int = 0
    creation_reason: str = ""
    adaptive_patterns: list[str] = Field(default_factory=list)
    ignored_generic_terms: list[str] = Field(default_factory=list)


class AdaptiveChatProfile(BaseModel):
    project_id: str
    inferred_domain: InferredChatDomain = "unknown"
    domain_confidence: Confidence = "low"
    recurring_entities: list[str] = Field(default_factory=list)
    recurring_locations: list[str] = Field(default_factory=list)
    recurring_people: list[str] = Field(default_factory=list)
    recurring_objects: list[str] = Field(default_factory=list)
    recurring_actions: list[str] = Field(default_factory=list)
    recurring_problem_terms: list[str] = Field(default_factory=list)
    recurring_completion_terms: list[str] = Field(default_factory=list)
    recurring_question_patterns: list[str] = Field(default_factory=list)
    generic_terms: list[str] = Field(default_factory=list)
    specific_terms: list[str] = Field(default_factory=list)
    topic_candidates: list[str] = Field(default_factory=list)
    workflow_patterns: list[str] = Field(default_factory=list)
    term_specificity: dict[str, float] = Field(default_factory=dict)
    term_quality_scores: dict[str, float] = Field(default_factory=dict)
    rejected_terms: list[str] = Field(default_factory=list)
    rejection_reasons: dict[str, str] = Field(default_factory=dict)
    last_updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class OperationalState(BaseModel):
    project_id: Optional[str] = None
    updated_at: Optional[str] = None
    decisions: list[Decision] = Field(default_factory=list)
    tasks: list[OperationalTask] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    information: list[Information] = Field(default_factory=list)
    open_questions: list[OperationalQuestion] = Field(default_factory=list)
    threads: list[OperationalThread] = Field(default_factory=list)
    macro_threads: list[OperationalMacroThread] = Field(default_factory=list)
    adaptive_chat_profile: Optional[AdaptiveChatProfile] = None
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
    topic_shift_score: int = 0
    thread_continuity_score: int = 0
    resolution_signal: bool = False
    reopen_signal: bool = False
    evidence_strength: EvidenceStrength = "none"
    thread_link_reason: str = ""
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
    adaptive_chat_profile_report: list[str] = Field(default_factory=list)
    operational_threads: list[str] = Field(default_factory=list)
    operational_macro_threads: list[str] = Field(default_factory=list)
    items_to_verify: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    conversational_noise_filtered: list[str] = Field(default_factory=list)
    impact_statistics: list[str] = Field(default_factory=list)
    markdown: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
