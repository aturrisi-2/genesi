from __future__ import annotations

import hashlib
import re
from collections import Counter
from datetime import datetime, timezone

from core.operational_memory.models import GroupingConfidence, MacroRelation, OperationalMacroThread, OperationalThread


SYSTEM_TAGS = {"SS01", "EWC05", "ELS07", "POL-03", "UTA", "T7", "B02"}
AREA_RE = re.compile(r"^(?:L\d{1,2}|piano\s+\d{1,2}|copertura\s+t\d+|torre\s+\d+|porta\s+\d{1,4}|B\d{2})$", re.IGNORECASE)
WORK_PACKAGE_TAGS = {
    "alimentazione",
    "mandata",
    "ripresa",
    "bilanciamento",
    "serranda",
    "fancoil",
    "plenum",
    "vele",
    "vela",
    "canale",
    "collegamento",
    "collegamenti",
    "montante",
    "potenziometro",
    "valvole",
    "pressione",
    "pre riscaldo",
}
COMPONENT_FAMILY_TAGS = {"serranda", "fancoil", "plenum", "vele", "vela", "canale", "BDF", "potenziometro", "montante"}
GENERIC_SYSTEM_TAGS = {"T7", "UTA"}


def _norm(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip()).upper()


def _lower(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def _parse_timestamp(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return datetime.now(timezone.utc)


def _macro_id(project_id: str, tags: list[str]) -> str:
    seed = "|".join(_norm(tag) for tag in tags[:5]) or "macro"
    digest = hashlib.sha1(f"{project_id}:{seed}".encode("utf-8")).hexdigest()[:12]
    return f"macro_{digest}"


def _unique(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = _norm(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(value)
    return result


def _thread_tags(thread: OperationalThread) -> list[str]:
    tags = list(thread.context_tags)
    text = " ".join([thread.title, *thread.related_tasks, *thread.related_issues]).lower()
    for tag in WORK_PACKAGE_TAGS:
        if tag in text:
            tags.append(tag)
    return _unique(tags)


def detect_work_package(thread: OperationalThread) -> list[str]:
    tags = _thread_tags(thread)
    packages = []
    lowered = {_lower(tag) for tag in tags}
    text = _lower(" ".join([thread.title, *thread.related_tasks, *thread.related_issues]))
    for package in WORK_PACKAGE_TAGS:
        if package in lowered or package in text:
            packages.append(package)
    return _unique(packages)


def _system_tags(tags: list[str]) -> set[str]:
    return {_norm(tag) for tag in tags if _norm(tag) in SYSTEM_TAGS}


def _area_tags(tags: list[str]) -> set[str]:
    return {_norm(tag) for tag in tags if AREA_RE.match(tag)}


def _component_tags(tags: list[str]) -> set[str]:
    return {_norm(tag) for tag in tags if _norm(tag) in {_norm(value) for value in COMPONENT_FAMILY_TAGS}}


def _work_package_tags(tags: list[str]) -> set[str]:
    return {_lower(tag) for tag in tags if _lower(tag) in WORK_PACKAGE_TAGS}


def _specific_system_overlap(left: set[str], right: set[str]) -> set[str]:
    overlap = left & right
    specific = {tag for tag in overlap if tag not in GENERIC_SYSTEM_TAGS}
    return specific or overlap


def _relation_for_threads(left: OperationalThread, right: OperationalThread) -> MacroRelation | None:
    left_tags = _thread_tags(left)
    right_tags = _thread_tags(right)
    system_overlap = _specific_system_overlap(_system_tags(left_tags), _system_tags(right_tags))
    if system_overlap:
        return "same_system"
    if _area_tags(left_tags) & _area_tags(right_tags):
        return "same_area"
    if _work_package_tags(left_tags) & _work_package_tags(right_tags):
        return "same_work_package"
    if _component_tags(left_tags) & _component_tags(right_tags):
        return "same_component_family"
    return None


def calculate_macro_similarity(left: OperationalThread, right: OperationalThread) -> float:
    left_tags = _thread_tags(left)
    right_tags = _thread_tags(right)
    score = 0.0
    system_overlap = _specific_system_overlap(_system_tags(left_tags), _system_tags(right_tags))
    if system_overlap:
        score += 0.45
    if _area_tags(left_tags) & _area_tags(right_tags):
        score += 0.25
    if _work_package_tags(left_tags) & _work_package_tags(right_tags):
        score += 0.20
    if _component_tags(left_tags) & _component_tags(right_tags):
        score += 0.15
    return min(score, 1.0)


def calculate_macro_confidence(threads: list[OperationalThread]) -> GroupingConfidence:
    if len(threads) >= 3:
        return "high"
    if len(threads) == 2:
        return "medium"
    return "low"


def _macro_title(tags: list[str]) -> str:
    systems = [tag for tag in tags if _norm(tag) in SYSTEM_TAGS]
    packages = [tag for tag in tags if _lower(tag) in WORK_PACKAGE_TAGS]
    areas = [tag for tag in tags if AREA_RE.match(tag)]
    parts = _unique([*systems[:2], *areas[:1], *packages[:2]])
    return " / ".join(parts) if parts else "Macro-thread operativo"


def summarize_macro_thread(macro: OperationalMacroThread, child_threads: list[OperationalThread]) -> str:
    open_count = len([thread for thread in child_threads if thread.status in {"open", "in_progress", "waiting", "stale"}])
    resolved_count = len([thread for thread in child_threads if thread.status == "resolved"])
    return (
        f"{macro.title}: {len(child_threads)} sottothread collegati, "
        f"{open_count} aperti/stale, {resolved_count} risolti."
    )


def _status_for_macro(child_threads: list[OperationalThread]) -> str:
    if any(thread.status in {"open", "in_progress", "waiting"} for thread in child_threads):
        return "open"
    if any(thread.status == "stale" for thread in child_threads):
        return "stale"
    return "resolved"


def _macro_from_threads(project_id: str, child_threads: list[OperationalThread]) -> OperationalMacroThread:
    context_tags = _unique([tag for thread in child_threads for tag in _thread_tags(thread)])
    started_at = min(child_threads, key=lambda thread: _parse_timestamp(thread.started_at)).started_at
    last_updated_at = max(child_threads, key=lambda thread: _parse_timestamp(thread.last_updated_at)).last_updated_at
    macro = OperationalMacroThread(
        macro_thread_id=_macro_id(project_id, context_tags),
        project_id=project_id,
        title=_macro_title(context_tags),
        status=_status_for_macro(child_threads),
        started_at=started_at,
        last_updated_at=last_updated_at,
        context_tags=context_tags,
        child_thread_ids=[thread.thread_id for thread in child_threads],
        related_event_ids=_unique([event_id for thread in child_threads for event_id in thread.related_event_ids]),
        confidence=calculate_macro_confidence(child_threads),
        open_items_count=sum(len(thread.related_tasks) + len(thread.unresolved_questions) for thread in child_threads if thread.status != "resolved"),
        critical_items_count=len([thread for thread in child_threads if thread.project_impact_score >= 80]),
    )
    macro.summary = summarize_macro_thread(macro, child_threads)
    return macro


def assign_thread_to_macro(thread: OperationalThread, macro_threads: list[OperationalMacroThread]) -> OperationalMacroThread | None:
    best_macro = None
    best_score = 0.0
    pseudo_threads = [
        OperationalThread(
            thread_id=macro.macro_thread_id,
            project_id=macro.project_id,
            title=macro.title,
            started_at=macro.started_at,
            last_updated_at=macro.last_updated_at,
            context_tags=macro.context_tags,
        )
        for macro in macro_threads
    ]
    for macro, pseudo in zip(macro_threads, pseudo_threads):
        score = calculate_macro_similarity(thread, pseudo)
        if score > best_score:
            best_macro = macro
            best_score = score
    return best_macro if best_score > 0 else None


def build_macro_threads(project_id: str, threads: list[OperationalThread]) -> list[OperationalMacroThread]:
    candidates = [thread for thread in threads if thread.related_event_ids and thread.project_impact_score >= 50]
    groups: list[list[OperationalThread]] = []

    for thread in candidates:
        matched_group = None
        best_score = 0.0
        for group in groups:
            score = max(calculate_macro_similarity(thread, existing) for existing in group)
            if score > best_score:
                best_score = score
                matched_group = group
        if matched_group is not None and best_score > 0:
            matched_group.append(thread)
        else:
            groups.append([thread])

    macro_threads = [_macro_from_threads(project_id, group) for group in groups if len(group) >= 2]
    macro_by_child: dict[str, OperationalMacroThread] = {}
    for macro in macro_threads:
        for child_id in macro.child_thread_ids:
            macro_by_child[child_id] = macro

    for thread in threads:
        macro = macro_by_child.get(thread.thread_id)
        if macro is None:
            thread.macro_thread_id = None
            thread.parent_thread_id = None
            thread.macro_title = None
            thread.macro_context_tags = []
            thread.macro_confidence = "low"
            thread.relation_to_macro = None
            continue
        thread.macro_thread_id = macro.macro_thread_id
        thread.parent_thread_id = macro.macro_thread_id
        thread.thread_level = "subthread"
        thread.macro_title = macro.title
        thread.macro_context_tags = list(macro.context_tags)
        thread.macro_confidence = macro.confidence
        thread.relation_to_macro = _relation_for_threads(
            thread,
            next(candidate for candidate in threads if candidate.thread_id != thread.thread_id and candidate.thread_id in macro.child_thread_ids),
        ) or "weak_relation"

    return macro_threads
