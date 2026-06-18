import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from api.operational import run_offline_whatsapp_demo_endpoint
from core.operational_memory.demo_runner import (
    OfflineWhatsAppDemoRequest,
    run_whatsapp_export_demo,
)
from core.operational_memory.snapshot_store import list_snapshots


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


@pytest.mark.asyncio
async def test_demo_run_imports_fixture_and_processes_pending(monkeypatch, isolated_operational_storage):
    _mock_extractor(monkeypatch)

    response = await run_whatsapp_export_demo(
        "site-demo",
        OfflineWhatsAppDemoRequest(raw_text=_fixture_text(), source_name="gruppo-cantiere-reale-anonimizzato"),
    )

    assert response.import_summary.parsed == 8
    assert response.import_summary.accepted == 8
    assert response.processing.processed == 8
    assert response.processing.pending_after == 0
    assert response.state_counts.decisions == 1
    assert response.state_counts.open_tasks >= 2


@pytest.mark.asyncio
async def test_demo_run_creates_snapshot(monkeypatch, isolated_operational_storage):
    _mock_extractor(monkeypatch)

    response = await run_whatsapp_export_demo(
        "site-demo",
        OfflineWhatsAppDemoRequest(raw_text=_fixture_text(), create_snapshot=True),
    )
    snapshots = await list_snapshots("site-demo")

    assert response.snapshot.created is True
    assert response.snapshot.snapshot_id
    assert len(snapshots) == 1


@pytest.mark.asyncio
async def test_demo_run_generates_markdown_report(monkeypatch, isolated_operational_storage):
    _mock_extractor(monkeypatch)

    response = await run_whatsapp_export_demo(
        "site-demo",
        OfflineWhatsAppDemoRequest(raw_text=_fixture_text(), report_format="markdown"),
    )

    assert "## Decisioni" in response.daily_report_markdown
    assert "## Task aperti" in response.daily_report_markdown
    assert "## Task completati" in response.daily_report_markdown
    assert response.daily_report_json is None


@pytest.mark.asyncio
async def test_demo_run_json_report_format_includes_report_json(monkeypatch, isolated_operational_storage):
    _mock_extractor(monkeypatch)

    response = await run_whatsapp_export_demo(
        "site-demo",
        OfflineWhatsAppDemoRequest(raw_text=_fixture_text(), report_format="json"),
    )

    assert response.daily_report_json is not None
    assert response.daily_report_json.decisions


@pytest.mark.asyncio
async def test_demo_run_second_launch_reports_duplicates(monkeypatch, isolated_operational_storage):
    _mock_extractor(monkeypatch)
    request = OfflineWhatsAppDemoRequest(raw_text=_fixture_text())

    first = await run_whatsapp_export_demo("site-demo", request)
    second = await run_whatsapp_export_demo("site-demo", request)

    assert first.import_summary.accepted == 8
    assert second.import_summary.accepted == 0
    assert second.import_summary.duplicates == 8
    assert second.processing.processed == 0


@pytest.mark.asyncio
async def test_demo_endpoint_empty_raw_text_returns_controlled_error(isolated_operational_storage):
    with pytest.raises(HTTPException) as exc:
        await run_offline_whatsapp_demo_endpoint(
            "site-demo",
            OfflineWhatsAppDemoRequest(raw_text="   "),
        )

    assert exc.value.status_code == 400
    assert "raw_text" in exc.value.detail
