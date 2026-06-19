from __future__ import annotations

from datetime import datetime, timedelta, timezone

from core.operational_memory.domain_classifier import classify_event
from core.operational_memory.models import Issue, OperationalEvent, OperationalState, OperationalTask
from core.operational_memory.thread_engine import build_threads_from_events


def _event(event_id: str, content: str, timestamp: str, **kwargs) -> OperationalEvent:
    event = OperationalEvent(
        event_id=event_id,
        project_id="thread-demo",
        sender="Marco",
        timestamp=timestamp,
        content=content,
        **kwargs,
    )
    return classify_event(event)


def test_same_t7_m2_context_events_go_to_same_thread():
    base = "2026-06-12T08:00:00+00:00"
    events = [
        _event("evt-1", "T7 M2 non parte", base),
        _event("evt-2", "Non funziona ancora", "2026-06-12T08:20:00+00:00"),
        _event("evt-3", "La sostituisco stamattina T7 M2", "2026-06-12T08:40:00+00:00"),
    ]
    state = OperationalState(
        project_id="thread-demo",
        issues=[Issue(text="T7 M2 non parte", source="msg", source_event_id="evt-1")],
        tasks=[OperationalTask(text="Sostituire T7 M2", source="msg", source_event_id="evt-3")],
    )

    # Fixed reference clock: assert the open/in_progress lifecycle without the
    # result drifting to "stale" as wall-clock time moves past the stale window.
    reference_now = datetime(2026, 6, 12, 9, 0, tzinfo=timezone.utc)
    threads, updated_events = build_threads_from_events("thread-demo", events, state, now=reference_now)

    assert len(threads) == 1
    assert threads[0].status == "in_progress"
    assert set(threads[0].related_event_ids) == {"evt-1", "evt-2", "evt-3"}
    assert len({event.thread_id for event in updated_events}) == 1
    assert updated_events[1].thread_continuity_score >= 55
    assert "stesso codice tecnico specifico" in threads[0].continuity_signals


def test_personal_logistics_event_does_not_open_operational_thread():
    events = [_event("evt-log", "Arrivo a Termini alle 12:25", "2026-06-12T08:00:00+00:00")]

    threads, updated_events = build_threads_from_events("thread-demo", events, OperationalState(project_id="thread-demo"))

    assert threads == []
    assert updated_events[0].thread_id is None


def test_resolution_event_closes_thread():
    events = [
        _event("evt-1", "T7 M2 non parte", "2026-06-12T08:00:00+00:00"),
        _event("evt-2", "T7 M2 risolto, ok sistemato", "2026-06-12T09:00:00+00:00"),
    ]

    threads, _updated_events = build_threads_from_events("thread-demo", events, OperationalState(project_id="thread-demo"))

    assert len(threads) == 1
    assert threads[0].status == "resolved"
    assert threads[0].closed_at == "2026-06-12T09:00:00+00:00"


def test_media_event_with_same_context_links_to_thread():
    events = [
        _event("evt-1", "T7 M2 non parte", "2026-06-12T08:00:00+00:00"),
        _event(
            "evt-img",
            "",
            "2026-06-12T08:05:00+00:00",
            type="image",
            attachment_path="C:/tmp/t7-m2.jpg",
            attachment_type="image",
            attachment_metadata={"simulated_ocr": "Foto quadro T7 M2 non alimentata"},
        ),
    ]

    threads, updated_events = build_threads_from_events("thread-demo", events, OperationalState(project_id="thread-demo"))

    assert len(threads) == 1
    assert "C:/tmp/t7-m2.jpg" in threads[0].related_media
    assert updated_events[1].thread_id == threads[0].thread_id


def test_media_without_operational_context_does_not_open_thread():
    events = [
        _event(
            "evt-img",
            "",
            "2026-06-12T08:05:00+00:00",
            type="image",
            attachment_path="C:/tmp/photo.jpg",
            attachment_type="image",
            media_description="Immagine WhatsApp offline senza OCR disponibile",
        ),
    ]

    threads, updated_events = build_threads_from_events("thread-demo", events, OperationalState(project_id="thread-demo"))

    assert threads == []
    assert updated_events[0].thread_id is None


