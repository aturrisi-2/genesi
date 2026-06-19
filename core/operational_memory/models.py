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
CanonicalTermType = Literal[
    "object",
    "location",
    "issue",
    "task",
    "material",
    "person_role",
    "workflow_step",
    "mixed",
]
ThreadRelationType = Literal[
    "same_object",
    "same_location",
    "same_work_package",
    "same_problem",
    "same_owner",
    "same_workflow_sequence",
    "follow_up",
    "weak_context",
]


LifecycleCategory = Literal["task", "issue", "decision", "question", "information"]
TaskLifecycle = Literal[
    "open", "in_progress", "blocked", "completed", "verified", "cancelled", "superseded", "stale"
]
IssueLifecycle = Literal[
    "open", "confirmed", "investigating", "mitigated", "resolved", "reopened", "stale", "superseded"
]
DecisionLifecycle = Literal["proposed", "confirmed", "active", "superseded", "revoked", "expired"]
QuestionLifecycle = Literal["open", "answered", "partially_answered", "stale", "superseded"]
InformationLifecycle = Literal["current", "updated", "superseded", "stale", "historical"]


class LifecycleHistoryEntry(BaseModel):
    status: str
    changed_at: str
    reason: str = ""
    evidence_event_ids: list[str] = Field(default_factory=list)


class LifecycleState(BaseModel):
    """Persistent operational lifecycle for a single operational item.

    Domain-agnostic: statuses are generic (open/resolved/superseded/stale...),
    never tied to any profession, site or platform. Every transition keeps the
    evidence event ids and a human-readable reason so it stays explainable."""

    category: LifecycleCategory
    current_status: str
    previous_status: Optional[str] = None
    status_changed_at: Optional[str] = None
    status_reason: str = ""
    confidence: Confidence = "medium"
    evidence_event_ids: list[str] = Field(default_factory=list)
    last_evidence_at: Optional[str] = None
    stale_after_days: int = 14
    superseded_by: Optional[str] = None
    reopened_by: Optional[str] = None
    lifecycle_history: list[LifecycleHistoryEntry] = Field(default_factory=list)


class OperationalItem(BaseModel):
    id: str = Field(default="")
    text: str
    source: str
    confidence: Confidence = "medium"
    lifecycle: Optional[LifecycleState] = None
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
    candidate_relation_ids: list[str] = Field(default_factory=list)
    candidate_parent_ids: list[str] = Field(default_factory=list)
    candidate_child_ids: list[str] = Field(default_factory=list)
    relation_confidence_summary: dict[str, int] = Field(default_factory=dict)


class ThreadRelationCandidate(BaseModel):
    relation_id: str
    project_id: str
    source_thread_id: str
    target_thread_id: str
    relation_type: ThreadRelationType = "weak_context"
    confidence: GroupingConfidence = "low"
    score: float = 0.0
    shared_canonical_terms: list[str] = Field(default_factory=list)
    shared_context_tags: list[str] = Field(default_factory=list)
    shared_workflow_steps: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
    should_promote_to_macro: bool = False
    should_remain_candidate: bool = False
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


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
    boundary_confidence: GroupingConfidence = "low"
    split_recommendation: Optional[str] = None
    rejected_macro_links: list[str] = Field(default_factory=list)
    macro_boundary_reasons: list[str] = Field(default_factory=list)


class CanonicalOperationalTerm(BaseModel):
    canonical_id: str
    label: str
    domain: InferredChatDomain = "unknown"
    confidence: Confidence = "low"
    source_terms: list[str] = Field(default_factory=list)
    head_entity: Optional[str] = None
    action_or_problem: Optional[str] = None
    context_modifiers: list[str] = Field(default_factory=list)
    term_type: CanonicalTermType = "mixed"
    first_seen_at: Optional[str] = None
    last_seen_at: Optional[str] = None
    evidence_count: int = 0
    boundary_confidence: Confidence = "low"
    boundary_reasons: list[str] = Field(default_factory=list)


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
    canonical_terms: list[CanonicalOperationalTerm] = Field(default_factory=list)
    canonical_topic_candidates: list[str] = Field(default_factory=list)
    canonicalization_confidence: Confidence = "low"
    last_updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class OperationalLifecycleDelta(BaseModel):
    newly_opened: list[str] = Field(default_factory=list)
    newly_resolved: list[str] = Field(default_factory=list)
    newly_completed: list[str] = Field(default_factory=list)
    newly_stale: list[str] = Field(default_factory=list)
    reopened: list[str] = Field(default_factory=list)
    superseded: list[str] = Field(default_factory=list)
    unchanged_active: list[str] = Field(default_factory=list)


class LifecycleTransitionRecord(BaseModel):
    item_id: str
    category: LifecycleCategory
    text: str = ""
    previous_status: Optional[str] = None
    new_status: str
    reason: str = ""
    confidence: Confidence = "medium"
    evidence_event_ids: list[str] = Field(default_factory=list)


class OperationalLifecycleSnapshot(BaseModel):
    project_id: str
    generated_at: str
    active_tasks: list[str] = Field(default_factory=list)
    completed_tasks: list[str] = Field(default_factory=list)
    active_issues: list[str] = Field(default_factory=list)
    resolved_issues: list[str] = Field(default_factory=list)
    stale_items: list[str] = Field(default_factory=list)
    decisions_active: list[str] = Field(default_factory=list)
    decisions_superseded: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    answered_questions: list[str] = Field(default_factory=list)
    high_attention_items: list[str] = Field(default_factory=list)
    changed_since_last_snapshot: list[str] = Field(default_factory=list)
    transitions: list[LifecycleTransitionRecord] = Field(default_factory=list)
    delta: OperationalLifecycleDelta = Field(default_factory=OperationalLifecycleDelta)


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
    thread_relation_candidates: list[ThreadRelationCandidate] = Field(default_factory=list)
    adaptive_chat_profile: Optional[AdaptiveChatProfile] = None
    domain_stats: dict[str, int] = Field(default_factory=dict)
    lifecycle_snapshot: Optional[OperationalLifecycleSnapshot] = None


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
    thread_relation_candidates: list[str] = Field(default_factory=list)
    items_to_verify: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
    conversational_noise_filtered: list[str] = Field(default_factory=list)
    impact_statistics: list[str] = Field(default_factory=list)
    lifecycle_changes: list[str] = Field(default_factory=list)
    lifecycle_current_state: list[str] = Field(default_factory=list)
    lifecycle_transitions: list[str] = Field(default_factory=list)
    markdown: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
