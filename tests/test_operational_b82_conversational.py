"""B8.2 — Conversational calibration: natural queries + team_brief composer.

Groups:
  1. Natural TAB-targeted queries → bridge (intent recognized after strip).
  2. Natural queries without target → group's own project (safe default),
     recognized as pure queries (no spurious ingest).
  3. Conversational/professional requests → team_brief draft composer:
     labelled draft, no emoji, never auto-sent, not ingested.
"""
from __future__ import annotations

import asyncio
import re

import pytest
from unittest.mock import AsyncMock, patch

from core.operational_memory.query_engine import (
    answer_query,
    classify_query_intent,
    is_pure_operational_invocation,
)
from core.operational_memory.models import OperationalState, OperationalTask, Issue
from core.operational_memory.chat_presence import build_chat_reply

CANARY_JID = "120363428502905378@g.us"
TAB_JID = "120363404290146040@g.us"
TAB_PROJECT = "tab-cefla-hq-enel-roma"
CANARY_PROJECT = "whatsapp-canary-ocr-01"

_TAB_RE = re.compile(r"\b(?:nel|del|di|in)\s+TAB\b|\bTAB\b", re.IGNORECASE)


def _strip_tab(q: str) -> str:
    s = _TAB_RE.sub("", q).strip()
    return re.sub(r"\s{2,}", " ", s).strip()


def _run(coro):
    return asyncio.run(coro)


def _sample_state() -> OperationalState:
    s = OperationalState(project_id="test-b82")
    s.tasks.append(OperationalTask(
        text="Verificare i bracci per ogni zona", source="wa",
        source_event_id="e1", source_timestamp="2026-07-01T08:00:00+00:00",
        due="2026-07-02",
    ))
    s.issues.append(Issue(
        text="UTA T7 non arriva acqua fredda", source="wa",
        source_event_id="e2", source_timestamp="2026-07-01T09:00:00+00:00",
    ))
    return s


# ---------------------------------------------------------------------------
# Group 1 — natural TAB-targeted queries → intent recognized after strip
# ---------------------------------------------------------------------------

def test_g1_fammi_capire_briefing():
    q = _strip_tab("fammi capire cosa sta succedendo nel TAB")
    assert classify_query_intent(q) == "briefing"
    assert is_pure_operational_invocation(q) is True


def test_g1_dove_mettere_attenzione():
    q = _strip_tab("dove devo mettere attenzione nel TAB?")
    assert classify_query_intent(q) == "attention"
    assert is_pure_operational_invocation(q) is True


def test_g1_cosa_manca_davvero():
    q = _strip_tab("cosa manca davvero nel TAB?")
    assert classify_query_intent(q) == "open_tasks"
    assert is_pure_operational_invocation(q) is True


def test_g1_chi_deve_muoversi():
    q = _strip_tab("chi deve muoversi nel TAB?")
    assert classify_query_intent(q) == "open_tasks"
    assert is_pure_operational_invocation(q) is True


def test_g1_cosa_rischia_di_bloccarci():
    q = _strip_tab("cosa rischia di bloccarci nel TAB?")
    assert classify_query_intent(q) == "attention"
    assert is_pure_operational_invocation(q) is True


# ---------------------------------------------------------------------------
# Group 2 — no target → pure query on group's own project (no spurious ingest)
# ---------------------------------------------------------------------------

def test_g2_all_no_target_pure():
    for q, expected in [
        ("cosa devo controllare?", "attention"),
        ("dove siamo scoperti?", "attention"),
        ("cosa rischia di bloccarci?", "attention"),
        ("chi deve muoversi?", "open_tasks"),
        ("cosa manca davvero?", "open_tasks"),
    ]:
        assert classify_query_intent(q) == expected, q
        assert is_pure_operational_invocation(q) is True, q


# ---------------------------------------------------------------------------
# Group 3 — conversational → team_brief / attention, pure (never ingested)
# ---------------------------------------------------------------------------

def test_g3_capocantiere_team_brief():
    q = "spiegamelo come lo diresti a un capocantiere"
    assert classify_query_intent(q) == "team_brief"
    assert is_pure_operational_invocation(q) is True


def test_g3_priorita_attention():
    q = "dammi solo le priorità"
    assert classify_query_intent(q) == "attention"
    assert is_pure_operational_invocation(q) is True


def test_g3_cosa_diresti_al_team():
    q = "cosa diresti al team?"
    assert classify_query_intent(q) == "team_brief"
    assert is_pure_operational_invocation(q) is True


def test_g3_messaggio_operativo():
    q = "preparami un messaggio operativo"
    assert classify_query_intent(q) == "team_brief"
    assert is_pure_operational_invocation(q) is True


def test_g3_sintesi_da_mandare():
    q = "fammi una sintesi da mandare in chat"
    assert classify_query_intent(q) == "team_brief"
    assert is_pure_operational_invocation(q) is True


# ---------------------------------------------------------------------------
# team_brief rendering — draft, no emoji, never auto-sent
# ---------------------------------------------------------------------------

def test_team_brief_reply_is_draft():
    state = _sample_state()
    reply = build_chat_reply(state, "preparami un messaggio operativo")
    assert reply.intent == "team_brief"
    assert "Bozza" in reply.reply_markdown
    assert "non inviata" in reply.reply_markdown


def test_team_brief_reply_no_emoji():
    state = _sample_state()
    reply = build_chat_reply(state, "cosa diresti al team?")
    # No emoji in the draft (proxy: check the known briefing-card emoji absent)
    for emoji in ["📌", "🧭", "📄", "⚠", "✅"]:
        assert emoji not in reply.reply_markdown


