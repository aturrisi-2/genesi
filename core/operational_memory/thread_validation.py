from __future__ import annotations

from dataclasses import dataclass, field
from itertools import combinations
from typing import Any

from core.operational_memory.models import OperationalEvent, OperationalMacroThread, OperationalThread


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
    macro_precision: float = 1.0
    macro_recall: float = 1.0
    macro_overmerge_rate: float = 0.0
    macro_fragmentation_rate: float = 0.0
    subthread_preservation_rate: float = 1.0
    macro_overmerge_cases: list[dict[str, Any]] = field(default_factory=list)
    macro_fragmentation_cases: list[dict[str, Any]] = field(default_factory=list)


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


def _macro_child_thread_ids(macro: dict[str, Any] | OperationalMacroThread) -> list[str]:
    return list(macro.get("child_thread_ids", [])) if isinstance(macro, dict) else list(macro.child_thread_ids)


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


def _expected_thread_list(expected_threads: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(expected_threads, dict):
        return list(expected_threads.get("threads", []))
    return expected_threads


def _expected_macro_list(expected_threads: list[dict[str, Any]] | dict[str, Any]) -> list[dict[str, Any]]:
    if isinstance(expected_threads, dict):
        return list(expected_threads.get("macro_threads", []))
    return []


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


def _event_label_by_id(annotated_events: list[dict[str, Any]]) -> dict[str, str | None]:
    return {_event_id(event): _expected_label(event) for event in annotated_events}


def _majority_label_for_thread(
    thread: dict[str, Any] | OperationalThread,
    annotated_events: list[dict[str, Any]],
) -> str | None:
    labels = [
        label
        for event_id, label in _event_label_by_id(annotated_events).items()
        if label and event_id in set(_thread_event_ids(thread))
    ]
    if not labels:
        return None
    return max(set(labels), key=labels.count)


def _thread_label_by_generated_id(
    annotated_events: list[dict[str, Any]],
    generated_threads: list[dict[str, Any] | OperationalThread],
) -> dict[str, str]:
    labels: dict[str, str] = {}
    for thread in generated_threads:
        label = _majority_label_for_thread(thread, annotated_events)
        if label:
            labels[_thread_id(thread)] = label
    return labels


def _macro_label_sets(
    annotated_events: list[dict[str, Any]],
    generated_threads: list[dict[str, Any] | OperationalThread],
    generated_macro_threads: list[dict[str, Any] | OperationalMacroThread],
) -> list[set[str]]:
    thread_labels = _thread_label_by_generated_id(annotated_events, generated_threads)
    return [
        {thread_labels[thread_id] for thread_id in _macro_child_thread_ids(macro) if thread_id in thread_labels}
        for macro in generated_macro_threads
    ]


def _expected_macro_label_sets(expected_threads: list[dict[str, Any]] | dict[str, Any]) -> list[set[str]]:
    return [set(item.get("expected_child_thread_labels", [])) for item in _expected_macro_list(expected_threads)]


def _pair_set_from_label_sets(label_sets: list[set[str]]) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    for labels in label_sets:
        for left, right in combinations(sorted(labels), 2):
            pairs.add((left, right))
    return pairs


def calculate_macro_precision(
    annotated_events: list[dict[str, Any]],
    expected_threads: list[dict[str, Any]] | dict[str, Any],
    generated_threads: list[dict[str, Any] | OperationalThread],
    generated_macro_threads: list[dict[str, Any] | OperationalMacroThread],
) -> float:
    generated_pairs = _pair_set_from_label_sets(_macro_label_sets(annotated_events, generated_threads, generated_macro_threads))
    if not generated_pairs:
        return 1.0
    expected_pairs = _pair_set_from_label_sets(_expected_macro_label_sets(expected_threads))
    return len(generated_pairs & expected_pairs) / len(generated_pairs)


def calculate_macro_recall(
    annotated_events: list[dict[str, Any]],
    expected_threads: list[dict[str, Any]] | dict[str, Any],
    generated_threads: list[dict[str, Any] | OperationalThread],
    generated_macro_threads: list[dict[str, Any] | OperationalMacroThread],
) -> float:
    expected_pairs = _pair_set_from_label_sets(_expected_macro_label_sets(expected_threads))
    if not expected_pairs:
        return 1.0
    generated_pairs = _pair_set_from_label_sets(_macro_label_sets(annotated_events, generated_threads, generated_macro_threads))
    return len(generated_pairs & expected_pairs) / len(expected_pairs)


def calculate_macro_overmerge_rate(
    annotated_events: list[dict[str, Any]],
    expected_threads: list[dict[str, Any]] | dict[str, Any],
    generated_threads: list[dict[str, Any] | OperationalThread],
    generated_macro_threads: list[dict[str, Any] | OperationalMacroThread],
) -> float:
    return 1.0 - calculate_macro_precision(annotated_events, expected_threads, generated_threads, generated_macro_threads)


def calculate_macro_fragmentation_rate(
    annotated_events: list[dict[str, Any]],
    expected_threads: list[dict[str, Any]] | dict[str, Any],
    generated_threads: list[dict[str, Any] | OperationalThread],
    generated_macro_threads: list[dict[str, Any] | OperationalMacroThread],
) -> float:
    return 1.0 - calculate_macro_recall(annotated_events, expected_threads, generated_threads, generated_macro_threads)


def calculate_subthread_preservation_rate(
    generated_threads: list[dict[str, Any] | OperationalThread],
    generated_macro_threads: list[dict[str, Any] | OperationalMacroThread],
) -> float:
    if not generated_threads:
        return 1.0
    child_ids = [thread_id for macro in generated_macro_threads for thread_id in _macro_child_thread_ids(macro)]
    unique_child_ids = set(child_ids)
    valid_child_ids = {_thread_id(thread) for thread in generated_threads}
    if any(thread_id not in valid_child_ids for thread_id in child_ids):
        return 0.0
    if len(child_ids) != len(unique_child_ids):
        return 0.0
    return len(valid_child_ids) / len(generated_threads)


def _macro_overmerge_cases(
    annotated_events: list[dict[str, Any]],
    expected_threads: list[dict[str, Any]] | dict[str, Any],
    generated_threads: list[dict[str, Any] | OperationalThread],
    generated_macro_threads: list[dict[str, Any] | OperationalMacroThread],
) -> list[dict[str, Any]]:
    expected_sets = _expected_macro_label_sets(expected_threads)
    generated_sets = _macro_label_sets(annotated_events, generated_threads, generated_macro_threads)
    cases: list[dict[str, Any]] = []
    for macro, labels in zip(generated_macro_threads, generated_sets):
        if len(labels) < 2:
            continue
        if not any(labels <= expected for expected in expected_sets):
            macro_id = macro["macro_thread_id"] if isinstance(macro, dict) else macro.macro_thread_id
            cases.append({"macro_thread_id": macro_id, "child_thread_labels": sorted(labels)})
    return cases


def _macro_fragmentation_cases(
    annotated_events: list[dict[str, Any]],
    expected_threads: list[dict[str, Any]] | dict[str, Any],
    generated_threads: list[dict[str, Any] | OperationalThread],
    generated_macro_threads: list[dict[str, Any] | OperationalMacroThread],
) -> list[dict[str, Any]]:
    generated_pairs = _pair_set_from_label_sets(_macro_label_sets(annotated_events, generated_threads, generated_macro_threads))
    cases: list[dict[str, Any]] = []
    for macro in _expected_macro_list(expected_threads):
        labels = set(macro.get("expected_child_thread_labels", []))
        expected_pairs = _pair_set_from_label_sets([labels])
        missing = sorted(expected_pairs - generated_pairs)
        if missing:
            cases.append(
                {
                    "expected_macro_label": macro.get("expected_macro_label"),
                    "missing_child_pairs": missing,
                    "expected_child_thread_labels": sorted(labels),
                }
            )
    return cases


def evaluate_thread_grouping(
    annotated_events: list[dict[str, Any]],
    expected_threads: list[dict[str, Any]] | dict[str, Any],
    generated_threads: list[dict[str, Any] | OperationalThread],
    generated_events: list[dict[str, Any] | OperationalEvent] | None = None,
    generated_macro_threads: list[dict[str, Any] | OperationalMacroThread] | None = None,
) -> ThreadValidationResult:
    generated_macro_threads = generated_macro_threads or []
    return ThreadValidationResult(
        event_count=len(annotated_events),
        expected_thread_count=len(_expected_thread_list(expected_threads)),
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
        macro_precision=calculate_macro_precision(annotated_events, expected_threads, generated_threads, generated_macro_threads),
        macro_recall=calculate_macro_recall(annotated_events, expected_threads, generated_threads, generated_macro_threads),
        macro_overmerge_rate=calculate_macro_overmerge_rate(annotated_events, expected_threads, generated_threads, generated_macro_threads),
        macro_fragmentation_rate=calculate_macro_fragmentation_rate(annotated_events, expected_threads, generated_threads, generated_macro_threads),
        subthread_preservation_rate=calculate_subthread_preservation_rate(generated_threads, generated_macro_threads),
        macro_overmerge_cases=_macro_overmerge_cases(annotated_events, expected_threads, generated_threads, generated_macro_threads),
        macro_fragmentation_cases=_macro_fragmentation_cases(annotated_events, expected_threads, generated_threads, generated_macro_threads),
    )
