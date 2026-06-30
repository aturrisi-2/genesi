"""Natural-language status/update invocations resolve to the inline 'stato'
command: pure read-only intent, never ingested. Working query intents are
unchanged. Synthetic only; no WhatsApp, no network.
"""
from core.operational_memory.query_engine import (
    classify_query_intent,
    is_pure_operational_invocation,
)

STATUS_NL = [
    "qual è lo stato?",
    "che stato abbiamo?",
    "stato lavori?",
    "a che punto siamo?",
    "aggiorna lo stato",
    "aggiornami sullo stato",
    "dammi lo stato",
    "qual è la situazione?",
]


def test_status_nl_resolves_to_cmd_stato_pure():
    for q in STATUS_NL:
        assert classify_query_intent(q) == "cmd_stato", q
        assert is_pure_operational_invocation(q) is True, q  # never ingested


def test_aggiorna_lo_stato_is_not_a_task():
    # The key G3 regression: an update-status invocation must be a pure query,
    # not stored as a project item.
    assert classify_query_intent("aggiorna lo stato") == "cmd_stato"
    assert is_pure_operational_invocation("aggiorna lo stato") is True


def test_working_intents_unchanged():
    assert classify_query_intent("problemi aperti?") == "open_issues"
    assert classify_query_intent("cosa manca?") == "open_tasks"
    assert classify_query_intent("decisioni prese?") == "active_decisions"
    assert classify_query_intent("fammi il report") == "briefing"
    assert classify_query_intent("stato") == "cmd_stato"
    assert classify_query_intent("aperti") == "cmd_aperti"
    assert classify_query_intent("report") == "cmd_report"


def test_noise_and_operational_statements_not_status():
    # Noise / confirmations are not status invocations.
    assert classify_query_intent("Ok") == "unknown"
    assert classify_query_intent("Perfetto") == "unknown"
    # A real operational statement must remain ingestible (not a pure query).
    stmt = "Quadro QGBT cablato, manca solo collaudo."
    assert is_pure_operational_invocation(stmt) is False


def test_explicit_update_with_colon_still_ingested():
    # "aggiorna: <fact>" carries a real update → must NOT be treated as pure.
    assert is_pure_operational_invocation("aggiorna: la valvola DN32 è chiusa") is False
