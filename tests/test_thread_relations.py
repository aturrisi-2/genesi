from __future__ import annotations

from core.operational_memory.chat_profile_engine import build_adaptive_chat_profile
from core.operational_memory.domain_classifier import classify_event
from core.operational_memory.macro_thread_engine import build_macro_threads
from core.operational_memory.models import OperationalEvent, OperationalThread
from core.operational_memory.thread_relation_engine import (
    build_thread_relation_candidates,
    calculate_canonical_discriminative_power,
    score_thread_relation,
)
from core.operational_memory.thread_validation import (
    calculate_candidate_relation_count,
    calculate_false_macro_prevention_rate,
    calculate_isolated_thread_rate,
    calculate_promoted_relation_count,
    calculate_rejected_relation_count,
    calculate_useful_unassigned_thread_rate,
    evaluate_thread_grouping,
)


def _event(project_id: str, event_id: str, content: str) -> OperationalEvent:
    return classify_event(
        OperationalEvent(
            event_id=event_id,
            project_id=project_id,
            source="relation-fixture",
            sender="persona_1",
            timestamp="2026-06-12T08:00:00+00:00",
            content=content,
            processed_status="processed",
        )
    )


def _thread(thread_id: str, project_id: str, title: str, tags: list[str], event_id: str) -> OperationalThread:
    return OperationalThread(
        thread_id=thread_id,
        project_id=project_id,
        title=title,
        started_at="2026-06-12T08:00:00+00:00",
        last_updated_at="2026-06-12T09:00:00+00:00",
        project_impact_score=85,
        related_event_ids=[event_id],
        context_tags=tags,
        related_issues=[title],
    )


def _profile(project_id: str, messages: list[str], threads: list[OperationalThread]):
    events = [_event(project_id, f"evt-{index}", message) for index, message in enumerate(messages)]
    return build_adaptive_chat_profile(project_id, events, threads), events


def test_same_object_and_problem_creates_high_candidate_relation():
    project_id = "relation-same-object-problem"
    threads = [
        _thread("a", project_id, "Pompa P12 non parte", ["pompa p12"], "evt-0"),
        _thread("b", project_id, "Pompa P12 non funziona ancora", ["pompa p12"], "evt-1"),
    ]
    profile, _events = _profile(project_id, [thread.title for thread in threads], threads)

    relation = score_thread_relation(threads[0], threads[1], profile)

    assert relation.confidence == "high"
    assert relation.relation_type in {"same_problem", "same_work_package"}
    assert relation.should_promote_to_macro is True


def test_same_location_different_problem_stays_medium_candidate_not_macro():
    project_id = "relation-same-location"
    threads = [
        _thread("leak", project_id, "Magazzino nord scaffale 3 perde acqua", ["magazzino nord"], "evt-0"),
        _thread("door", project_id, "Magazzino nord porta bloccata", ["magazzino nord"], "evt-1"),
    ]
    profile, _events = _profile(project_id, [thread.title for thread in threads], threads)

    relation = score_thread_relation(threads[0], threads[1], profile)

    assert relation.confidence == "medium"
    assert relation.relation_type == "same_location"
    assert relation.should_remain_candidate is True
    assert relation.should_promote_to_macro is False


def test_generic_shared_word_does_not_create_useful_relation():
    project_id = "relation-generic-only"
    threads = [
        _thread("a", project_id, "Problema da verificare", ["problema"], "evt-0"),
        _thread("b", project_id, "Verifica completata", ["verifica"], "evt-1"),
    ]
    profile, _events = _profile(project_id, [thread.title for thread in threads], threads)

    relation = score_thread_relation(threads[0], threads[1], profile)

    assert relation.confidence == "low"
    assert relation.should_remain_candidate is False
    assert relation.should_promote_to_macro is False


def test_medium_relation_is_not_promoted_automatically_to_macro():
    project_id = "relation-medium-not-promoted"
    threads = [
        _thread("a", project_id, "Area est consegna materiale in ritardo", ["area est"], "evt-0"),
        _thread("b", project_id, "Area est accesso porta bloccato", ["area est"], "evt-1"),
    ]
    profile, events = _profile(project_id, [thread.title for thread in threads], threads)
    relations = build_thread_relation_candidates(project_id, threads, events, profile)
    macros = build_macro_threads(project_id, threads, events, profile)

    assert any(relation.confidence == "medium" for relation in relations)
    assert not any(relation.should_promote_to_macro for relation in relations)
    assert macros == []


def test_high_relation_and_low_heterogeneity_can_be_promoted():
    project_id = "relation-high-promoted"
    threads = [
        _thread("a", project_id, "Ticket 1042 errore login cliente beta", ["ticket 1042", "errore login"], "evt-0"),
        _thread("b", project_id, "Errore login ticket 1042 risolto", ["ticket 1042", "errore login"], "evt-1"),
    ]
    profile, events = _profile(project_id, [thread.title for thread in threads], threads)
    relations = build_thread_relation_candidates(project_id, threads, events, profile)

    assert any(relation.should_promote_to_macro for relation in relations)
    assert calculate_promoted_relation_count(relations) == 1


