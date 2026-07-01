from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


EventType = Literal["text", "image", "pdf", "document"]


def normalize_media_category(raw_type: str | None, mime: str | None = None) -> str:
    """Generic media category from a raw platform type and/or mime, used to route
    OCR/extraction. Returns one of image|video|audio|document, or "" if no media.
    Domain/platform-agnostic — no hardcoded chat/group token."""
    t = f"{(raw_type or '').lower()} {(mime or '').lower()}"
    if not t.strip():
        return ""
    if any(k in t for k in ("image", "photo", "screenshot", "jpeg", "jpg", "png", "webp", "sticker")):
        return "image"
    if any(k in t for k in ("video", "mp4", "mov", "avi", "webm")):
        return "video"
    if any(k in t for k in ("audio", "voice", "ptt", "ogg", "opus", "mpeg", "mp3", "wav")):
        return "audio"
    if any(k in t for k in ("pdf", "document", "doc", "docx", "xls", "xlsx", "sheet", "file", "application")):
        return "document"
    return ""


def normalize_event_type(raw_type: str | None) -> EventType:
    """Map ANY attachment/media type (substring-tolerant: 'imageMessage',
    'documentMessage', 'audio/ogg', 'unknown', …) to a VALID OperationalEvent.type.
    pdf→pdf, image-like→image, everything else with media→document, empty→text.
    Never returns an invalid literal."""
    t = (raw_type or "").lower()
    if not t or t == "text":
        return "text"
    if "pdf" in t:
        return "pdf"
    if any(k in t for k in ("image", "photo", "screenshot", "jpeg", "jpg", "png", "webp", "sticker")):
        return "image"
    # document/file/audio/video/voice/unknown/unsupported/ignored/… → safe fallback
    return "document"
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
    # "single_item" | "supersession" | "contradiction" | "partial_answer" | "mitigation"
    transition_kind: str = "single_item"
    related_item_id: Optional[str] = None
    related_text: str = ""


class LifecycleItemState(BaseModel):
    item_id: str
    category: LifecycleCategory
    status: str
    text: str = ""
    first_seen_at: Optional[str] = None
    last_evidence_at: Optional[str] = None


class SnapshotDelta(BaseModel):
    previous_snapshot_id: Optional[str] = None
    previous_generated_at: Optional[str] = None
    newly_opened: list[str] = Field(default_factory=list)
    newly_completed: list[str] = Field(default_factory=list)
    newly_resolved: list[str] = Field(default_factory=list)
    newly_superseded: list[str] = Field(default_factory=list)
    newly_stale: list[str] = Field(default_factory=list)
    reopened_items: list[str] = Field(default_factory=list)
    still_active: list[str] = Field(default_factory=list)
    historical_superseded_items: list[str] = Field(default_factory=list)
    aging_attention_items: list[str] = Field(default_factory=list)
    unresolved_items_by_age: dict[str, list[str]] = Field(default_factory=dict)


class StoredLifecycleSnapshot(BaseModel):
    snapshot_id: str
    project_id: str
    generated_at: str
    item_states: list[LifecycleItemState] = Field(default_factory=list)


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
    superseded_pairs: list[LifecycleTransitionRecord] = Field(default_factory=list)
    contradictions: list[LifecycleTransitionRecord] = Field(default_factory=list)
    partially_answered_questions: list[str] = Field(default_factory=list)
    mitigated_issues: list[str] = Field(default_factory=list)
    delta: OperationalLifecycleDelta = Field(default_factory=OperationalLifecycleDelta)
    snapshot_delta: Optional["SnapshotDelta"] = None


class ReviewItem(BaseModel):
    """Extracted item NOT accepted into the active operational state, kept in a
    reviewable queue (audit / filter tuning / human decision). Never shown as an
    active task/issue/etc. nor in the main report. Non-breaking, default empty."""
    proposed_type: str = ""        # task | issue | information | question | decision | unknown
    reason: str = ""               # vague_question | meta_system | weak_task | possible_joke | missing_context | low_confidence
    confidence: Confidence = "low"
    evidence_event_id: str = ""
    timestamp: str = ""            # set at creation (state_engine)
    snippet: str = ""              # max 200 chars
    source: str = ""
    project_id: str = ""


class OperationalState(BaseModel):
    project_id: Optional[str] = None
    updated_at: Optional[str] = None
    decisions: list[Decision] = Field(default_factory=list)
    tasks: list[OperationalTask] = Field(default_factory=list)
    issues: list[Issue] = Field(default_factory=list)
    information: list[Information] = Field(default_factory=list)
    open_questions: list[OperationalQuestion] = Field(default_factory=list)
    # Non-active reviewable queue (accepted/needs_review/ignored). Empty by default
    # → non-breaking. Only `accepted` items reach the lists above.
    review_queue: list[ReviewItem] = Field(default_factory=list)
    threads: list[OperationalThread] = Field(default_factory=list)
    macro_threads: list[OperationalMacroThread] = Field(default_factory=list)
    thread_relation_candidates: list[ThreadRelationCandidate] = Field(default_factory=list)
    adaptive_chat_profile: Optional[AdaptiveChatProfile] = None
    domain_stats: dict[str, int] = Field(default_factory=dict)
    lifecycle_snapshot: Optional[OperationalLifecycleSnapshot] = None


class QueryAnswerItem(BaseModel):
    item_id: str = ""
    category: str = ""
    status: str = ""
    text: str
    confidence: Confidence = "medium"
    evidence_event_ids: list[str] = Field(default_factory=list)
    reason: str = ""
    owner: Optional[str] = None
    due: Optional[str] = None


