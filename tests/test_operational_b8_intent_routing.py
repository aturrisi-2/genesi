"""B8 — TAB bridge intent calibration tests.

Verifies that natural-language query variants (with TAB keyword stripped)
resolve to the correct pure operational intent.  Also tests that the
improved TAB strip regex removes "nel/del/di TAB" as a unit, leaving no
dangling prepositions.
"""
from __future__ import annotations

import re

from core.operational_memory.query_engine import (
    classify_query_intent,
    is_pure_operational_invocation,
)

# Mirror the patched regex from whatsapp_operational
_TAB_RE = re.compile(r"\b(?:nel|del|di|in)\s+TAB\b|\bTAB\b", re.IGNORECASE)


def _strip_tab(q: str) -> str:
    s = _TAB_RE.sub("", q).strip()
    return re.sub(r"\s{2,}", " ", s).strip()


# ---------------------------------------------------------------------------
# Strip regex correctness
# ---------------------------------------------------------------------------

def test_strip_bare_tab():
    assert _strip_tab("stato TAB") == "stato"


def test_strip_nel_tab():
    assert _strip_tab("cosa manca nel TAB?") == "cosa manca ?"


def test_strip_nel_tab_quadro():
    assert _strip_tab("fammi il quadro della situazione nel TAB") == "fammi il quadro della situazione"


def test_strip_del_tab():
    assert _strip_tab("decisioni prese del TAB") == "decisioni prese"


def test_strip_case_insensitive():
    assert _strip_tab("problemi aperti tab") == "problemi aperti"


# ---------------------------------------------------------------------------
# New intents (B8 additions to query_engine._INTENT_PATTERNS)
# ---------------------------------------------------------------------------

# C1c — briefing via "quadro della situazione"
def test_fammi_il_quadro_briefing():
    q = _strip_tab("fammi il quadro della situazione TAB")
    assert classify_query_intent(q) == "briefing"
    assert is_pure_operational_invocation(q) is True


def test_fammi_quadro_briefing_variant():
    assert classify_query_intent("fammi il quadro") == "briefing"
    assert is_pure_operational_invocation("fammi il quadro") is True


# C4a — open_tasks via "chi deve fare cosa"
def test_chi_deve_fare_cosa_open_tasks():
    q = _strip_tab("chi deve fare cosa nel TAB?")
    assert classify_query_intent(q) == "open_tasks"
    assert is_pure_operational_invocation(q) is True


def test_per_responsabile_open_tasks():
    q = _strip_tab("attività per responsabile TAB")
    assert classify_query_intent(q) == "open_tasks"
    assert is_pure_operational_invocation(q) is True


def test_materiali_mancanti_open_tasks():
    q = _strip_tab("materiali mancanti TAB")
    assert classify_query_intent(q) == "open_tasks"
    assert is_pure_operational_invocation(q) is True


# C5a — attention via "cosa scade"
def test_cosa_scade_attention():
    q = _strip_tab("cosa scade a breve nel TAB?")
    assert classify_query_intent(q) == "attention"
    assert is_pure_operational_invocation(q) is True


def test_scadenze_attention():
    assert classify_query_intent("scadenze") == "attention"
    assert is_pure_operational_invocation("scadenze") is True


# C8b — unanswered via "risposte mancano"
def test_risposte_mancano_unanswered():
    assert classify_query_intent("quali risposte mancano") == "unanswered"
    assert is_pure_operational_invocation("quali risposte mancano") is True


# C10b/c — attention via "bloccante/scoperti/bloccarci"
def test_bloccante_attention():
    assert classify_query_intent("cosa è bloccante") == "attention"
    assert is_pure_operational_invocation("cosa è bloccante") is True


def test_bloccarci_attention():
    assert classify_query_intent("cosa rischia di bloccarci") == "attention"
    assert is_pure_operational_invocation("cosa rischia di bloccarci") is True


# ---------------------------------------------------------------------------
# Non-regression: existing intents unchanged by B8 patterns
# ---------------------------------------------------------------------------

def test_existing_cmd_stato_unchanged():
    for q in ["stato", "qual è lo stato?", "a che punto siamo?"]:
        assert classify_query_intent(q) == "cmd_stato", q


def test_existing_open_issues_unchanged():
    assert classify_query_intent("problemi aperti") == "open_issues"


def test_existing_open_tasks_cosa_manca_unchanged():
    assert classify_query_intent("cosa manca") == "open_tasks"


def test_existing_unanswered_unchanged():
    assert classify_query_intent("domande aperte") == "unanswered"


def test_existing_active_decisions_unchanged():
    assert classify_query_intent("decisioni prese") == "active_decisions"


def test_existing_briefing_fammi_il_punto_unchanged():
    assert classify_query_intent("fammi il punto") == "briefing"


def test_existing_digest_riepilog_unchanged():
    assert classify_query_intent("riepiloga") == "digest"


# ---------------------------------------------------------------------------
# B8 queries that remain NO_TAB_KW (fail-closed, correct)
# ---------------------------------------------------------------------------

def test_blocco_without_tab_correct_intent():
    # No TAB keyword → stays in canary project via normal flow
    # But intent is still recognized correctly if analyzed
    assert classify_query_intent("cosa è bloccante") == "attention"


def test_decisioni_without_tab_correct_intent():
    assert classify_query_intent("quali decisioni tecniche risultano") == "active_decisions"
