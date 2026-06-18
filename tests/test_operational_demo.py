import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from core.operational_memory.daily_report import build_daily_report
from core.operational_memory.event_store import list_events
from core.operational_memory.models import OperationalEvent
from core.operational_memory.snapshot_store import create_snapshot, list_snapshots
from core.operational_memory.state_engine import get_project_state
from core.operational_memory.watcher_engine import ingest_events_batch, process_pending_events


FIXTURE_PATH = Path("tests/fixtures/cantiere_day_events.json")


@pytest.fixture()
def isolated_operational_storage(monkeypatch, tmp_path):
    monkeypatch.setattr("core.operational_memory.event_store._BASE_DIR", tmp_path / "events")
    monkeypatch.setattr("core.operational_memory.state_store._BASE_DIR", tmp_path / "state")
    monkeypatch.setattr("core.operational_memory.snapshot_store._BASE_DIR", tmp_path / "snapshots")


def _load_demo_events() -> list[OperationalEvent]:
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    return [OperationalEvent(**item) for item in data]


def _payload_for_message(message: str) -> dict:
    if "posa cartongesso" in message:
        return {
            "decisions": [],
            "tasks": [{"text": "Verificare il materiale", "owner": "Luca", "due": "entro le 10", "status": "open", "source": "msg 1"}],
            "issues": [],
            "information": [{"text": "Oggi inizia la posa cartongesso al piano 2", "source": "msg 1"}],
            "open_questions": [],
        }
    if "Mancano 12 profili metallici" in message or "mancano 12 profili metallici" in message:
        return {
            "decisions": [],
            "tasks": [],
            "issues": [{"text": "Mancano 12 profili metallici", "source": "msg 1"}],
            "information": [{"text": "Consegnati 42 pannelli cartongesso", "source": "msg 1"}],
            "open_questions": [],
        }
    if "spostiamo la posa del vano scala" in message:
        return {
            "decisions": [{"text": "La posa del vano scala e' spostata a venerdi mattina", "source": "msg 1"}],
            "tasks": [{"text": "Completare le pareti uffici", "owner": None, "due": "oggi", "status": "open", "source": "msg 1"}],
            "issues": [],
            "information": [],
            "open_questions": [],
        }
    if "Ordine integrativo" in message:
        return {
            "decisions": [],
            "tasks": [{"text": "Ritirare 12 profili metallici", "owner": "Luca", "due": "venerdi ore 8:30", "status": "open", "source": "msg 1"}],
            "issues": [],
            "information": [{"text": "Consegna profili prevista venerdi ore 8:30", "source": "msg 1"}],
            "open_questions": [],
        }
    if "Gianni chiude stuccatura" in message:
        return {
            "decisions": [],
            "tasks": [{"text": "Chiudere stuccatura pareti uffici", "owner": "Gianni", "due": "oggi", "status": "open", "source": "msg 1"}],
            "issues": [{"text": "Vano scala fermo per profili mancanti", "source": "msg 1"}],
            "information": [{"text": "Pareti uffici completate al 60%", "source": "msg 1"}],
            "open_questions": [],
        }
    if "Stuccatura pareti uffici completata" in message:
        return {
            "decisions": [],
            "tasks": [{"text": "Chiudere stuccatura pareti uffici", "owner": "Gianni", "due": "oggi", "status": "completed", "source": "msg 1"}],
            "issues": [],
            "information": [],
            "open_questions": [],
        }
    if "Screenshot cronoprogramma" in message:
        return {
            "decisions": [],
            "tasks": [{"text": "Verificare materiale", "owner": None, "due": "venerdi ore 8:30", "status": "open", "source": "msg 1"}],
            "issues": [],
            "information": [{"text": "Cronoprogramma aggiornato: vano scala venerdi", "source": "msg 1"}],
            "open_questions": [],
        }
    if "Chi conferma domani mattina" in message:
        return {
            "decisions": [],
            "tasks": [],
            "issues": [],
            "information": [],
            "open_questions": [{"text": "Chi conferma domani mattina la ricezione dei profili?", "source": "msg 1"}],
        }
    return {"decisions": [], "tasks": [], "issues": [], "information": [], "open_questions": []}


