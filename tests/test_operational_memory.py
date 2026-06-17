import json
from unittest.mock import AsyncMock

import pytest

from core.operational_memory.extractor import extract_state


@pytest.mark.asyncio
async def test_extract_state_maps_llm_json(monkeypatch):
    payload = {
        "decisions": [{"text": "La consegna e' spostata a mercoledi", "source": "msg 2"}],
        "tasks": [{"text": "Verificare il materiale", "owner": "Marco", "due": None, "source": "msg 3"}],
        "issues": [{"text": "La fornitura e' incompleta", "source": "msg 1"}],
        "information": [{"text": "La consegna e' prevista venerdi", "source": "msg 4"}],
        "open_questions": [{"text": "Confermare l'orario di consegna", "source": "msg 5"}],
    }
    mock_call = AsyncMock(return_value=json.dumps(payload))
    monkeypatch.setattr("core.operational_memory.extractor.llm_service._call_model", mock_call)

    state = await extract_state([
        "La fornitura e' incompleta.",
        "Ok, spostiamo la consegna a mercoledi.",
        "Marco verifica il materiale.",
        "Consegna prevista venerdi.",
        "A che ora consegnano?",
    ])

    assert state.decisions[0].text == "La consegna e' spostata a mercoledi"
    assert state.tasks[0].owner == "Marco"
    assert state.issues[0].source == "msg 1"
    assert state.information[0].text == "La consegna e' prevista venerdi"
    assert state.open_questions[0].text == "Confermare l'orario di consegna"
    assert state.tasks[0].id.startswith("task_")
    mock_call.assert_awaited_once()


@pytest.mark.asyncio
async def test_extract_state_drops_items_without_source(monkeypatch):
    payload = {
        "decisions": [{"text": "Decisione senza fonte", "source": ""}],
        "tasks": [],
        "issues": [],
        "information": [],
        "open_questions": [],
    }
    monkeypatch.setattr(
        "core.operational_memory.extractor.llm_service._call_model",
        AsyncMock(return_value=json.dumps(payload)),
    )

    state = await extract_state(["Messaggio qualsiasi"])

    assert state.decisions == []
