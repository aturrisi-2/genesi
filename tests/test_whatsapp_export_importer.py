import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from api.operational import WhatsAppExportImportRequest, import_whatsapp_export_endpoint
from core.operational_memory.daily_report import build_daily_report
from core.operational_memory.event_store import list_events
from core.operational_memory.importers.whatsapp_export import parse_whatsapp_export
from core.operational_memory.state_engine import get_project_state
from core.operational_memory.watcher_engine import process_pending_events


FIXTURE_PATH = Path("tests/fixtures/whatsapp_export_sample.txt")


@pytest.fixture()
def isolated_operational_storage(monkeypatch, tmp_path):
    monkeypatch.setattr("core.operational_memory.event_store._BASE_DIR", tmp_path / "events")
    monkeypatch.setattr("core.operational_memory.state_store._BASE_DIR", tmp_path / "state")
    monkeypatch.setattr("core.operational_memory.snapshot_store._BASE_DIR", tmp_path / "snapshots")


def _fixture_text() -> str:
    return FIXTURE_PATH.read_text(encoding="utf-8")


def _payload_for_message(message: str) -> dict:
    if "posa cartongesso" in message:
        return {
            "decisions": [],
            "tasks": [{"text": "Verificare il materiale", "owner": "Luca", "due": "entro le 10", "status": "open", "source": "msg 1"}],
            "issues": [],
            "information": [{"text": "Inizia posa cartongesso al piano 2", "source": "msg 1"}],
            "open_questions": [],
        }
    if "Allegato WhatsApp" in message and "ordine_profili.pdf" in message:
        return {
            "decisions": [],
            "tasks": [{"text": "Verificare ordine profili", "owner": "Sara", "due": None, "status": "open", "source": "msg 1"}],
            "issues": [],
            "information": [{"text": "Ricevuto PDF ordine profili", "source": "msg 1"}],
            "open_questions": [],
        }
    if "Allegato WhatsApp" in message:
        return {
            "decisions": [],
            "tasks": [],
            "issues": [{"text": "Verificare contenuto media omesso", "source": "msg 1"}],
            "information": [],
            "open_questions": [],
        }
    if "mancano 12 profili metallici" in message:
        return {
            "decisions": [],
            "tasks": [],
            "issues": [{"text": "Mancano 12 profili metallici", "source": "msg 1"}],
            "information": [],
            "open_questions": [],
        }
    if "spostiamo la posa del vano scala" in message:
        return {
            "decisions": [{"text": "La posa del vano scala e' spostata a venerdi mattina", "source": "msg 1"}],
            "tasks": [],
            "issues": [],
            "information": [],
            "open_questions": [],
        }
    if "Gianni chiude stuccatura" in message:
        return {
            "decisions": [],
            "tasks": [{"text": "Chiudere stuccatura", "owner": "Gianni", "due": "oggi", "status": "open", "source": "msg 1"}],
            "issues": [],
            "information": [{"text": "Pareti uffici completate al 60%", "source": "msg 1"}],
            "open_questions": [],
        }
    if "Stuccatura pareti uffici completata" in message:
        return {
            "decisions": [],
            "tasks": [{"text": "Chiudere stuccatura", "owner": "Gianni", "due": "oggi", "status": "completed", "source": "msg 1"}],
            "issues": [],
            "information": [],
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


def test_parser_recognizes_valid_whatsapp_lines():
    result = parse_whatsapp_export(_fixture_text(), "site-wa", "gruppo-cantiere-demo")

    assert len(result.events) == 8
    assert result.events[0].sender == "Marco"
    assert result.events[0].timestamp.startswith("2026-06-18T07:42:13")
    assert result.events[0].event_id.startswith("wa_")


def test_parser_merges_multiline_messages():
    result = parse_whatsapp_export(_fixture_text(), "site-wa", "gruppo-cantiere-demo")

    first = result.events[0]
    report = next(event for event in result.events if event.sender == "Marco" and "Report avanzamento" in event.content)
    assert "Luca verifica il materiale entro le 10." in first.content
    assert "pareti uffici completate al 60%." in report.content
    assert "Gianni chiude stuccatura entro oggi." in report.content


def test_parser_ignores_system_messages():
    result = parse_whatsapp_export(_fixture_text(), "site-wa", "gruppo-cantiere-demo")

    assert result.ignored == 2
    assert all("ha aggiunto" not in event.content for event in result.events)


def test_parser_maps_media_omitted_to_simulated_attachment_events():
    result = parse_whatsapp_export(_fixture_text(), "site-wa", "gruppo-cantiere-demo")

    media = [event for event in result.events if event.type != "text"]
    assert {event.type for event in media} == {"image", "pdf"}
    assert media[0].attachment_metadata["description"].startswith("Allegato WhatsApp")


@pytest.mark.asyncio
async def test_import_endpoint_creates_pending_events(isolated_operational_storage):
    response = await import_whatsapp_export_endpoint(
        "site-wa",
        WhatsAppExportImportRequest(
            raw_text=_fixture_text(),
            source_name="gruppo-cantiere-demo",
            timezone="Europe/Rome",
        ),
    )
    events = await list_events("site-wa")

    assert response.parsed == 8
    assert response.accepted == 8
    assert response.duplicates == 0
    assert response.ignored == 2
    assert all(event.processed_status == "pending" for event in events)


@pytest.mark.asyncio
async def test_duplicate_import_does_not_duplicate_events(isolated_operational_storage):
    request = WhatsAppExportImportRequest(raw_text=_fixture_text(), source_name="gruppo-cantiere-demo")

    first = await import_whatsapp_export_endpoint("site-wa", request)
    second = await import_whatsapp_export_endpoint("site-wa", request)
    events = await list_events("site-wa")

    assert first.accepted == 8
    assert second.accepted == 0
    assert second.duplicates == 8
    assert len(events) == 8


@pytest.mark.asyncio
async def test_processing_after_import_updates_operational_state(monkeypatch, isolated_operational_storage):
    _mock_extractor(monkeypatch)
    await import_whatsapp_export_endpoint("site-wa", WhatsAppExportImportRequest(raw_text=_fixture_text()))

    result = await process_pending_events("site-wa")
    state = await get_project_state("site-wa")

    assert result["processed"] == 8
    assert len(state.decisions) == 1
    assert len(state.tasks) >= 3
    assert len(state.issues) >= 2
    assert len(state.information) >= 3
    assert len(state.open_questions) == 1


@pytest.mark.asyncio
async def test_daily_report_after_whatsapp_import_has_useful_sections(monkeypatch, isolated_operational_storage):
    _mock_extractor(monkeypatch)
    await import_whatsapp_export_endpoint("site-wa", WhatsAppExportImportRequest(raw_text=_fixture_text()))
    await process_pending_events("site-wa")

    report = await build_daily_report("site-wa")

    assert report.decisions
    assert report.tasks_open
    assert report.tasks_completed
    assert report.issues_open
    assert report.open_questions
    assert "## Decisioni" in report.markdown
    assert "## Domande aperte" in report.markdown
