from __future__ import annotations

import json
from pathlib import Path

import pytest

from core.operational_memory.chat_profile_engine import (
    build_adaptive_chat_profile,
    calculate_term_specificity,
    is_linguistic_fragment,
    is_operational_term,
)
from core.operational_memory.daily_report import build_daily_report
from core.operational_memory.domain_classifier import classify_event
from core.operational_memory.event_store import save_events
from core.operational_memory.macro_thread_engine import build_macro_threads
from core.operational_memory.models import Information, OperationalEvent, OperationalState, OperationalThread
from core.operational_memory.state_store import save_state
from core.operational_memory.thread_validation import (
    calculate_adaptive_profile_accuracy,
    calculate_accepted_operational_term_rate,
    calculate_generic_term_detection_rate,
    calculate_macro_thread_adaptive_precision,
    calculate_macro_thread_adaptive_recall,
    calculate_operative_report_leakage_rate,
    calculate_rejected_fragment_rate,
    calculate_specific_term_detection_rate,
    calculate_vocabulary_noise_rate,
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
    assert any("ticket 1042" in term for term in profile.specific_terms)
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


def test_construction_profile_rejects_linguistic_fragments_and_keeps_operational_terms():
    data = {
        "project_id": "profile-quality-construction",
        "events": [
            {"event_id": "q01", "sender": "p1", "timestamp": "2026-06-12T08:00:00+00:00", "content": "Area break pressione statica rumore accettabile"},
            {"event_id": "q02", "sender": "p2", "timestamp": "2026-06-12T08:05:00+00:00", "content": "Area break pressione statica da verificare"},
            {"event_id": "q03", "sender": "p1", "timestamp": "2026-06-12T08:10:00+00:00", "content": "Fancoil perde acqua in porta 034"},
            {"event_id": "q04", "sender": "p3", "timestamp": "2026-06-12T08:15:00+00:00", "content": "Griglia anti volatili da installare"},
            {"event_id": "q05", "sender": "p2", "timestamp": "2026-06-12T08:20:00+00:00", "content": "58 la davvero il break avere"},
        ],
    }
    events = _events_from_fixture(data)
    profile = build_adaptive_chat_profile(data["project_id"], events)

    assert all(is_linguistic_fragment(term) for term in ["58 la", "davvero il", "break avere", "il problema"])
    assert not {"58 la", "davvero il", "break avere"} & set(profile.specific_terms)
    assert {"area break", "pressione statica", "fancoil perde acqua", "griglia anti volatili"} & set(profile.specific_terms)
    assert calculate_vocabulary_noise_rate(profile) == 0
    assert profile.rejected_terms
    assert calculate_accepted_operational_term_rate(["area break", "pressione statica", "fancoil perde acqua"], profile) > 0


def test_logistics_family_and_support_terms_are_clean_without_technical_bias():
    logistics = _load_fixture("chat_profile_logistics_sample.json")
    family = _load_fixture("chat_profile_family_sample.json")
    support = _load_fixture("chat_profile_customer_support_sample.json")

    logistics_profile = build_adaptive_chat_profile(logistics["project_id"], _events_from_fixture(logistics))
    family_profile = build_adaptive_chat_profile(family["project_id"], _events_from_fixture(family))
    support_profile = build_adaptive_chat_profile(support["project_id"], _events_from_fixture(support))

    logistics_terms = set(logistics_profile.specific_terms + logistics_profile.topic_candidates + logistics_profile.recurring_entities)
    family_terms = set(family_profile.specific_terms + family_profile.topic_candidates + family_profile.recurring_entities)
    support_terms = set(support_profile.specific_terms + support_profile.topic_candidates + support_profile.recurring_entities)

    assert {"ordine", "magazzino", "consegna"} & logistics_terms
    assert {"scuola", "spesa", "compiti", "visita"} & family_terms
    assert {"ticket", "cliente", "errore login", "intervento", "risolto"} & support_terms
    assert not any(term in family_terms for term in {"t7", "ss01", "fancoil"})


def test_non_is_never_rendered_as_useful_generic_term():
    data = {
        "project_id": "profile-no-negation-generic",
        "events": [
            {"event_id": "n01", "sender": "p1", "timestamp": "2026-06-12T08:00:00+00:00", "content": "Non parte fancoil porta 034"},
            {"event_id": "n02", "sender": "p2", "timestamp": "2026-06-12T08:05:00+00:00", "content": "Non funziona ancora fancoil porta 034"},
            {"event_id": "n03", "sender": "p1", "timestamp": "2026-06-12T08:10:00+00:00", "content": "Non alimentato quadro porta 034"},
        ],
    }
    profile = build_adaptive_chat_profile(data["project_id"], _events_from_fixture(data))

    assert "non" not in profile.generic_terms
    assert "non" not in profile.specific_terms


@pytest.mark.asyncio
async def test_train_information_is_filtered_from_operative_only_but_available_in_full_context(monkeypatch, tmp_path):
    from core.operational_memory import event_store, state_store

    monkeypatch.setattr(event_store, "_BASE_DIR", tmp_path / "events")
    monkeypatch.setattr(state_store, "_BASE_DIR", tmp_path / "state")
    project_id = "profile-report-gate-train"
    train_text = "Il treno sta andando sulla linea normale non l'alta velocita"
    event = classify_event(
        OperationalEvent(
            event_id="train-001",
            project_id=project_id,
            source="fixture",
            sender="persona_1",
            timestamp="2026-06-12T08:00:00+00:00",
            content=train_text,
            processed_status="processed",
        )
    )
    state = OperationalState(
        project_id=project_id,
        information=[
            Information(
                text=train_text,
                source="fixture",
                confidence="high",
                source_event_id=event.event_id,
                source_timestamp=event.timestamp,
                source_sender=event.sender,
                source_excerpt=train_text,
            )
        ],
    )
    await save_events(project_id, [event])
    await save_state(project_id, state)

    operative = await build_daily_report(project_id, report_mode="OPERATIVE_ONLY")
    full = await build_daily_report(project_id, report_mode="FULL_CONTEXT")

    assert train_text not in "\n".join(operative.information)
    assert train_text in "\n".join(full.information)
    assert calculate_operative_report_leakage_rate(operative.information, [train_text]) == 0
