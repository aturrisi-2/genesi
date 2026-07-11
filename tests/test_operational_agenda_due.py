"""Operational Memory — due/owner extraction contract + agenda view (Fase 1 TAB).

Audit Fase 0 (2026-07-11) sul gruppo TAB CEFLA: ingest solido ma `due` 2/19 e
`owner` 4/19 → lo stato non sostiene la pianificazione "impegni di oggi".
Questi test pinnano i tre interventi:

  1. `_normalize_due`: il campo "due" rispetta il contratto ISO — date relative
     italiane risolte in modo deterministico rispetto al timestamp del messaggio
     sorgente, testo libero mai propagato (→ None).
  2. Intent "agenda" nel query engine: le domande di pianificazione ricevono i
     task attivi ordinati per scadenza (senza data in coda); gli intent
     esistenti non vengono scavalcati.
  3. Marker `OPERATIONAL_MEDIA_INGESTED`: l'ingest dei media è osservabile
     esplicitamente (l'audit doveva dedurlo da type=image).

Tutti offline: funzioni pure + fixture sintetiche, nessun LLM/storage/rete.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

import pytest

from core.operational_memory.extractor import _normalize_due, _normalize_items
from core.operational_memory.models import (
    OperationalEvent,
    OperationalState,
    OperationalTask,
)
from core.operational_memory.query_engine import (
    agenda_tasks,
    answer_query,
    classify_query_intent,
)


REF = "2026-07-08T09:30:00"  # mercoledì


# --------------------------------------------------------------------------- #
# 1. _normalize_due — contratto ISO
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("value,expected", [
    ("2026-07-15", "2026-07-15"),
    ("2026-07-15T14:00", "2026-07-15T14:00"),
    ("2026-07-15 14:00:30", "2026-07-15T14:00"),
    (None, None),
    ("", None),
    ("null", None),
])
def test_normalize_due_iso_passthrough_and_empty(value, expected):
    assert _normalize_due(value, REF) == expected


@pytest.mark.parametrize("value,expected", [
    ("domani", "2026-07-09"),
    ("dopodomani", "2026-07-10"),
    ("oggi", "2026-07-08"),
    ("stasera", "2026-07-08"),
    ("domani alle 14", "2026-07-09T14:00"),
    ("domani alle 8:30", "2026-07-09T08:30"),
    ("entro venerdì", "2026-07-10"),   # venerdì successivo al mercoledì di rif.
    ("entro mercoledì", "2026-07-15"), # stesso giorno → occorrenza successiva
    ("lunedì", "2026-07-13"),
    ("15/07", "2026-07-15"),
    ("15/07/2026", "2026-07-15"),
])
def test_normalize_due_relative_italian(value, expected):
    assert _normalize_due(value, REF) == expected


@pytest.mark.parametrize("value", [
    "appena possibile", "quando si può", "prossimamente", "boh",
])
def test_normalize_due_unresolvable_becomes_none(value):
    assert _normalize_due(value, REF) is None


def test_normalize_due_bad_reference_does_not_crash():
    out = _normalize_due("domani", "non-una-data")
    assert out is None or len(out) >= 10  # fallback su now(): comunque ISO


# --------------------------------------------------------------------------- #
# 2. _normalize_items applica il contratto ai task estratti
# --------------------------------------------------------------------------- #

def test_normalize_items_normalizes_task_due_and_owner():
    raw = [{"text": "Verificare il quadro elettrico", "source": "msg 2",
            "confidence": "high", "due": "domani alle 9", "owner": "  Marco "}]
    meta = {"source_timestamp": REF}
    items = _normalize_items(raw, OperationalTask, "task", meta)
    assert len(items) == 1
    assert items[0].due == "2026-07-09T09:00"
    assert items[0].owner == "Marco"


def test_normalize_items_free_text_due_never_propagates():
    raw = [{"text": "Ordinare i materiali", "source": "msg 3",
            "confidence": "high", "due": "appena arriva il furgone", "owner": ""}]
    items = _normalize_items(raw, OperationalTask, "task", {"source_timestamp": REF})
    assert items[0].due is None
    assert items[0].owner is None


# --------------------------------------------------------------------------- #
# 3. Intent "agenda" + ordinamento per scadenza
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("q", [
    "impegni di oggi?",
    "che agenda abbiamo?",
    "cosa dobbiamo fare domani?",
    "programma della settimana",
    "cosa c'è in programma oggi?",
])
def test_agenda_intent_classification(q):
    assert classify_query_intent(q) == "agenda"


@pytest.mark.parametrize("q,expected", [
    ("cosa manca?", "open_tasks"),
    ("fammi il punto", "briefing"),
    ("problemi aperti?", "open_issues"),
    ("cosa resta aperto?", "remaining_open"),
    ("mi impegno a farlo io", "unknown"),  # "impegno" singolare ≠ agenda
])
def test_existing_intents_not_hijacked(q, expected):
    assert classify_query_intent(q) == expected


def _state_with_tasks() -> OperationalState:
    st = OperationalState(project_id="agenda-test-proj")
    st.tasks.extend([
        OperationalTask(text="Task senza scadenza", source="m1",
                        source_event_id="m1"),
        OperationalTask(text="Consegna certificazioni", source="m2",
                        source_event_id="m2", due="2026-07-12", owner="Anna"),
        OperationalTask(text="Verifica quadro elettrico", source="m3",
                        source_event_id="m3", due="2026-07-09T08:00",
                        owner="Marco"),
    ])
    return st


def test_agenda_tasks_ordered_by_due_with_undated_last():
    ordered = agenda_tasks(_state_with_tasks())
    assert [it.due for it in ordered] == ["2026-07-09T08:00", "2026-07-12", None]
    assert ordered[0].owner == "Marco"


def test_answer_query_agenda_end_to_end():
    result = answer_query(_state_with_tasks(), "impegni di oggi?")
    assert result.intent == "agenda"
    assert "scadenza" in result.summary
    assert [it.due for it in result.items] == ["2026-07-09T08:00", "2026-07-12", None]


# --------------------------------------------------------------------------- #
# 4. Marker media esplicito
# --------------------------------------------------------------------------- #

def test_media_ingest_emits_explicit_marker(monkeypatch):
    from core.operational_memory import watcher_engine as we

    calls: list[tuple] = []
    monkeypatch.setattr(we, "log", lambda marker, **kw: calls.append((marker, kw)))

    async def _fake_append(event):
        return event, True
    monkeypatch.setattr(we, "append_event", _fake_append)
    monkeypatch.setattr(we, "normalize_event", lambda e: e)

    img = OperationalEvent(event_id="ev_img_1", project_id="agenda-test-proj",
                           type="image", text="foto quadro", sender="Anna",
                           timestamp=REF)
    txt = OperationalEvent(event_id="ev_txt_1", project_id="agenda-test-proj",
                           type="text", text="ok fatto", sender="Anna",
                           timestamp=REF)
    asyncio.run(we.ingest_event(img))
    asyncio.run(we.ingest_event(txt))

    media_markers = [kw for m, kw in calls if m == "OPERATIONAL_MEDIA_INGESTED"]
    assert len(media_markers) == 1
    assert media_markers[0]["media_type"] == "image"
    assert media_markers[0]["event_id"] == "ev_img_1"
