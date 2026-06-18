import json
from unittest.mock import AsyncMock

import pytest

from core.operational_memory.daily_report import build_daily_report
from core.operational_memory.extractor import extract_state
from core.operational_memory.state_engine import ingest_messages


@pytest.fixture()
def isolated_operational_storage(monkeypatch, tmp_path):
    monkeypatch.setattr("core.operational_memory.state_store._BASE_DIR", tmp_path / "state")
    monkeypatch.setattr("core.operational_memory.event_store._BASE_DIR", tmp_path / "events")


@pytest.mark.asyncio
async def test_isolated_si_does_not_become_decision(monkeypatch):
    payload = {
        "decisions": [{"text": "Si", "source": "msg 1", "confidence": "high"}],
        "tasks": [],
        "issues": [],
        "information": [],
        "open_questions": [],
    }
    monkeypatch.setattr(
        "core.operational_memory.extractor.llm_service._call_model",
        AsyncMock(return_value=json.dumps(payload)),
    )

    state = await extract_state(["Si"])

    assert state.decisions == []


@pytest.mark.asyncio
async def test_media_placeholders_are_ignored_before_llm(monkeypatch):
    mock = AsyncMock(return_value=json.dumps({"decisions": [], "tasks": [], "issues": [], "information": [], "open_questions": []}))
    monkeypatch.setattr("core.operational_memory.extractor.llm_service._call_model", mock)

    state = await extract_state(["Sticker non incluso", "Immagine omessa", "Video omesso", "audio omesso"])

    assert state.decisions == []
    assert state.tasks == []
    assert state.issues == []
    assert state.information == []
    assert state.open_questions == []
    mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_media_placeholder_is_ignored_in_report(monkeypatch, isolated_operational_storage):
    payload = {
        "decisions": [],
        "tasks": [],
        "issues": [{"text": "Immagine omessa", "source": "msg 1", "confidence": "high"}],
        "information": [{"text": "Sticker non incluso", "source": "msg 1", "confidence": "high"}],
        "open_questions": [],
    }
    monkeypatch.setattr(
        "core.operational_memory.extractor.llm_service._call_model",
        AsyncMock(return_value=json.dumps(payload)),
    )

    await ingest_messages("quality-demo", ["Verificare allegato"])
    report = await build_daily_report("quality-demo")

    assert "Immagine omessa" not in report.markdown
    assert "Sticker non incluso" not in report.markdown
    assert report.issues_open == []
    assert report.information == []


@pytest.mark.asyncio
async def test_realistic_technical_examples_are_extracted(monkeypatch):
    payload = {
        "decisions": [],
        "tasks": [{"text": "Sostituire servomotore", "owner": None, "due": None, "status": "open", "source": "msg 2", "confidence": "high"}],
        "issues": [
            {"text": "Manca potenziometro", "source": "msg 1", "confidence": "high"},
            {"text": "T7 M2 non parte", "source": "msg 3", "confidence": "high"},
        ],
        "information": [],
        "open_questions": [],
    }
    monkeypatch.setattr(
        "core.operational_memory.extractor.llm_service._call_model",
        AsyncMock(return_value=json.dumps(payload)),
    )

    state = await extract_state(["Manca potenziometro", "Sostituire servomotore", "T7 M2 non parte"])

    assert [issue.text for issue in state.issues] == ["Manca potenziometro", "T7 M2 non parte"]
    assert [task.text for task in state.tasks] == ["Sostituire servomotore"]


@pytest.mark.asyncio
async def test_daily_report_excludes_low_confidence_and_limits_next_actions(monkeypatch, isolated_operational_storage):
    async def fake_call(_model, _prompt, _message, **_kwargs):
        return json.dumps(
            {
                "decisions": [{"text": "Va bene", "source": "msg 1", "confidence": "low"}],
                "tasks": [
                    {"text": f"Sostituire servomotore linea {idx}", "owner": None, "due": None, "status": "open", "source": f"msg {idx}", "confidence": "medium"}
                    for idx in range(12)
                ],
                "issues": [{"text": "Manca potenziometro", "source": "msg 20", "confidence": "medium"}],
                "information": [{"text": "Top top top", "source": "msg 21", "confidence": "high"}],
                "open_questions": [{"text": "T7 M2 non parte?", "source": "msg 22", "confidence": "medium"}],
            }
        )

    monkeypatch.setattr("core.operational_memory.extractor.llm_service._call_model", AsyncMock(side_effect=fake_call))

    await ingest_messages("quality-demo", ["batch tecnico"])
    report = await build_daily_report("quality-demo")

    assert report.decisions == []
    assert "Top top top" not in report.markdown
    assert "Manca potenziometro" in report.issues_open
    assert len(report.next_actions) == 10
