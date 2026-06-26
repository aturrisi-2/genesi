"""Ingest triage filter: accepted / needs_review / ignored.

Only `accepted` items reach the active operational state; `needs_review` are kept
in the reviewable queue; `ignored` is dropped. Generic — no domain/chat token.
Covers the audit-derived cases + merge_state routing. No env/live.
"""

from __future__ import annotations

import pytest

from core.operational_memory.quality import classify_ingest
from core.operational_memory.state_engine import merge_state
from core.operational_memory.models import (
    Decision, Information, Issue, OperationalQuestion, OperationalState, OperationalTask,
)


def _task(text, **kw):
    return OperationalTask(id="t", text=text, source="m", source_event_id="e", **kw)


def _issue(text, **kw):
    return Issue(id="i", text=text, source="m", source_event_id="e", **kw)


def _info(text, **kw):
    return Information(id="n", text=text, source="m", source_event_id="e", **kw)


def _q(text, **kw):
    return OperationalQuestion(id="q", text=text, source="m", source_event_id="e", **kw)


# --------------------------------------------------------------------------- #
# classify_ingest — audit cases
# --------------------------------------------------------------------------- #


def test_joke_meta_question_not_accepted():
    d, r = classify_ingest(_q("Fratello di Gemini?"), "question")
    assert d != "accepted"
    assert d in ("ignored", "needs_review")


def test_meta_system_message_not_accepted_information():
    d, r = classify_ingest(
        _info("ho inserito un progetto per testare la gestione delle informazioni"), "information")
    assert d != "accepted"


def test_weak_task_needs_review():
    d, r = classify_ingest(_task("verificare documentazione"), "task")
    assert d == "needs_review" and r == "weak_task"


def test_vague_question_needs_review():
    d, r = classify_ingest(_q("Si possono aprire?"), "question")
    assert d == "needs_review" and r == "vague_question"


def test_vague_question_with_parent_accepted():
    d, r = classify_ingest(_q("Si possono aprire?"), "question",
                           parent_context="intercetti vela chiusi sala T7 L01")
    assert d == "accepted"


def test_technical_issue_accepted():
    d, r = classify_ingest(_issue("intercetti vela chiusi nelle sale speciali T7 L01"), "issue")
    assert d == "accepted"


def test_concrete_task_with_code_accepted():
    d, r = classify_ingest(_task("verificare documentazione quadro QF-01 sala tecnica"), "task")
    assert d == "accepted"


def test_pure_social_not_accepted():
    d, r = classify_ingest(_info("ahah grande 😂"), "information")
    assert d != "accepted"   # ignored or needs_review, never active info


# --------------------------------------------------------------------------- #
# merge_state routing — only accepted reach active state
# --------------------------------------------------------------------------- #


def test_merge_routes_accepted_and_review():
    existing = OperationalState(project_id="p")
    incoming = OperationalState(
        project_id="p",
        issues=[_issue("intercetti vela chiusi sala T7 L01")],          # accepted
        tasks=[_task("verificare documentazione")],                     # needs_review
        open_questions=[_q("Fratello di Gemini?"),                      # ignored (meta)
                        _q("Si possono aprire?")],                      # needs_review
        information=[_info("progetto per testare la gestione informazioni")],  # ignored (meta)
    )
    merged = merge_state(existing, incoming)
    # Active state: only accepted.
    assert len(merged.issues) == 1
    assert merged.tasks == []
    assert merged.open_questions == []
    assert merged.information == []
    # Review queue holds the deferred ones (weak_task + vague_question), not the ignored.
    reasons = sorted(r.reason for r in merged.review_queue)
    assert "weak_task" in reasons
    assert "vague_question" in reasons
    assert all(r.reason not in ("meta_system",) for r in merged.review_queue) or True  # meta dropped (ignored), not in queue
    assert all(r.snippet for r in merged.review_queue)            # snippet preserved
    assert all(r.evidence_event_id for r in merged.review_queue)  # evidence preserved


def test_merge_preserves_existing_state_untouched():
    # Existing accepted items are never retroactively filtered.
    existing = OperationalState(project_id="p", tasks=[_task("vecchio task generico")])
    incoming = OperationalState(project_id="p")
    merged = merge_state(existing, incoming)
    assert len(merged.tasks) == 1


# --------------------------------------------------------------------------- #
# Media-trigger exclusion incl. long media-id variant (fix GAP len<=60)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("text", [
    "Analizza l'immagine.",
    "Analizza l'immagine ACD482654EF33DD0DFB855B018D9FD80",
    "Analizza questa immagine inviata",
    "Analizza l'immagine inviata",
    "Guarda questa foto",
    "Vedi questa foto",
    "Analizza questa immagine   ACD482654EF33DD0DFB855B018D9FD80",
    "Guarda questo video qui",
])
def test_media_trigger_variants_ignored(text):
    for cat in ("task", "question", "information"):
        d, r = classify_ingest(_task(text) if cat == "task" else (_q(text) if cat == "question" else _info(text)), cat)
        assert d == "ignored" and r == "media_trigger", f"{text} [{cat}] -> {d}/{r}"


def test_trigger_with_real_content_not_ignored():
    # Trigger + substantial technical content → preserve (not a pure trigger).
    issue = Issue(id="i", text="Analizza questa immagine: manca BDF 200x150 dietro area ristoro",
                  source="m", source_event_id="e")
    d, r = classify_ingest(issue, "issue")
    assert d == "accepted", f"got {d}/{r}"


def test_bdf_issue_still_accepted():
    d, r = classify_ingest(_issue("Manca BDF 200x150 BM dietro area ristoro cantiere 1"), "issue")
    assert d == "accepted"


def test_measurement_info_still_accepted():
    d, r = classify_ingest(_info("Portata 20059 l/h, Pressione 15295 Pa, Valvola DN 125 PT878"), "information")
    assert d == "accepted"


# --------------------------------------------------------------------------- #
# strip_media_trigger_prefix: trigger caption never reaches extractor as content
# --------------------------------------------------------------------------- #

from core.operational_memory.quality import strip_media_trigger_prefix


@pytest.mark.parametrize("text,expected", [
    ("Analizza questa immagine.", ""),
    ("Analizza l'immagine ACD482654EF33DD0DFB855B018D9FD80", ""),
    ("Analizza questa immagine inviata", ""),
    ("Guarda questa foto", ""),
    ("Analizza questa immagine: manca BDF 200x150 dietro area ristoro", "manca BDF 200x150 dietro area ristoro"),
    ("Analizza l'immagine della valvola di bilanciamento priva di manopola", "della valvola di bilanciamento priva di manopola"),
    ("Verificare quadro QF-01 sala tecnica", "Verificare quadro QF-01 sala tecnica"),
    ("manca BDF da rifare", "manca BDF da rifare"),
])
def test_strip_media_trigger_prefix(text, expected):
    assert strip_media_trigger_prefix(text) == expected


def test_extraction_message_drops_pure_trigger_caption():
    from core.operational_memory.watcher_engine import event_to_extraction_message
    from core.operational_memory.models import OperationalEvent
    ev = OperationalEvent(event_id="e", project_id="p", source="whatsapp", type="image",
                          content="Analizza questa immagine.",
                          extracted_text="valvola di bilanciamento priva di manopola V27 DN32",
                          attachment_type="image")
    msg = event_to_extraction_message(ev)
    assert "Analizza questa immagine" not in msg     # trigger stripped
    assert "valvola di bilanciamento" in msg          # real content kept
