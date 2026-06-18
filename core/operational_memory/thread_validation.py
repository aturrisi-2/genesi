from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from core.operational_memory.models import OperationalEvent, OperationalThread


OPERATIONAL_ROLES = {"opens_thread", "continues_thread", "closes_thread", "weak_evidence", "follow_up"}


@dataclass
class ThreadValidationResult:
    event_count: int
    expected_thread_count: int
    generated_thread_count: int
    precision: float
    recall: float
    overmerge_rate: float
    fragmentation_rate: float
    orphan_operational_events: list[str] = field(default_factory=list)
    wrong_thread_assignments: list[dict[str, Any]] = field(default_factory=list)
    overmerge_cases: list[dict[str, Any]] = field(default_factory=list)
    fragmentation_cases: list[dict[str, Any]] = field(default_factory=list)
    related_past_thread_ids_created: int = 0


def _event_id(event: dict[str, Any] | OperationalEvent) -> str:
    return event["event_id"] if isinstance(event, dict) else event.event_id


def _event_role(event: dict[str, Any] | OperationalEvent) -> str:
    if isinstance(event, dict):
        return str(event.get("expected_role") or "")
    return ""


def _expected_label(event: dict[str, Any] | OperationalEvent) -> str | None:
    if isinstance(event, dict):
        label = event.get("expected_thread_label")
        return str(label) if label else None
    return None


def _generated_thread_id(event: dict[str, Any] | OperationalEvent) -> str | None:
    if isinstance(event, dict):
        value = event.get("generated_thread_id") or event.get("thread_id")
        return str(value) if value else None
    return event.thread_id


def _thread_id(thread: dict[str, Any] | OperationalThread) -> str:
    return thread["thread_id"] if isinstance(thread, dict) else thread.thread_id


def _thread_event_ids(thread: dict[str, Any] | OperationalThread) -> list[str]:
    return list(thread.get("related_event_ids", [])) if isinstance(thread, dict) else list(thread.related_event_ids)


def _related_past_thread_ids(thread: dict[str, Any] | OperationalThread) -> list[str]:
    if isinstance(thread, dict):
        return list(thread.get("related_past_thread_ids", []))
    return list(thread.related_past_thread_ids)


def _expected_operational_events(annotated_events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        event
        for event in annotated_events
        if _expected_label(event) and _event_role(event) in OPERATIONAL_ROLES
    ]


