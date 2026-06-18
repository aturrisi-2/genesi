import json
from unittest.mock import AsyncMock

import pytest

from core.operational_memory.daily_report import build_daily_report
from core.operational_memory.context_extractor import extract_context
from core.operational_memory.extractor import extract_state
from core.operational_memory.state_engine import ingest_messages


@pytest.fixture()
def isolated_operational_storage(monkeypatch, tmp_path):
    monkeypatch.setattr("core.operational_memory.state_store._BASE_DIR", tmp_path / "state")
    monkeypatch.setattr("core.operational_memory.event_store._BASE_DIR", tmp_path / "events")


def test_context_extractor_recognizes_els07_copertura_t2():
    context = extract_context("Manca potenziometro per ELS07 COPERTURA T2")

    assert context.context_system == "ELS07"
    assert context.context_location == "COPERTURA T2"
    assert "potenziometro" in [tag.lower() for tag in context.context_tags]


def test_context_extractor_recognizes_stf_b1_v10_t7_mandata():
    context = extract_context("STF B1 V10 Mandata T7 non alimentata")

    assert context.context_area == "STF"
    assert context.context_system == "T7"
    assert context.context_location == "B1 V10"
    assert "Mandata" in context.context_tags


def test_context_extractor_recognizes_ewc05_and_l4():
    context = extract_context("EWC05 manca collegamento montante da L4 in su")

    assert context.context_system == "EWC05"
    assert context.context_level == "L4"
    assert "montante" in [tag.lower() for tag in context.context_tags]


def test_context_extractor_recognizes_porta_034_as_location():
    context = extract_context("Verificare porta 034")

    assert context.context_location == "porta 034"


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
    assert any("Manca potenziometro" in item for item in report.issues_open)
    assert len(report.next_actions) == 10


@pytest.mark.asyncio
async def test_ambiguous_item_without_context_goes_to_verify(monkeypatch, isolated_operational_storage):
    payload = {
        "decisions": [],
        "tasks": [],
        "issues": [{"text": "Da controllare", "source": "msg 1", "confidence": "medium"}],
        "information": [],
        "open_questions": [],
    }
    monkeypatch.setattr(
        "core.operational_memory.extractor.llm_service._call_model",
        AsyncMock(return_value=json.dumps(payload)),
    )

    await ingest_messages("quality-demo", ["Da controllare"])
    report = await build_daily_report("quality-demo")

    assert report.issues_open == []
    assert report.items_to_verify
