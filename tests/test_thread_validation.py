from __future__ import annotations

import json
from pathlib import Path

from core.operational_memory.domain_classifier import classify_event
from core.operational_memory.macro_thread_engine import build_macro_threads
from core.operational_memory.models import OperationalEvent, OperationalState
from core.operational_memory.thread_engine import build_threads_from_events
from core.operational_memory.thread_validation import (
    calculate_fragmentation_rate,
    calculate_macro_fragmentation_rate,
    calculate_macro_overmerge_rate,
    calculate_macro_precision,
    calculate_macro_recall,
    calculate_overmerge_rate,
    calculate_subthread_preservation_rate,
    calculate_thread_precision,
    calculate_thread_recall,
    evaluate_thread_grouping,
)


FIXTURES = Path(__file__).parent / "fixtures"


def _load_sample() -> list[dict]:
    return json.loads((FIXTURES / "thread_validation_sample.json").read_text(encoding="utf-8"))


def _load_expected() -> list[dict]:
    return json.loads((FIXTURES / "thread_validation_expected.json").read_text(encoding="utf-8"))


def _event_from_sample(item: dict) -> OperationalEvent:
    event_type = item.get("type", "text")
    event = OperationalEvent(
        event_id=item["event_id"],
        project_id="validation-demo",
        source="validation-fixture",
        sender=item["sender"],
        timestamp=item["timestamp"],
        type=event_type,
        content=item["content"],
        attachment_path=f"C:/tmp/{item['event_id']}.jpg" if event_type == "image" else None,
        attachment_type="image" if event_type == "image" else None,
        media_description=item.get("media_description"),
    )
    return classify_event(event)


def _generated_from_fixture() -> tuple[list, list[OperationalEvent]]:
    events = [_event_from_sample(item) for item in _load_sample()]
    threads, updated_events = build_threads_from_events("validation-demo", events, OperationalState(project_id="validation-demo"))
    return threads, updated_events


def _generated_macro_from_fixture():
    threads, updated_events = _generated_from_fixture()
    macro_threads = build_macro_threads("validation-demo", threads)
    return threads, updated_events, macro_threads


def test_validator_loads_annotated_dataset():
    sample = _load_sample()
    expected = _load_expected()

    assert 30 <= len(sample) <= 50
    assert len(expected["threads"]) == 15
    assert len(expected["macro_threads"]) == 4
    assert all({"event_id", "timestamp", "sender", "content", "context_tags", "expected_thread_label", "expected_role"} <= set(item) for item in sample)


def test_validator_calculates_precision_and_recall():
    sample = _load_sample()
    expected = _load_expected()
    generated_threads = [
        {"thread_id": "t7", "related_event_ids": ["val_010", "val_011", "val_012", "val_013", "val_014"]},
        {"thread_id": "ewc", "related_event_ids": ["val_006", "val_007", "val_008", "val_009"]},
    ]

    result = evaluate_thread_grouping(sample, expected, generated_threads)

    assert 0 <= result.precision <= 1
    assert 0 <= result.recall <= 1
    assert calculate_thread_precision(sample, generated_threads) == result.precision
    assert calculate_thread_recall(sample, generated_threads) == result.recall


def test_overmerge_case_is_detected():
    sample = _load_sample()
    generated_threads = [
        {"thread_id": "bad_merge", "related_event_ids": ["val_010", "val_011", "val_019"]},
    ]

    assert calculate_overmerge_rate(sample, generated_threads) > 0
    result = evaluate_thread_grouping(sample, _load_expected(), generated_threads)
    assert result.overmerge_cases


def test_fragmentation_case_is_detected():
    sample = _load_sample()
    generated_threads = [
        {"thread_id": "t7_a", "related_event_ids": ["val_010", "val_011"]},
        {"thread_id": "t7_b", "related_event_ids": ["val_012", "val_013", "val_014"]},
    ]

    assert calculate_fragmentation_rate(sample, generated_threads) > 0
    result = evaluate_thread_grouping(sample, _load_expected(), generated_threads)
    assert any(case["expected_thread_label"] == "T7_M2_NON_PARTE" for case in result.fragmentation_cases)


def test_personal_logistics_event_is_not_in_operational_thread():
    threads, updated_events = _generated_from_fixture()
    unrelated = {event.event_id: event for event in updated_events if event.event_id in {"val_029", "val_030", "val_032"}}

    assert threads
    assert all(event.thread_id is None for event in unrelated.values())


def test_media_without_ocr_has_weak_weight():
    _threads, updated_events = _generated_from_fixture()
    media_event = next(event for event in updated_events if event.event_id == "val_031")

    assert media_event.evidence_strength == "weak"


def test_follow_up_links_to_past_thread_without_auto_merge():
    threads, updated_events = _generated_from_fixture()
    follow_up = next(event for event in updated_events if event.event_id == "val_015")
    follow_up_thread = next(thread for thread in threads if follow_up.thread_id == thread.thread_id)

    assert follow_up.reopen_signal is True
    assert follow_up_thread.related_past_thread_ids
    assert "val_014" not in follow_up_thread.related_event_ids


def test_current_thread_engine_has_measurable_baseline():
    sample = _load_sample()
    expected = _load_expected()
    threads, updated_events, macro_threads = _generated_macro_from_fixture()

    result = evaluate_thread_grouping(sample, expected, threads, updated_events, macro_threads)

    assert result.event_count == 40
    assert result.expected_thread_count == 15
    assert result.generated_thread_count > 0
    assert result.fragmentation_rate >= 0
    assert result.overmerge_rate >= 0
    assert result.subthread_preservation_rate == 1.0


