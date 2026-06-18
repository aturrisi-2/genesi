import json
from unittest.mock import AsyncMock

import pytest

from core.operational_memory.event_store import list_events
from core.operational_memory.models import OperationalEvent
from core.operational_memory.state_engine import get_project_state
from core.operational_memory.watcher_engine import (
    get_events,
    ingest_event,
    process_pending_events,
)


@pytest.fixture()
def isolated_operational_storage(monkeypatch, tmp_path):
    monkeypatch.setattr("core.operational_memory.event_store._BASE_DIR", tmp_path / "events")
    monkeypatch.setattr("core.operational_memory.state_store._BASE_DIR", tmp_path / "state")


@pytest.mark.asyncio
async def test_ingests_text_event(isolated_operational_storage):
    event = OperationalEvent(
        event_id="evt-001",
        project_id="site-001",
        source="simulated-whatsapp",
        sender="Marco",
        type="text",
        content="Verifico il materiale domani",
    )

    stored, created = await ingest_event(event)
    events = await get_events("site-001")

    assert created is True
    assert stored.processed_status == "pending"
    assert len(events) == 1
    assert events[0].sender == "Marco"


@pytest.mark.asyncio
async def test_deduplicates_events_by_event_id(isolated_operational_storage):
    event = OperationalEvent(
        event_id="evt-dup",
        project_id="site-001",
        sender="Marco",
        type="text",
        content="Prima versione",
    )
    duplicate = OperationalEvent(
        event_id="evt-dup",
        project_id="site-001",
        sender="Luca",
        type="text",
        content="Seconda versione",
    )

    first, first_created = await ingest_event(event)
    second, second_created = await ingest_event(duplicate)
    events = await get_events("site-001")

    assert first_created is True
    assert second_created is False
    assert first.event_id == second.event_id
    assert len(events) == 1
    assert events[0].content == "Prima versione"


@pytest.mark.asyncio
async def test_process_pending_updates_state_and_marks_processed(monkeypatch, isolated_operational_storage):
    payload = {
        "decisions": [],
        "tasks": [{"text": "Verificare il materiale", "owner": "Marco", "due": "domani", "source": "msg 1"}],
        "issues": [],
        "information": [],
        "open_questions": [],
    }
    mock_call = AsyncMock(return_value=json.dumps(payload))
    monkeypatch.setattr("core.operational_memory.extractor.llm_service._call_model", mock_call)

    await ingest_event(OperationalEvent(
        event_id="evt-002",
        project_id="site-001",
        sender="Marco",
        type="text",
        content="Verifico il materiale domani",
    ))

    result = await process_pending_events("site-001")
    events = await list_events("site-001")
    state = await get_project_state("site-001")

    assert result["processed"] == 1
    assert result["failed"] == 0
    assert events[0].processed_status == "processed"
    assert len(state.tasks) == 1
    assert state.tasks[0].owner == "Marco"
    mock_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_processed_event_is_not_reprocessed(monkeypatch, isolated_operational_storage):
    payload = {
        "decisions": [],
        "tasks": [{"text": "Verificare il materiale", "owner": "Marco", "due": None, "source": "msg 1"}],
        "issues": [],
        "information": [],
        "open_questions": [],
    }
    mock_call = AsyncMock(return_value=json.dumps(payload))
    monkeypatch.setattr("core.operational_memory.extractor.llm_service._call_model", mock_call)

    await ingest_event(OperationalEvent(
        event_id="evt-003",
        project_id="site-001",
        sender="Marco",
        type="text",
        content="Verifico il materiale",
    ))

    first = await process_pending_events("site-001")
    second = await process_pending_events("site-001")
    state = await get_project_state("site-001")

    assert first["processed"] == 1
    assert second["processed"] == 0
    assert len(state.tasks) == 1
    mock_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_image_event_uses_simulated_attachment_text(monkeypatch, isolated_operational_storage):
    payload = {
        "decisions": [],
        "tasks": [],
        "issues": [{"text": "Mancano 12 pannelli", "source": "msg 1"}],
        "information": [],
        "open_questions": [],
    }
    mock_call = AsyncMock(return_value=json.dumps(payload))
    monkeypatch.setattr("core.operational_memory.extractor.llm_service._call_model", mock_call)

    await ingest_event(OperationalEvent(
        event_id="evt-img",
        project_id="site-001",
        sender="Sara",
        type="image",
        content="",
        attachment_metadata={
            "file_name": "materiale.jpg",
            "simulated_ocr": "Mancano 12 pannelli",
        },
    ))

    result = await process_pending_events("site-001")
    state = await get_project_state("site-001")

    assert result["processed"] == 1
    assert len(state.issues) == 1
    assert "Mancano 12 pannelli" in mock_call.await_args.args[2]
