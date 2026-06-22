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

import os
import re
from datetime import datetime, timedelta, timezone

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


# --------------------------------------------------------------------------- #
# T-A4.1 — Contextual parent inference (gated OFF, no quote/reply needed)
# --------------------------------------------------------------------------- #

# Conservative defaults. Inference is a SECONDARY strategy: it runs only when
# there is no explicit reply_to_id AND the flag is enabled. The strong explicit
# binding (PARENT_BOUND) is never altered.
INFER_WINDOW_MIN = 45        # candidate must be within this many minutes before the child
HIGH_THRESHOLD = 6.0         # minimum score to infer a parent
MARGIN = 2.0                 # best must beat the runner-up by this much (else AMBIGUOUS)

_STOPWORDS = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una", "di", "a", "da", "in",
    "con", "su", "per", "tra", "fra", "e", "ed", "o", "ma", "che", "non", "si",
    "ci", "se", "come", "dai", "poi", "anche", "lo", "ok", "allora", "cosa",
    "the", "a", "an", "to", "of", "and", "or", "is", "it", "we", "do", "ll",
}


def _inference_enabled() -> bool:
    return (os.getenv("OPERATIONAL_CONTEXT_INFERENCE_ENABLED") or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_ts(value) -> datetime:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except Exception:
        return datetime.now(timezone.utc)


def _tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^0-9a-zàèéìòù]+", (text or "").lower()) if len(t) >= 3 and t not in _STOPWORDS}


def _child_text(event: OperationalEvent) -> str:
    return " ".join(p for p in [event.content or "", event.extracted_text or ""] if p.strip())


def _author_mentioned(child_text: str, sender: str) -> bool:
    """True if the candidate's author name (first token) is named in the child."""
    name = (sender or "").strip().split()[0] if (sender or "").strip() else ""
    if len(name) < 3:
        return False
    return re.search(rf"\b{re.escape(name.lower())}\b", (child_text or "").lower()) is not None


def _score_candidate(child_event, child_text, child_tokens, child_tags, cand, gap_min):
    """Return (score, signals[], independent_count). Pure, no I/O, no text logged."""
    from core.operational_memory.context_extractor import extract_context, has_operational_context
    from core.operational_memory.thread_engine import _event_text, _has_resolution_signal, _tag_groups

    cand_text = _event_text(cand)
    cand_ctx = extract_context(cand_text)
    cand_tags = cand_ctx.context_tags
    signals: list[str] = []
    score = 0.0

    # Linking signals (independent).
    if _author_mentioned(child_text, cand.sender):
        score += 3.0
        signals.append("author_mention")

    cg, tg = _tag_groups(child_tags), _tag_groups(cand_tags)
    tech_overlap = (cg["code"] & tg["code"]) | (cg["component"] & tg["component"]) | (cg["area_location"] & tg["area_location"])
    if tech_overlap:
        score += 3.0 + (1.0 if len(tech_overlap) >= 2 else 0.0)
        signals.append("tech_overlap")

    cand_tokens = _tokens(cand_text)
    inter = child_tokens & cand_tokens
    union = child_tokens | cand_tokens
    jaccard = (len(inter) / len(union)) if union else 0.0
    if jaccard >= 0.2 and len(inter) >= 2:
        score += 2.0
        signals.append("lexical")

    # A resolved/closed candidate is demoted and does NOT count as open operational.
    cand_resolved = _has_resolution_signal(cand_text)

    # Boost-only signals (NOT counted toward the independent-link requirement).
    if has_operational_context(cand_ctx) and not cand_resolved:
        score += 2.0
        signals.append("open_operational")
    if gap_min <= 15:
        score += 1.0
    elif gap_min <= 30:
        score += 0.5

    # Penalties.
    if cand_resolved:
        score -= 4.0
        signals.append("closed_penalty")
    if len(cand_text.strip()) < 12 and not cand_tags:
        score -= 2.0
        signals.append("generic_penalty")

    independent = len({s for s in signals if s in {"author_mention", "tech_overlap", "lexical", "open_operational"}})
    return score, signals, independent


async def infer_parent_context(event: OperationalEvent, project_id: str) -> OperationalEvent:
    """Secondary, gated strategy: infer a contextual parent for a message that has
    NO explicit reply_to_id. Off unless OPERATIONAL_CONTEXT_INFERENCE_ENABLED — then
    behaviour is identical to today. Conservative: requires a high score, a margin
    over the runner-up, and >=2 independent signals with at least one linking signal
    (author/tech/lexical). Ambiguous or below threshold → no binding. Never raises;
    never re-ingests; never logs text. The explicit PARENT_BOUND path is untouched."""
    if event.parent_event_id or not _inference_enabled():
        return event
    child_text = _child_text(event)
    if not child_text.strip():
        return event
    try:
        from core.operational_memory.context_extractor import extract_context
        events = await list_events(project_id)
    except Exception as exc:
        log("OPERATIONAL_PARENT_LOOKUP_ERROR", error=str(exc), mode="inferred")
        return event

    child_time = _parse_ts(event.timestamp)
    child_tokens = _tokens(child_text)
    child_tags = extract_context(child_text).context_tags

    scored = []
    for cand in events:
        if cand.event_id == event.event_id:
            continue
        gap = (child_time - _parse_ts(cand.timestamp)).total_seconds() / 60.0
        if gap <= 0 or gap > INFER_WINDOW_MIN:
            continue
        s, sig, ind = _score_candidate(event, child_text, child_tokens, child_tags, cand, gap)
        scored.append((s, ind, sig, cand))

    if not scored:
        log("OPERATIONAL_PARENT_NOT_FOUND", child_event_id=event.event_id[:24],
            mode="inferred", reason="no_candidate_in_window")
        return event

    scored.sort(key=lambda x: x[0], reverse=True)
    best_score, best_ind, best_sig, best = scored[0]
    second_score = scored[1][0] if len(scored) > 1 else 0.0
    cc = len(scored)
    eff_threshold = HIGH_THRESHOLD + max(0, cc - 5) * 0.5  # density penalty
    has_link = any(s in {"author_mention", "tech_overlap", "lexical"} for s in best_sig)

    if best_score < eff_threshold or best_ind < 2 or not has_link:
        log("OPERATIONAL_PARENT_NOT_FOUND", child_event_id=event.event_id[:24],
            mode="inferred", best_score=round(best_score, 1), candidate_count=cc,
            independent=best_ind, reason="below_threshold")
        return event
    if (best_score - second_score) < MARGIN:
        log("OPERATIONAL_PARENT_AMBIGUOUS", child_event_id=event.event_id[:24],
            candidate_count=cc, best_score=round(best_score, 1), second_score=round(second_score, 1))
        return event

    merged = _parent_context_text(best)
    if merged:
        event.parent_context = merged
    event.parent_event_id = best.event_id
    event.reply_relation = "inferred_context"
    confidence = "high" if best_score >= eff_threshold + 2 else "medium"
    event.parent_binding_meta = {
        "confidence": confidence,
        "reason": "contextual_inference",
        "candidate_count": cc,
        "signals": best_sig,
    }
    log("OPERATIONAL_PARENT_INFERRED", parent_event_id=best.event_id,
        child_event_id=event.event_id, parent_type=best.type,
        score=round(best_score, 1), confidence=confidence,
        candidate_count=cc, signals=",".join(best_sig), ctx_len=len(event.parent_context or ""))
    return event