def test_logistics_delay_does_not_fuse_with_warehouse_personnel():
    project_id = "relation-logistics"
    threads = [
        _thread("order", project_id, "Ordine AX45 consegna in ritardo", ["ordine ax45"], "evt-0"),
        _thread("order-follow", project_id, "Consegna ordine AX45 confermata domani", ["ordine ax45"], "evt-1"),
        _thread("warehouse", project_id, "Magazzino nord turno personale confermato", ["magazzino nord"], "evt-2"),
    ]
    profile, events = _profile(project_id, [thread.title for thread in threads], threads)
    relations = build_thread_relation_candidates(project_id, threads, events, profile)

    promoted_pairs = {frozenset([relation.source_thread_id, relation.target_thread_id]) for relation in relations if relation.should_promote_to_macro}
    assert frozenset(["order", "order-follow"]) in promoted_pairs
    assert all("warehouse" not in pair for pair in promoted_pairs)


def test_family_school_links_deadline_but_not_shopping_or_health():
    project_id = "relation-family"
    threads = [
        _thread("school", project_id, "Scuola compiti scadenza venerdi", ["scuola", "compiti"], "evt-0"),
        _thread("deadline", project_id, "Compiti scuola da consegnare domani", ["scuola", "compiti"], "evt-1"),
        _thread("shopping", project_id, "Spesa cena da fare", ["spesa"], "evt-2"),
        _thread("health", project_id, "Visita medica confermata", ["visita"], "evt-3"),
    ]
    profile, events = _profile(project_id, [thread.title for thread in threads], threads)
    relations = build_thread_relation_candidates(project_id, threads, events, profile)

    useful_pairs = {frozenset([relation.source_thread_id, relation.target_thread_id]) for relation in relations if relation.confidence != "low"}
    assert frozenset(["school", "deadline"]) in useful_pairs
    assert all(frozenset(["school", other]) not in useful_pairs for other in ["shopping", "health"])


def test_customer_support_login_does_not_merge_with_billing_problem():
    project_id = "relation-support"
    threads = [
        _thread("login", project_id, "Ticket 1042 errore login cliente beta", ["ticket 1042", "errore login"], "evt-0"),
        _thread("login-fix", project_id, "Intervento ticket 1042 errore login risolto", ["ticket 1042", "errore login"], "evt-1"),
        _thread("billing", project_id, "Ticket 1043 fattura errata cliente beta", ["ticket 1043", "fattura"], "evt-2"),
    ]
    profile, events = _profile(project_id, [thread.title for thread in threads], threads)
    relations = build_thread_relation_candidates(project_id, threads, events, profile)

    promoted_pairs = {frozenset([relation.source_thread_id, relation.target_thread_id]) for relation in relations if relation.should_promote_to_macro}
    assert frozenset(["login", "login-fix"]) in promoted_pairs
    assert all("billing" not in pair for pair in promoted_pairs)


def test_relation_metrics_expose_useful_unassigned_threads():
    annotated = [
        {"event_id": "a", "expected_thread_label": "ORDER_DELAY", "expected_role": "opens_thread"},
        {"event_id": "b", "expected_thread_label": "ORDER_DELAY", "expected_role": "follow_up"},
    ]
    project_id = "relation-metrics"
    threads = [
        _thread("order", project_id, "Ordine AX45 consegna in ritardo", ["ordine ax45"], "a"),
        _thread("follow", project_id, "Consegna ordine AX45 confermata domani", ["ordine ax45"], "b"),
    ]
    profile, events = _profile(project_id, [thread.title for thread in threads], threads)
    relations = build_thread_relation_candidates(project_id, threads, events, profile)
    result = evaluate_thread_grouping(annotated, {"threads": []}, threads, generated_thread_relations=relations, adaptive_profile=profile)

    assert calculate_candidate_relation_count(relations) >= 0
    assert calculate_rejected_relation_count(relations) >= 0
    assert result.candidate_relation_count == calculate_candidate_relation_count(relations)
    assert result.candidate_relation_precision >= 0
    assert result.candidate_relation_recall >= 0
    assert calculate_useful_unassigned_thread_rate(threads, [], relations) > 0
    assert calculate_isolated_thread_rate(threads, [], relations) < 1
    assert calculate_false_macro_prevention_rate(threads, [], relations) >= 0


def test_relation_pruning_limits_many_similar_threads_without_hardcoded_terms():
    project_id = "relation-pruning-generic"
    threads = [
        _thread(f"thread-{index}", project_id, f"Area comune modulo {index} da verificare", ["area comune"], f"evt-{index}")
        for index in range(20)
    ]
    profile, events = _profile(project_id, [thread.title for thread in threads], threads)
    stats: dict = {}

    relations = build_thread_relation_candidates(
        project_id,
        threads,
        events,
        profile,
        relation_max_candidates_per_thread=3,
        stats=stats,
    )

    assert stats["raw_pairs"] == 190
    assert stats["pruned_pairs"] > 0
    assert len(relations) < stats["raw_pairs"]
    assert max(len(thread.candidate_relation_ids) for thread in threads) <= 6


def test_diffuse_canonical_term_is_penalized_generically():
    project_id = "relation-diffuse-canonical"
    threads = [
        _thread(f"thread-{index}", project_id, f"Cliente alfa tema {index} da verificare", ["cliente alfa"], f"evt-{index}")
        for index in range(12)
    ]
    profile, events = _profile(project_id, [thread.title for thread in threads], threads)

    powers = [
        calculate_canonical_discriminative_power(canonical.label, profile, threads)
        for canonical in profile.canonical_terms
    ]
    stats: dict = {}
    build_thread_relation_candidates(project_id, threads, events, profile, stats=stats)

    assert powers
    assert min(powers) < 0.75
    assert stats["raw_pairs"] >= stats["kept_pairs"]
