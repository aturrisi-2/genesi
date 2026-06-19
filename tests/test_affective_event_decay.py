from datetime import datetime, timedelta, timezone

import pytest

from core.affective_event_decay import (
    ACUTE_SUPPORT,
    BACKGROUND_MEMORY,
    GENTLE_AWARENESS,
    INACTIVE_UNLESS_REFERENCED,
    affective_decay_stage,
    classify_affective_event,
    current_message_reactivates,
)
from core.context_assembler import ContextAssembler
from core.group_reactivity import detect_group_emotional_tone


NOW = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)


def ts_days_ago(days: int) -> int:
    return int((NOW - timedelta(days=days)).timestamp())


def test_recent_sensitive_event_is_acute_support():
    event = classify_affective_event(
        "Una persona del gruppo ha avuto un incidente serio.",
        NOW - timedelta(days=1),
        now=NOW,
    )

    assert event["stage"] == ACUTE_SUPPORT
    assert event["active_support"] is True


def test_week_old_sensitive_event_is_gentle_awareness_not_acutely_dominant():
    event = classify_affective_event(
        "Un familiare ha vissuto una perdita importante.",
        NOW - timedelta(days=7),
        now=NOW,
    )

    assert event["stage"] == GENTLE_AWARENESS
    assert event["active_support"] is True


def test_old_sensitive_event_becomes_background_memory():
    event = classify_affective_event(
        "Nel gruppo era emersa una malattia delicata.",
        NOW - timedelta(days=20),
        now=NOW,
    )

    assert event["stage"] == BACKGROUND_MEMORY
    assert event["active_support"] is False


def test_very_old_sensitive_event_is_inactive_unless_referenced():
    assert affective_decay_stage(NOW - timedelta(days=60), now=NOW) == INACTIVE_UNLESS_REFERENCED


def test_direct_reference_reactivates_sensitive_event_temporarily():
    event = classify_affective_event(
        "Una persona aveva avuto una crisi familiare.",
        NOW - timedelta(days=60),
        current_message="Oggi quella crisi mi pesa di nuovo.",
        now=NOW,
    )

    assert event["stage"] == ACUTE_SUPPORT
    assert event["reactivated"] is True


def test_generic_message_does_not_reactivate_sensitive_event():
    event = classify_affective_event(
        "Una persona aveva avuto una crisi familiare.",
        NOW - timedelta(days=60),
        current_message="Buongiorno, ci vediamo in ufficio.",
        now=NOW,
    )

    assert current_message_reactivates("Buongiorno, ci vediamo in ufficio.") is False
    assert event["stage"] == INACTIVE_UNLESS_REFERENCED
    assert event["active_support"] is False


def test_unrelated_sensitive_keyword_does_not_reactivate_historical_event():
    event = classify_affective_event(
        "Una persona ha avuto un incidente serio.",
        NOW - timedelta(days=60),
        current_message="Oggi ho un po' di ansia per una riunione.",
        now=NOW,
    )

    assert event["stage"] == INACTIVE_UNLESS_REFERENCED
    assert event["reactivated"] is False


def test_group_tone_decays_for_old_delicate_messages():
    tone = detect_group_emotional_tone(
        [
            {"first_name": "PersonaA", "text": "Abbiamo avuto una perdita dolorosa.", "ts": ts_days_ago(20)},
            {"first_name": "PersonaB", "text": "Buongiorno a tutti.", "ts": ts_days_ago(0)},
        ]
    )

    assert tone["tone"] == "normal"
    assert tone["stage"] == BACKGROUND_MEMORY
    assert tone["prompt_block"] == ""


def test_group_tone_uses_gentle_awareness_after_about_a_week():
    tone = detect_group_emotional_tone(
        [
            {"first_name": "PersonaA", "text": "Abbiamo avuto un lutto in famiglia.", "ts": ts_days_ago(7)},
            {"first_name": "PersonaB", "text": "Ci aggiorniamo per il progetto.", "ts": ts_days_ago(0)},
        ]
    )

    assert tone["tone"] == "grief"
    assert tone["stage"] == GENTLE_AWARENESS
    assert "non usare tono condolente" in tone["prompt_block"]


def test_group_tone_recent_event_is_platform_and_profession_agnostic():
    tone = detect_group_emotional_tone(
        [
            {"first_name": "PersonaA", "text": "C'e stato un incidente, giornata pesante.", "ts": ts_days_ago(1)},
            {"first_name": "PersonaB", "text": "Messaggio da una chat qualunque.", "ts": ts_days_ago(0)},
        ]
    )

    assert tone["tone"] == "grief"
    assert tone["stage"] == ACUTE_SUPPORT
    assert "EVENTO DELICATO RECENTE" in tone["prompt_block"]


class _DummyLatentState:
    async def load(self, user_id):
        return {}


@pytest.mark.asyncio
async def test_context_assembler_keeps_old_delicate_fact_out_of_active_prompt(monkeypatch):
    from core.personal_facts_service import personal_facts_service

    old_fact = {
        "text": "Una persona vicina ha avuto una crisi familiare.",
        "saved_at": (NOW - timedelta(days=60)).isoformat(),
    }

    async def _get_relevant(user_id, user_message, limit=8):
        return [old_fact]

    async def _get_all(user_id):
        return [old_fact]

    monkeypatch.setattr(personal_facts_service, "get_relevant", _get_relevant)
    monkeypatch.setattr(personal_facts_service, "get_all", _get_all)

    context = await ContextAssembler(None, _DummyLatentState()).build(
        "affective-neutral-user",
        "Aggiorniamo la scaletta del progetto.",
        platform="widget",
    )

    summary = context["summary"]
    assert "Una persona vicina ha avuto una crisi familiare" not in summary
    assert "[FATTI PERSONALI APPRESI]" not in summary
    assert "[MEMORIE AFFETTIVE DI BACKGROUND]" not in summary
    assert context["affective_background"][0]["text"] == old_fact["text"]


@pytest.mark.asyncio
async def test_context_assembler_reactivates_old_delicate_fact_when_context_matches(monkeypatch):
    from core.personal_facts_service import personal_facts_service

    old_fact = {
        "text": "Una persona vicina ha avuto una crisi familiare.",
        "saved_at": (NOW - timedelta(days=60)).isoformat(),
    }

    async def _get_relevant(user_id, user_message, limit=8):
        return [old_fact]

    async def _get_all(user_id):
        return [old_fact]

    monkeypatch.setattr(personal_facts_service, "get_relevant", _get_relevant)
    monkeypatch.setattr(personal_facts_service, "get_all", _get_all)

    context = await ContextAssembler(None, _DummyLatentState()).build(
        "affective-reactivated-user",
        "Quella crisi familiare mi pesa di nuovo oggi.",
        platform="widget",
    )

    summary = context["summary"]
    assert "Una persona vicina ha avuto una crisi familiare" in summary
    assert "[FATTI PERSONALI APPRESI]" in summary
    assert "usa con prudenza" in summary