def _expected_pairs(annotated_events: list[dict[str, Any]]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    events = _expected_operational_events(annotated_events)
    for left, right in combinations(events, 2):
        if _expected_label(left) == _expected_label(right):
            pairs.add(tuple(sorted((_event_id(left), _event_id(right)))))
    return pairs


def _generated_pairs(generated_threads: list[dict[str, Any] | OperationalThread]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for thread in generated_threads:
        for left, right in combinations(sorted(set(_thread_event_ids(thread))), 2):
            pairs.add((left, right))
    return pairs


def _label_by_event(annotated_events: list[dict[str, Any]]) -> dict[str, str | None]:
    return {_event_id(event): _expected_label(event) for event in annotated_events}


def _thread_by_event(
    generated_threads: list[dict[str, Any] | OperationalThread],
    generated_events: list[dict[str, Any] | OperationalEvent] | None = None,
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for thread in generated_threads:
        for event_id in _thread_event_ids(thread):
            mapping[event_id] = _thread_id(thread)
    for event in generated_events or []:
        thread_id = _generated_thread_id(event)
        if thread_id:
            mapping[_event_id(event)] = thread_id
    return mapping


def calculate_thread_precision(
    annotated_events: list[dict[str, Any]],
    generated_threads: list[dict[str, Any] | OperationalThread],
) -> float:
    generated_pairs = _generated_pairs(generated_threads)
    if not generated_pairs:
        return 1.0
    labels = _label_by_event(annotated_events)
    correct = 0
    for left, right in generated_pairs:
        if labels.get(left) and labels.get(left) == labels.get(right):
            correct += 1
    return correct / len(generated_pairs)


def calculate_thread_recall(
    annotated_events: list[dict[str, Any]],
    generated_threads: list[dict[str, Any] | OperationalThread],
) -> float:
    expected_pairs = _expected_pairs(annotated_events)
    if not expected_pairs:
        return 1.0
    generated_pairs = _generated_pairs(generated_threads)
    return len(expected_pairs & generated_pairs) / len(expected_pairs)


def calculate_overmerge_rate(
    annotated_events: list[dict[str, Any]],
    generated_threads: list[dict[str, Any] | OperationalThread],
) -> float:
    generated_pairs = _generated_pairs(generated_threads)
    if not generated_pairs:
        return 0.0
    labels = _label_by_event(annotated_events)
    wrong = 0
    for left, right in generated_pairs:
        if labels.get(left) != labels.get(right):
            wrong += 1
    return wrong / len(generated_pairs)


def calculate_fragmentation_rate(
    annotated_events: list[dict[str, Any]],
    generated_threads: list[dict[str, Any] | OperationalThread],
) -> float:
    expected_pairs = _expected_pairs(annotated_events)
    if not expected_pairs:
        return 0.0
    generated_pairs = _generated_pairs(generated_threads)
    missing = expected_pairs - generated_pairs
    return len(missing) / len(expected_pairs)


def _overmerge_cases(
    annotated_events: list[dict[str, Any]],
    generated_threads: list[dict[str, Any] | OperationalThread],
) -> list[dict[str, Any]]:
    labels = _label_by_event(annotated_events)
    cases: list[dict[str, Any]] = []
    for thread in generated_threads:
        grouped: dict[str | None, list[str]] = {}
        for event_id in _thread_event_ids(thread):
            grouped.setdefault(labels.get(event_id), []).append(event_id)
        non_empty_labels = [label for label in grouped if label]
        if len(non_empty_labels) > 1:
            cases.append(
                {
                    "thread_id": _thread_id(thread),
                    "labels": {str(label): ids for label, ids in grouped.items() if label},
                }
            )
    return cases


def _fragmentation_cases(
    annotated_events: list[dict[str, Any]],
    generated_threads: list[dict[str, Any] | OperationalThread],
    generated_events: list[dict[str, Any] | OperationalEvent] | None = None,
) -> list[dict[str, Any]]:
    thread_by_event = _thread_by_event(generated_threads, generated_events)
    by_label: dict[str, list[str]] = {}
    for event in _expected_operational_events(annotated_events):
        by_label.setdefault(_expected_label(event) or "", []).append(_event_id(event))

    cases: list[dict[str, Any]] = []
    for label, event_ids in by_label.items():
        generated_ids = {thread_by_event.get(event_id) for event_id in event_ids if thread_by_event.get(event_id)}
        missing = [event_id for event_id in event_ids if not thread_by_event.get(event_id)]
        if len(generated_ids) > 1 or missing:
            cases.append(
                {
                    "expected_thread_label": label,
                    "generated_thread_ids": sorted(generated_ids),
                    "missing_event_ids": missing,
                    "expected_event_ids": event_ids,
                }
            )
    return cases


def _orphan_operational_events(
    annotated_events: list[dict[str, Any]],
    generated_threads: list[dict[str, Any] | OperationalThread],
    generated_events: list[dict[str, Any] | OperationalEvent] | None = None,
) -> list[str]:
    thread_by_event = _thread_by_event(generated_threads, generated_events)
    return [
        _event_id(event)
        for event in _expected_operational_events(annotated_events)
        if _event_role(event) != "weak_evidence" and not thread_by_event.get(_event_id(event))
    ]


def _wrong_thread_assignments(
    annotated_events: list[dict[str, Any]],
    generated_threads: list[dict[str, Any] | OperationalThread],
) -> list[dict[str, Any]]:
    labels = _label_by_event(annotated_events)
    issues: list[dict[str, Any]] = []
    for thread in generated_threads:
        event_ids = _thread_event_ids(thread)
        labels_in_thread = [labels.get(event_id) for event_id in event_ids if labels.get(event_id)]
        if not labels_in_thread:
            continue
        majority = max(set(labels_in_thread), key=labels_in_thread.count)
        for event_id in event_ids:
            label = labels.get(event_id)
            if label and label != majority:
                issues.append(
                    {
                        "event_id": event_id,
                        "expected_thread_label": label,
                        "generated_thread_id": _thread_id(thread),
                        "majority_thread_label": majority,
                    }
                )
    return issues


def evaluate_thread_grouping(
    annotated_events: list[dict[str, Any]],
    expected_threads: list[dict[str, Any]],
    generated_threads: list[dict[str, Any] | OperationalThread],
    generated_events: list[dict[str, Any] | OperationalEvent] | None = None,
) -> ThreadValidationResult:
    return ThreadValidationResult(
        event_count=len(annotated_events),
        expected_thread_count=len(expected_threads),
        generated_thread_count=len(generated_threads),
        precision=calculate_thread_precision(annotated_events, generated_threads),
        recall=calculate_thread_recall(annotated_events, generated_threads),
        overmerge_rate=calculate_overmerge_rate(annotated_events, generated_threads),
        fragmentation_rate=calculate_fragmentation_rate(annotated_events, generated_threads),
        orphan_operational_events=_orphan_operational_events(annotated_events, generated_threads, generated_events),
        wrong_thread_assignments=_wrong_thread_assignments(annotated_events, generated_threads),
        overmerge_cases=_overmerge_cases(annotated_events, generated_threads),
        fragmentation_cases=_fragmentation_cases(annotated_events, generated_threads, generated_events),
        related_past_thread_ids_created=len(
            {thread_id for thread in generated_threads for thread_id in _related_past_thread_ids(thread)}
        ),
    )