class QueryResult(BaseModel):
    query: str
    intent: str
    summary: str = ""
    count: int = 0
    items: list[QueryAnswerItem] = Field(default_factory=list)


class OperationalDigest(BaseModel):
    project_id: str
    generated_at: str
    headline: str = ""
    open_tasks: list[QueryAnswerItem] = Field(default_factory=list)
    open_issues: list[QueryAnswerItem] = Field(default_factory=list)
    resolved_issues: list[QueryAnswerItem] = Field(default_factory=list)
    active_decisions: list[QueryAnswerItem] = Field(default_factory=list)
    unanswered_questions: list[QueryAnswerItem] = Field(default_factory=list)
    attention_items: list[QueryAnswerItem] = Field(default_factory=list)
    recent_changes: list[str] = Field(default_factory=list)


class BriefingRow(BaseModel):
    key: str
    label: str
    count: int = 0
    active: bool = True
    items: list[QueryAnswerItem] = Field(default_factory=list)
    note: str = ""


class OperationalBriefing(BaseModel):
    project_id: str
    generated_at: str
    headline: str = ""
    rows: list[BriefingRow] = Field(default_factory=list)
    synthesis: str = ""
    recommended_action: str = ""
    changes_since_previous: list[str] = Field(default_factory=list)
    markdown: str = ""


class InvocationConfig(BaseModel):
    """Per-project rules that decide when Genesi is allowed to answer. Generic:
    names/commands are configurable, never hardcoded to a chat or platform."""

    bot_names: list[str] = Field(default_factory=lambda: ["genesi"])
    command_prefixes: list[str] = Field(default_factory=lambda: ["/genesi", "!genesi"])
    respond_in_dm: bool = True
    authorized_triggers: list[str] = Field(default_factory=list)


class InvocationDecision(BaseModel):
    respond: bool = False
    mode: str = "silent"  # silent | name | tag | command | dm | trigger
    query: str = ""
    reason: str = ""


class ChatAttachment(BaseModel):
    path: Optional[str] = None
    type: Optional[str] = None  # image | pdf | document
    extracted_text: Optional[str] = None
    metadata: dict = Field(default_factory=dict)


class ChatMessage(BaseModel):
    project_id: str
    message_id: str
    text: str = ""
    sender: str = ""
    chat_id: str = ""
    source: str = "chat"
    timestamp: Optional[str] = None
    is_dm: bool = False
    attachments: list[ChatAttachment] = Field(default_factory=list)
    # Reply/quoted linkage (platform-independent). Adapters set reply_to_id to the
    # quoted/replied message id; the optional parent_* fields carry an inline
    # snapshot of the parent used as a fallback when the parent event is not (yet)
    # in the store. No platform/domain token here.
    reply_to_id: Optional[str] = None
    parent_text: str = ""
    parent_media_type: str = ""
    parent_attachment_summary: str = ""


class ChatReply(BaseModel):
    project_id: str
    invoked_by: str = ""
    intent: str = ""
    table_markdown: str = ""
    synthesis: str = ""
    actions: list[str] = Field(default_factory=list)
    evidence_event_ids: list[str] = Field(default_factory=list)
    report_id: str = ""
    report_url: str = ""
    reply_markdown: str = ""


class StoredReport(BaseModel):
    report_id: str
    project_id: str
    generated_at: str
    markdown: str = ""


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

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_event_type(cls, v):
        """Final defensive guard: no raw/platform media type (unknown, audio,
        video, imageMessage, …) can ever reach OperationalEvent.type. Closes EVERY
        construction path. Raw value is preserved by callers in attachment_type."""
        raw = v if isinstance(v, str) else ("" if v is None else str(v))
        norm = normalize_event_type(raw)
        if raw and raw not in ("text", "image", "pdf", "document") and raw != norm:
            try:
                from core.log import log
                log("OPERATIONAL_EVENT_TYPE_NORMALIZED", raw_type=raw[:24],
                    normalized_type=norm, source="event_model")
            except Exception:
                pass
        return norm
    attachment_metadata: dict = Field(default_factory=dict)
    attachment_path: Optional[str] = None
    attachment_type: Optional[str] = None
    extracted_text: Optional[str] = None
    media_description: Optional[str] = None
    extraction_status: Optional[str] = None
    extraction_confidence: Optional[Confidence] = None
    # Explicit reply/quoted binding (distinct from the semantic thread_id). When a
    # message replies to a parent (e.g. a voice note answering a photo), the child
    # event points to the parent via parent_event_id and carries the merged parent
    # context (caption + OCR/extracted_text + media_description) for extraction.
    # Evidence stays separate: parent_event_id is the parent pointer, the child's
    # own evidence is its event_id. The parent is never re-ingested.
    parent_event_id: Optional[str] = None
    reply_relation: str = ""
    parent_context: str = ""
    # Inferred-binding metadata (T-A4.1, gated). Empty for explicit reply binding.
    # {confidence, reason, candidate_count, signals[]}. Non-breaking (default {}).
    parent_binding_meta: dict = Field(default_factory=dict)
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
    media_transparency: dict[str, Any] = Field(default_factory=dict)
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
    lifecycle_superseded: list[str] = Field(default_factory=list)
    lifecycle_contradictions: list[str] = Field(default_factory=list)
    lifecycle_partially_answered: list[str] = Field(default_factory=list)
    lifecycle_mitigated: list[str] = Field(default_factory=list)
    lifecycle_temporal_delta: list[str] = Field(default_factory=list)
    lifecycle_unresolved_by_age: list[str] = Field(default_factory=list)
    lifecycle_aging_attention: list[str] = Field(default_factory=list)
    markdown: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)
