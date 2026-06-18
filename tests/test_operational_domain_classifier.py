import pytest
from unittest.mock import AsyncMock

from core.operational_memory.daily_report import build_daily_report
from core.operational_memory.domain_classifier import classify_domain, classify_domains
from core.operational_memory.models import OperationalEvent
from core.operational_memory.state_engine import get_project_state
from core.operational_memory.watcher_engine import ingest_events_batch, process_pending_events


@pytest.fixture()
def isolated_operational_storage(monkeypatch, tmp_path):
    monkeypatch.setattr("core.operational_memory.event_store._BASE_DIR", tmp_path / "events")
    monkeypatch.setattr("core.operational_memory.state_store._BASE_DIR", tmp_path / "state")
    monkeypatch.setattr("core.operational_memory.snapshot_store._BASE_DIR", tmp_path / "snapshots")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("T7 M2 non parte", "TECHNICAL_ISSUE"),
        ("Arrivo a Termini alle 12:25", "LOGISTICS"),
        ("Sono bloccato con la schiena", "PERSONNEL"),
        ("Andiamo al mare", "SOCIAL"),
        ("Manca potenziometro", "TECHNICAL_ISSUE"),
        ("Domani iniziamo SS01", "TASK_ASSIGNMENT"),
    ],
)
def test_classify_domain_examples(text, expected):
    assert classify_domain(text) == expected


def test_media_event_gets_media_evidence_secondary_domain():
    domains = classify_domains("Foto quadro T7 non alimentata", event_type="image")

    assert "MEDIA_EVIDENCE" in domains
    assert "TECHNICAL_ISSUE" in domains


@pytest.mark.asyncio
async def test_non_operative_domains_are_filtered_before_extraction(monkeypatch, isolated_operational_storage):
    async def fake_call(_model, _prompt, _message, **_kwargs):
        return '{"decisions":[],"tasks":[],"issues":[{"text":"T7 M2 non parte","source":"msg 1"}],"information":[],"open_questions":[]}'

    monkeypatch.setattr("core.operational_memory.extractor.llm_service._call_model", AsyncMock(side_effect=fake_call))
    events = [
        OperationalEvent(
            event_id="evt-logistics",
            project_id="domain-demo",
            sender="Marco",
            content="Arrivo a Termini alle 12:25",
        ),
        OperationalEvent(
            event_id="evt-social",
            project_id="domain-demo",
            sender="Sara",
            content="Andiamo al mare",
        ),
        OperationalEvent(
            event_id="evt-technical",
            project_id="domain-demo",
            sender="Luca",
            content="T7 M2 non parte",
        ),
    ]

    await ingest_events_batch("domain-demo", events)
    await process_pending_events("domain-demo")
    state = await get_project_state("domain-demo")
    report = await build_daily_report("domain-demo")

    assert state.domain_stats["logistics_events"] == 1
    assert state.domain_stats["social_events"] == 1
    assert state.domain_stats["technical_events"] == 1
    assert any("Eventi social esclusi: 1" in item for item in report.conversational_noise_filtered)
    assert any("Eventi logistici esclusi: 1" in item for item in report.conversational_noise_filtered)
