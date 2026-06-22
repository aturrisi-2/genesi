"""T-A3.1 — Reply/quoted context binding for Operational Memory (core, no host).

When a message explicitly replies to / quotes a parent (e.g. a voice note that
answers a photo with a caption + OCR), the child event must be interpreted with
the parent's context so a single, complete operational item is extracted (task +
location + technical reference + timing), not an isolated audio fragment.

This module is platform-independent: adapters only set `reply_to_id` on the
ChatMessage (mapped to `parent_event_id` on the event). Here we look the parent
event up in the store and merge its textual context into the child.

Guarantees:
  * never raises into the caller — any failure degrades to no binding;
  * never re-ingests the parent (read-only lookup, evidence stays separate);
  * never logs the full parent/child text — only ids / lengths / booleans.
"""

from __future__ import annotations

from core.log import log
from core.operational_memory.event_store import list_events
from core.operational_memory.models import OperationalEvent


def _parent_context_text(parent: OperationalEvent) -> str:
    """Merge the parent's operational text (caption + OCR/extracted_text + media
    description) into one block, de-duplicated, order preserved. Generic."""
    parts: list[str] = []
    for candidate in (parent.content, parent.extracted_text, parent.media_description):
        c = (candidate or "").strip()
        if c and c not in parts:
            parts.append(c)
    return "\n".join(parts)


async def resolve_parent_context(event: OperationalEvent, project_id: str) -> OperationalEvent:
    """Populate `event.parent_context` from the parent event when `parent_event_id`
    is set. Falls back to any inline context already on the event (seeded by the
    adapter) when the parent is not found. Mutates and returns the event. Never
    raises; never re-ingests the parent."""
    if not event.parent_event_id:
        return event
    try:
        events = await list_events(project_id)
    except Exception as exc:  # store unreadable → keep any inline context, no crash
        log("OPERATIONAL_PARENT_LOOKUP_ERROR", error=str(exc))
        return event

    parent = next((e for e in events if e.event_id == event.parent_event_id), None)
    if parent is None:
        # Parent not (yet) ingested / out of order → keep the inline snapshot if the
        # adapter provided one; the child remains a valid standalone event.
        log("OPERATIONAL_PARENT_NOT_FOUND",
            parent_event_id=str(event.parent_event_id)[:24],
            child_event_id=str(event.event_id)[:24],
            has_inline=bool((event.parent_context or "").strip()))
        return event

    merged = _parent_context_text(parent)
    if merged:
        event.parent_context = merged
    # Privacy: ids / length / type only — never the parent or child text.
    log("OPERATIONAL_PARENT_BOUND",
        parent_event_id=parent.event_id, child_event_id=event.event_id,
        parent_type=parent.type, ctx_len=len(event.parent_context or ""))
    return event
