from __future__ import annotations

import pytest

from core.operational_memory.models import (
    Decision,
    Information,
    Issue,
    LifecycleHistoryEntry,
    LifecycleState,
    OperationalEvent,
    OperationalQuestion,
    OperationalState,
    OperationalTask,
)
from core.operational_memory.refinement_report import build_refinement_report


def _lc(category, status, confidence="medium"):
    return LifecycleState(
        category=category, current_status=status, confidence=confidence, status_reason="r",
        evidence_event_ids=["ev1"],
        lifecycle_history=[LifecycleHistoryEntry(status=status, changed_at="2026-06-12T08:00:00+00:00")],
    )


def _state():
    return OperationalState(
        project_id="proj-generic",
        tasks=[
            OperationalTask(id="t1", text="installare il sensore", source="m", source_event_id="e1",
                            source_sender="Ann", lifecycle=_lc("task", "open")),
            OperationalTask(id="t2", text="inviare la documentazione", source="m", source_event_id="e2",
                            lifecycle=_lc("task", "completed")),
            OperationalTask(id="t3", text="Nota non operativa: comprare il pane", source="m", source_event_id="e3",
                            lifecycle=_lc("task", "open")),
        ],
        issues=[Issue(id="i1", text="accesso non verificato", source="m", source_event_id="e4", confidence="low",
                      lifecycle=_lc("issue", "open", "low"))],
        decisions=[Decision(id="d1", text="se non pronto si rimanda", source="m", source_event_id="e5",
                            lifecycle=_lc("decision", "confirmed"))],
        open_questions=[OperationalQuestion(id="q1", text="quando consegniamo?", source="m", source_event_id="e6",
                                            lifecycle=_lc("question", "open"))],
        information=[Information(id="info1", text="fornitura prevista venerdì", source="m", source_event_id="e7",
                                lifecycle=_lc("information", "current"))],
    )


def _events():
    return [
        OperationalEvent(event_id="m1", project_id="proj-generic", type="image",
                         attachment_metadata={"extraction_status": "text_extracted"}),
        OperationalEvent(event_id="m2", project_id="proj-generic", type="document",
                         attachment_metadata={"extraction_status": "pdf_text_unavailable"}),
        OperationalEvent(event_id="m3", project_id="proj-generic", type="image",
                         attachment_metadata={"extraction_status": "analysis_error"}),
    ]


def test_report_has_all_sections():
    md = build_refinement_report(_state(), _events())
    for header in [
        "## 1. Sintesi affidabilità", "## 2. Avanzamenti interpretativi",
        "## 3. Possibili incomprensioni", "## 4. Possibili duplicati o conflitti",
        "## 5. Persone e ruoli", "## 6. Media / OCR",
        "## 7. Bug tecnici e caveat", "## 8. Azioni consigliate per Alfio",
    ]:
        assert header in md


def test_report_media_ocr_section_counts():
    md = build_refinement_report(_state(), _events())
    assert "Media analizzati: 3" in md
    assert "OCR riusciti: 1" in md
    assert "falliti: 1" in md
    assert "pdf_text_unavailable" in md.lower() or "PDF senza estrazione" in md


def test_report_includes_incomprensioni_even_if_empty():
    empty = OperationalState(project_id="empty")
    md = build_refinement_report(empty, [])
    assert "## 3. Possibili incomprensioni" in md
    assert "Nessuna incertezza" in md


def test_report_includes_actions():
    md = build_refinement_report(_state(), _events())
    assert "## 8. Azioni consigliate per Alfio" in md
    assert "1." in md


def test_report_is_not_operational_briefing():
    md = build_refinement_report(_state(), _events())
    # It is the refinement report, never the operational card.
    assert "Report di Affinamento Operativo" in md
    assert "📌 Quadro operativo" not in md


def test_report_no_secrets_or_tokens():
    md = build_refinement_report(_state(), _events()).lower()
    for token in ["token", "secret", "password", "api_key", "bearer"]:
        assert token not in md


def test_report_generic_no_hardcoded_domain():
    import re
    import core.operational_memory.refinement_report as mod
    body = open(mod.__file__, "r", encoding="utf-8").read().lower()
    for token in ["tab cefla", "hq enel", "corridoio", "120363", "@g.us", "test tab"]:
        assert not re.search(rf"{re.escape(token)}", body), f"hardcoded: {token}"


def test_report_non_operational_note_flagged():
    md = build_refinement_report(_state(), _events())
    assert "Nota non operativa" in md          # surfaced as an incomprensione
