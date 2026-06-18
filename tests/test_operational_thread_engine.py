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

    threads, updated_events = build_threads_from_events("thread-demo", events, state)

    assert len(threads) == 1
    assert threads[0].status == "in_progress"
    assert set(threads[0].related_event_ids) == {"evt-1", "evt-2", "evt-3"}
    assert len({event.thread_id for event in updated_events}) == 1


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