def test_macro_metrics_are_calculated():
    sample = _load_sample()
    expected = _load_expected()
    generated_threads = [
        {"thread_id": "ss01", "related_event_ids": ["val_021", "val_022", "val_033"]},
        {"thread_id": "stf", "related_event_ids": ["val_016", "val_017", "val_018"]},
        {"thread_id": "bdf", "related_event_ids": ["val_025", "val_026"]},
    ]
    generated_macros = [{"macro_thread_id": "macro_ss01", "child_thread_ids": ["ss01", "stf", "bdf"]}]

    assert calculate_macro_precision(sample, expected, generated_threads, generated_macros) == 1.0
    assert calculate_macro_recall(sample, expected, generated_threads, generated_macros) > 0
    assert calculate_macro_overmerge_rate(sample, expected, generated_threads, generated_macros) == 0
    assert calculate_macro_fragmentation_rate(sample, expected, generated_threads, generated_macros) >= 0
    assert calculate_subthread_preservation_rate(generated_threads, generated_macros) == 1.0


def test_ss01_related_subthreads_can_share_macro_but_remain_distinct():
    sample = _load_sample()
    expected = _load_expected()
    generated_threads = [
        {"thread_id": "ss01", "related_event_ids": ["val_021", "val_022", "val_033"]},
        {"thread_id": "stf", "related_event_ids": ["val_016", "val_017", "val_018"]},
        {"thread_id": "bdf", "related_event_ids": ["val_025", "val_026"]},
        {"thread_id": "ssle", "related_event_ids": ["val_039", "val_040"]},
    ]
    generated_macros = [{"macro_thread_id": "macro_ss01", "child_thread_ids": ["ss01", "stf", "bdf", "ssle"]}]
    result = evaluate_thread_grouping(sample, expected, generated_threads, generated_macro_threads=generated_macros)

    assert result.macro_precision == 1.0
    assert result.subthread_preservation_rate == 1.0
    assert len({thread["thread_id"] for thread in generated_threads}) == 4


def test_ewc05_threads_share_macro():
    sample = _load_sample()
    expected = _load_expected()
    generated_threads = [
        {"thread_id": "ewc_main", "related_event_ids": ["val_006", "val_007", "val_008", "val_009"]},
        {"thread_id": "ewc_follow", "related_event_ids": ["val_036"]},
    ]
    generated_macros = [{"macro_thread_id": "macro_ewc", "child_thread_ids": ["ewc_main", "ewc_follow"]}]

    assert calculate_macro_precision(sample, expected, generated_threads, generated_macros) == 1.0


def test_b02_fancoil_and_serranda_share_macro_but_remain_distinct():
    sample = _load_sample()
    expected = _load_expected()
    generated_threads = [
        {"thread_id": "b02_fancoil", "related_event_ids": ["val_037"]},
        {"thread_id": "b02_serranda", "related_event_ids": ["val_038"]},
    ]
    generated_macros = [{"macro_thread_id": "macro_b02", "child_thread_ids": ["b02_fancoil", "b02_serranda"]}]

    assert calculate_macro_precision(sample, expected, generated_threads, generated_macros) == 1.0
    assert calculate_subthread_preservation_rate(generated_threads, generated_macros) == 1.0


def test_area_break_does_not_belong_to_t7_m2_macro():
    sample = _load_sample()
    expected = _load_expected()
    generated_threads = [
        {"thread_id": "area", "related_event_ids": ["val_023", "val_024"]},
        {"thread_id": "t7m2", "related_event_ids": ["val_010", "val_011"]},
    ]
    generated_macros = [{"macro_thread_id": "bad_macro", "child_thread_ids": ["area", "t7m2"]}]

    assert calculate_macro_overmerge_rate(sample, expected, generated_threads, generated_macros) > 0


def test_social_personal_events_do_not_create_operational_macro():
    sample = _load_sample()
    expected = _load_expected()
    generated_threads = [{"thread_id": "noise", "related_event_ids": ["val_029", "val_030", "val_032"]}]
    generated_macros = [{"macro_thread_id": "bad_noise", "child_thread_ids": ["noise"]}]
    result = evaluate_thread_grouping(sample, expected, generated_threads, generated_macro_threads=generated_macros)

    assert result.macro_precision == 1.0
    assert not result.macro_overmerge_cases


def test_media_without_ocr_can_contribute_only_when_thread_linked():
    threads, updated_events, macro_threads = _generated_macro_from_fixture()
    media_event = next(event for event in updated_events if event.event_id == "val_031")

    assert media_event.evidence_strength == "weak"
    if media_event.thread_id:
        assert any(media_event.thread_id in macro.child_thread_ids for macro in macro_threads) or macro_threads == []


def test_macro_layer_does_not_merge_lifecycle_subthreads():
    threads, _updated_events, macro_threads = _generated_macro_from_fixture()
    original_thread_ids = {thread.thread_id for thread in threads}
    child_ids = {thread_id for macro in macro_threads for thread_id in macro.child_thread_ids}

    assert child_ids <= original_thread_ids
    assert len(original_thread_ids) == len({thread.thread_id for thread in threads})