def test_team_brief_reply_structure():
    state = _sample_state()
    reply = build_chat_reply(state, "fammi una sintesi da mandare in chat")
    assert "Situazione:" in reply.reply_markdown
    assert "Priorità:" in reply.reply_markdown
    assert "Prossima azione:" in reply.reply_markdown


def test_team_brief_no_raw_dump():
    """Draft must cap the priorities list (max 5 + count), not dump everything."""
    state = _sample_state()
    for n in range(10):
        state.issues.append(Issue(
            text=f"Problema {n} su quadro Q{n}", source="wa",
            source_event_id=f"ex{n}", source_timestamp="2026-07-01T10:00:00+00:00",
        ))
    reply = build_chat_reply(state, "preparami un messaggio operativo")
    priority_lines = [l for l in reply.reply_markdown.splitlines() if l.startswith("- ")]
    assert len(priority_lines) <= 6  # 5 items + "… e altri N"


def test_team_brief_answer_query_dispatch():
    state = _sample_state()
    result = answer_query(state, "preparami un messaggio operativo")
    assert result.intent == "team_brief"


# ---------------------------------------------------------------------------
# WhatsApp integration — bridge for G1, no ingest for G3
# ---------------------------------------------------------------------------

@pytest.fixture()
def _wa_env(monkeypatch):
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational.is_whatsapp_operational_enabled",
        lambda: True,
    )
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational.resolve_whatsapp_project_id",
        lambda jid: CANARY_PROJECT if jid == CANARY_JID else None,
    )
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational.is_whatsapp_operational_reply_enabled",
        lambda jid=None: True,
    )
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational._TAB_BRIDGE_ORIGIN_JID", CANARY_JID
    )
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational._TAB_BRIDGE_PROJECT_ID", TAB_PROJECT
    )
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational.flush_project", AsyncMock()
    )
    # B8.2 tests assume console mode OFF — pin the B8.3 flag regardless of host env.
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational._TAB_BRIDGE_DEFAULT_NO_TARGET",
        False,
    )
    update_mock = AsyncMock()
    monkeypatch.setattr(
        "core.operational_memory.whatsapp_operational._safe_update", update_mock
    )
    return update_mock


def _tab_reply_mock(intent):
    from core.operational_memory.models import ChatReply
    return ChatReply(
        project_id=TAB_PROJECT, intent=intent,
        reply_markdown="mock", synthesis="", table_markdown="",
        actions=[], evidence_event_ids=[], report_id="", report_url="",
    )


def test_g1_natural_tab_queries_bridge(_wa_env):
    """All 5 natural TAB-targeted queries must fire the bridge."""
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    queries = [
        "Genesi, fammi capire cosa sta succedendo nel TAB",
        "Genesi, dove devo mettere attenzione nel TAB?",
        "Genesi, cosa manca davvero nel TAB?",
        "Genesi, chi deve muoversi nel TAB?",
        "Genesi, cosa rischia di bloccarci nel TAB?",
    ]
    for q in queries:
        sent = []

        async def send(jid, text, **kw):
            sent.append((jid, text))

        with patch(
            "core.operational_memory.whatsapp_operational.build_operational_reply",
            new=AsyncMock(return_value=_tab_reply_mock("attention")),
        ) as mock_build:
            _run(maybe_handle_whatsapp_operational(
                group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
                first_name="Alfio", text=q, send_message=send,
            ))
        assert sent and sent[0][0] == CANARY_JID, q
        assert "Vista TAB reale" in sent[0][1], q
        assert mock_build.call_args[0][0] == TAB_PROJECT, q


def test_g3_conversational_not_ingested(_wa_env):
    """Conversational queries are pure → never ingested into canary state."""
    from core.operational_memory.whatsapp_operational import maybe_handle_whatsapp_operational
    update_mock = _wa_env
    for q in [
        "Genesi, preparami un messaggio operativo",
        "Genesi, cosa diresti al team?",
        "Genesi, dammi solo le priorità",
    ]:
        async def send(jid, text, **kw):
            pass

        with patch(
            "core.operational_memory.whatsapp_operational.build_operational_reply",
            new=AsyncMock(return_value=_tab_reply_mock("team_brief")),
        ):
            _run(maybe_handle_whatsapp_operational(
                group_jid=CANARY_JID, sender_jid="s@s.whatsapp.net",
                first_name="Alfio", text=q, send_message=send,
            ))
    update_mock.assert_not_called()


# ---------------------------------------------------------------------------
# Non-regression
# ---------------------------------------------------------------------------

def test_existing_intents_unchanged():
    for q, exp in [
        ("fammi il punto", "briefing"),
        ("riepiloga", "digest"),
        ("cosa manca", "open_tasks"),
        ("problemi aperti", "open_issues"),
        ("stato", "cmd_stato"),
        ("decisioni prese", "active_decisions"),
        ("cosa devo controllare ?", "attention"),
        ("dove siamo scoperti ?", "attention"),
        ("scadenze", "attention"),
        ("domande aperte", "unanswered"),
    ]:
        assert classify_query_intent(q) == exp, q


def test_operational_update_still_ingested():
    """Real updates (not queries) must remain non-pure → ingested."""
    for q in [
        "Il quadro QGBT2 è stato cablato",
        "segna che Mario ha consegnato il cavo FG16",
    ]:
        assert is_pure_operational_invocation(q) is False, q