def test_thread_without_updates_can_be_marked_stale():
    old = datetime(2026, 6, 1, 8, 0, tzinfo=timezone.utc)
    now = old + timedelta(days=10)
    events = [_event("evt-1", "EWC05 manca collegamento montante", old.isoformat())]

    threads, _updated_events = build_threads_from_events(
        "thread-demo",
        events,
        OperationalState(project_id="thread-demo"),
        stale_days=7,
        now=now,
    )

    assert len(threads) == 1
    assert threads[0].status == "stale"


def test_area_break_and_t7_m2_are_not_fused_without_strong_context():
    events = [
        _event("evt-area", "Area break per avere rumore accettabile -58% la portata", "2026-06-12T08:00:00+00:00"),
        _event("evt-t7", "T7 M2 non parte", "2026-06-12T08:05:00+00:00"),
    ]

    threads, updated_events = build_threads_from_events("thread-demo", events, OperationalState(project_id="thread-demo"))

    assert len(threads) == 2
    assert updated_events[0].thread_id != updated_events[1].thread_id


def test_els07_copertura_t2_does_not_merge_with_ss01_mandata_t7():
    events = [
        _event("evt-els", "ELS07 COPERTURA T2 manca potenziometro", "2026-06-12T08:00:00+00:00"),
        _event("evt-ss01", "SS01 Mandata T7 da verificare", "2026-06-12T08:10:00+00:00"),
    ]

    threads, updated_events = build_threads_from_events("thread-demo", events, OperationalState(project_id="thread-demo"))

    assert len(threads) == 2
    assert updated_events[0].thread_id != updated_events[1].thread_id


def test_media_without_ocr_does_not_fuse_different_threads():
    events = [
        _event("evt-t7", "T7 M2 non parte", "2026-06-12T08:00:00+00:00"),
        _event(
            "evt-img",
            "",
            "2026-06-12T08:03:00+00:00",
            type="image",
            attachment_path="C:/tmp/no-ocr.jpg",
            attachment_type="image",
            media_description="Immagine WhatsApp offline senza OCR disponibile",
        ),
        _event("evt-els", "ELS07 COPERTURA T2 manca potenziometro", "2026-06-12T08:06:00+00:00"),
    ]

    threads, updated_events = build_threads_from_events("thread-demo", events, OperationalState(project_id="thread-demo"))

    assert len(threads) == 2
    assert updated_events[0].thread_id != updated_events[2].thread_id
    assert sum(1 for thread in threads if "evt-img" in thread.related_event_ids) <= 1


def test_resolution_word_closes_only_when_context_matches_thread():
    events = [
        _event("evt-t7", "T7 M2 non parte", "2026-06-12T08:00:00+00:00"),
        _event("evt-els", "ELS07 fatto", "2026-06-12T08:05:00+00:00"),
    ]

    threads, _updated_events = build_threads_from_events("thread-demo", events, OperationalState(project_id="thread-demo"))

    t7_thread = next(thread for thread in threads if "T7" in thread.context_tags)
    assert t7_thread.status != "resolved"


def test_closed_problem_creates_follow_up_related_to_past_thread():
    events = [
        _event("evt-t7", "T7 M2 non parte", "2026-06-12T08:00:00+00:00"),
        _event("evt-close", "T7 M2 risolto e verificato", "2026-06-12T09:00:00+00:00"),
        _event("evt-reopen", "T7 M2 non funziona ancora", "2026-06-13T08:00:00+00:00"),
    ]

    threads, updated_events = build_threads_from_events("thread-demo", events, OperationalState(project_id="thread-demo"))

    assert len(threads) == 2
    assert threads[0].status == "resolved"
    assert threads[1].related_past_thread_ids == [threads[0].thread_id]
    assert updated_events[-1].reopen_signal is True


def test_temporal_proximity_alone_is_not_enough_to_merge_threads():
    events = [
        _event("evt-ss01", "Domani iniziamo SS01", "2026-06-12T08:00:00+00:00"),
        _event("evt-ewc", "EWC05 manca collegamento montante", "2026-06-12T08:01:00+00:00"),
    ]

    threads, updated_events = build_threads_from_events("thread-demo", events, OperationalState(project_id="thread-demo"))

    assert len(threads) == 2
    assert updated_events[0].thread_id != updated_events[1].thread_id