def _mock_extractor(monkeypatch):
    async def fake_call(_model, _prompt, message, **_kwargs):
        return json.dumps(_payload_for_message(message))

    mock = AsyncMock(side_effect=fake_call)
    monkeypatch.setattr("core.operational_memory.extractor.llm_service._call_model", mock)
    return mock


@pytest.mark.asyncio
async def test_batch_ingest_accepts_multiple_events(isolated_operational_storage):
    events = _load_demo_events()

    result = await ingest_events_batch("cantiere-demo", events)
    stored = await list_events("cantiere-demo")

    assert result == {"accepted": len(events), "duplicates": 0, "failed": 0}
    assert len(stored) == len(events)


@pytest.mark.asyncio
async def test_batch_ingest_handles_duplicates(isolated_operational_storage):
    events = _load_demo_events()
    duplicate = events[0]

    first = await ingest_events_batch("cantiere-demo", events)
    second = await ingest_events_batch("cantiere-demo", [duplicate])

    assert first["accepted"] == len(events)
    assert second == {"accepted": 0, "duplicates": 1, "failed": 0}


@pytest.mark.asyncio
async def test_process_pending_updates_persistent_state(monkeypatch, isolated_operational_storage):
    _mock_extractor(monkeypatch)
    await ingest_events_batch("cantiere-demo", _load_demo_events())

    result = await process_pending_events("cantiere-demo")
    state = await get_project_state("cantiere-demo")

    assert result["processed"] == 9
    assert len(state.decisions) >= 1
    assert len(state.tasks) >= 4
    assert len(state.issues) >= 2
    assert len(state.information) >= 4
    assert len(state.open_questions) == 1


@pytest.mark.asyncio
async def test_snapshot_is_created(monkeypatch, isolated_operational_storage):
    _mock_extractor(monkeypatch)
    await ingest_events_batch("cantiere-demo", _load_demo_events())
    await process_pending_events("cantiere-demo")

    snapshot = await create_snapshot("cantiere-demo")
    snapshots = await list_snapshots("cantiere-demo")

    assert snapshot.project_id == "cantiere-demo"
    assert snapshot.counts["tasks"] >= 4
    assert snapshot.source_event_count == 9
    assert len(snapshots) == 1


@pytest.mark.asyncio
async def test_daily_report_contains_required_sections(monkeypatch, isolated_operational_storage):
    _mock_extractor(monkeypatch)
    await ingest_events_batch("cantiere-demo", _load_demo_events())
    await process_pending_events("cantiere-demo")

    report = await build_daily_report("cantiere-demo")

    assert report.title == "Aggiornamento giornaliero - cantiere-demo"
    assert report.decisions
    assert report.tasks_open
    assert report.tasks_completed
    assert report.issues_open
    assert report.information
    assert report.open_questions
    assert "## Decisioni" in report.markdown
    assert "## Task aperti" in report.markdown
    assert "## Task completati" in report.markdown
    assert "## Prossime azioni suggerite" in report.markdown


@pytest.mark.asyncio
async def test_simulated_image_pdf_document_events_are_processed(monkeypatch, isolated_operational_storage):
    mock = _mock_extractor(monkeypatch)
    events = [event for event in _load_demo_events() if event.type in {"image", "pdf", "document"}]
    await ingest_events_batch("cantiere-demo", events)

    result = await process_pending_events("cantiere-demo")

    joined_messages = "\n".join(call.args[2] for call in mock.await_args_list)
    assert result["processed"] == len(events)
    assert "DDT 184" in joined_messages
    assert "Ordine integrativo" in joined_messages
    assert "Pareti uffici completate al 60%" in joined_messages
    assert "Screenshot cronoprogramma" in joined_messages
