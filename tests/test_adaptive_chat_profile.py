from __future__ import annotations

import json
from pathlib import Path

from core.operational_memory.chat_profile_engine import build_adaptive_chat_profile, calculate_term_specificity
from core.operational_memory.domain_classifier import classify_event
from core.operational_memory.macro_thread_engine import build_macro_threads
from core.operational_memory.models import OperationalEvent, OperationalThread
from core.operational_memory.thread_validation import (
    calculate_adaptive_profile_accuracy,
    calculate_generic_term_detection_rate,
    calculate_macro_thread_adaptive_precision,
    calculate_macro_thread_adaptive_recall,
    calculate_specific_term_detection_rate,
    calculate_workflow_detection_confidence,
)
from core.operational_memory.workflow_engine import infer_workflow_patterns


FIXTURES = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _events_from_fixture(data: dict) -> list[OperationalEvent]:
    return [
        classify_event(
            OperationalEvent(
                event_id=item["event_id"],
                project_id=data["project_id"],
                source="adaptive-fixture",
                sender=item["sender"],
                timestamp=item["timestamp"],
                content=item["content"],
                processed_status="processed",
            )
        )
        for item in data["events"]
    ]


def _thread(thread_id: str, project_id: str, title: str, tags: list[str], events: list[str]) -> OperationalThread:
    return OperationalThread(
        thread_id=thread_id,
        project_id=project_id,
        title=title,
        started_at="2026-06-12T08:00:00+00:00",
        last_updated_at="2026-06-12T09:00:00+00:00",
        project_impact_score=85,
        related_event_ids=events,
        context_tags=tags,
        related_issues=[title],
    )


def test_construction_profile_infers_construction_or_maintenance():
    data = _load_fixture("chat_profile_construction_sample.json")
    events = _events_from_fixture(data)
    profile = build_adaptive_chat_profile(data["project_id"], events)
    workflow, confidence = infer_workflow_patterns(events, profile)
    profile.workflow_patterns = workflow

    assert profile.inferred_domain in {"construction_site", "maintenance"}
    assert calculate_adaptive_profile_accuracy(data["expected_domain"], profile) >= 0.8
    assert calculate_generic_term_detection_rate(data["expected_generic_terms"], profile) >= 1.0
    assert calculate_specific_term_detection_rate(data["expected_specific_terms"], profile) >= 0.5
    assert confidence > 0


def test_logistics_profile_does_not_use_construction_logic():
    data = _load_fixture("chat_profile_logistics_sample.json")
    events = _events_from_fixture(data)
    profile = build_adaptive_chat_profile(data["project_id"], events)

    assert profile.inferred_domain == "logistics"
    assert "ordine" in profile.generic_terms
    assert any(term in profile.specific_terms for term in {"ordine ax45", "magazzino nord"})
    assert "fancoil" not in profile.recurring_objects


def test_family_profile_avoids_false_technical_macro_topics():
    data = _load_fixture("chat_profile_family_sample.json")
    events = _events_from_fixture(data)
    profile = build_adaptive_chat_profile(data["project_id"], events)
    threads = [
        _thread("school", data["project_id"], "Portare bambini a scuola", ["scuola"], ["f01", "f02"]),
        _thread("shopping", data["project_id"], "Fare spesa per cena", ["spesa"], ["f03", "f05"]),
    ]
    macros = build_macro_threads(data["project_id"], threads, events, profile)

    assert profile.inferred_domain == "family_coordination"
    assert not any("T7" in macro.title or "SS01" in macro.title for macro in macros)


def test_customer_support_profile_detects_ticket_workflow():
    data = _load_fixture("chat_profile_customer_support_sample.json")
    events = _events_from_fixture(data)
    profile = build_adaptive_chat_profile(data["project_id"], events)
    workflow, confidence = infer_workflow_patterns(events, profile)
    profile.workflow_patterns = workflow

    assert profile.inferred_domain == "customer_support"
    assert "ticket 1042" in profile.specific_terms
    assert "cliente" in profile.generic_terms
    assert "completion" in "_".join(workflow) or "completion" in workflow
    assert calculate_workflow_detection_confidence(profile, confidence) > 0


def test_recurring_generic_term_is_downgraded_and_rare_discriminant_promoted():
    data = _load_fixture("chat_profile_construction_sample.json")
    events = _events_from_fixture(data)
    profile = build_adaptive_chat_profile(data["project_id"], events)

    assert "t7" in profile.generic_terms
    assert "porta 034" in profile.specific_terms
    assert profile.term_specificity["porta 034"] > profile.term_specificity["t7"]
    assert calculate_term_specificity("t7", __import__("collections").Counter({"t7": 8}), 8) < 0.5


def test_macro_threads_use_adaptive_profile_not_fixed_technical_lists():
    data = _load_fixture("chat_profile_customer_support_sample.json")
    events = _events_from_fixture(data)
    threads = [
        _thread("ticket_1042_open", data["project_id"], "Cliente Beta ticket 1042 errore login", ["ticket 1042", "cliente beta"], ["s01", "s02"]),
        _thread("ticket_1042_close", data["project_id"], "Ticket 1042 chiuso", ["ticket 1042", "cliente beta"], ["s03", "s04"]),
        _thread("ticket_1043", data["project_id"], "Cliente Alfa ticket 1043 fattura", ["ticket 1043", "cliente alfa"], ["s05", "s06"]),
    ]
    profile = build_adaptive_chat_profile(data["project_id"], events, threads)
    macros = build_macro_threads(data["project_id"], threads, events, profile)

    assert any({"ticket_1042_open", "ticket_1042_close"} <= set(macro.child_thread_ids) for macro in macros)
    assert all("ticket 1042" in macro.adaptive_patterns[0] or macro.adaptive_patterns for macro in macros)


def test_adaptive_macro_metrics_are_exposed():
    annotated = [
        {"event_id": "a", "expected_thread_label": "A", "expected_role": "opens_thread"},
        {"event_id": "b", "expected_thread_label": "B", "expected_role": "opens_thread"},
    ]
    expected = {"macro_threads": [{"expected_child_thread_labels": ["A", "B"]}]}
    threads = [
        {"thread_id": "ta", "related_event_ids": ["a"]},
        {"thread_id": "tb", "related_event_ids": ["b"]},
    ]
    macros = [{"macro_thread_id": "m", "child_thread_ids": ["ta", "tb"]}]

    assert calculate_macro_thread_adaptive_precision(annotated, expected, threads, macros) == 1.0
    assert calculate_macro_thread_adaptive_recall(annotated, expected, threads, macros) == 1.0


def test_tab_cefla_fixture_still_builds_adaptive_profile_without_special_rules():
    sample = json.loads((FIXTURES / "thread_validation_sample.json").read_text(encoding="utf-8"))
    events = [
        classify_event(
            OperationalEvent(
                event_id=item["event_id"],
                project_id="tab-cefla-adaptive-test",
                sender=item["sender"],
                timestamp=item["timestamp"],
                type=item.get("type", "text"),
                content=item["content"],
                media_description=item.get("media_description"),
                processed_status="processed",
            )
        )
        for item in sample
    ]
    profile = build_adaptive_chat_profile("tab-cefla-adaptive-test", events)

    assert profile.inferred_domain in {"construction_site", "maintenance", "engineering", "generic_group_chat"}
    assert profile.generic_terms or profile.specific_terms
