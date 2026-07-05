"""Group conversational-continuity coverage.

Investigates the reported symptom: in conversational groups Genesi "wakes from
hibernation" — when invoked (or when it auto-activates) it replies as if it had
seen only the last message, ignoring the recent discussion and the historical
context it should have been following silently.

These tests are OFFLINE and side-effect free:
  * no live WhatsApp/Telegram send (send/updater are in-memory spies);
  * no real LLM (extractor is mocked);
  * no real state store (stores are redirected to tmp_path);
  * the empathic/operational root causes are pinned via static source checks.

They characterise WHERE the continuity is preserved (data layer) and WHERE it is
lost (the deterministic reply builder deflects on non-operational phrasing, and
the empathic prompt instructs the model to ignore the injected context). Generic:
no chat/JID/profession token is hardcoded.
"""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock

import pytest

from core.operational_memory.models import (
    Decision,
    Issue,
    OperationalQuestion,
    OperationalState,
    OperationalTask,
)
from core.operational_memory.query_engine import answer_query, classify_query_intent


GROUP_JID = "120363000000000001@g.us"
SENDER_JID = "393339990001"
PROJECT = "continuity-test-proj"

_EMPTY_LLM = json.dumps(
    {"decisions": [], "tasks": [], "issues": [], "information": [], "open_questions": []}
)


async def _drain_background_tasks():
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


# --------------------------------------------------------------------------- #
# A realistic recent discussion (8–12 messages): decision, task, issue, a reply
# to an earlier message, then a topic change and a final invocation.
# --------------------------------------------------------------------------- #

# (message_id, sender, text, reply_to_id)
_DISCUSSION: list[tuple[str, str, str, str | None]] = [
    ("m1", "Anna", "La fornitura di cavi al piano 3 è arrivata incompleta", None),
    ("m2", "Bruno", "Confermo, mancano ancora due bobine", "m1"),
    ("m3", "Anna", "Allora spostiamo il collaudo del piano 3 a mercoledì", None),
    ("m4", "Carla", "Ok per mercoledì, avviso l'elettricista", None),
    ("m5", "Bruno", "Marco deve verificare il quadro elettrico prima del collaudo", None),
    ("m6", "Marco", "Va bene, lo controllo domani mattina", "m5"),
    ("m7", "Carla", "Ricordate che venerdì c'è il sopralluogo del cliente", None),
    ("m8", "Anna", "Per il piano 5 invece va tutto liscio", None),
    ("m9", "Bruno", "Sì, piano 5 nessun problema aperto", None),
]


@pytest.fixture
def enabled(monkeypatch):
    monkeypatch.setenv("OPERATIONAL_MEMORY_WHATSAPP_ENABLED", "true")
    monkeypatch.setenv("WHATSAPP_CHAT_PROJECT_MAP", json.dumps({GROUP_JID: PROJECT}))
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://genesi.example.com/")
    return monkeypatch


@pytest.fixture
def isolated_stores(monkeypatch, tmp_path):
    from core.operational_memory import (
        event_store,
        incremental_index,
        snapshot_store,
        state_store,
    )

    monkeypatch.setattr(event_store, "_BASE_DIR", tmp_path / "events")
    monkeypatch.setattr(state_store, "_BASE_DIR", tmp_path / "state")
    monkeypatch.setattr(snapshot_store, "_BASE_DIR", tmp_path / "snap")
    monkeypatch.setattr(snapshot_store, "_LIFECYCLE_BASE_DIR", tmp_path / "lcsnap")
    monkeypatch.setattr(incremental_index, "_BASE_DIR", tmp_path / "idx")
    monkeypatch.setattr(
        "core.operational_memory.extractor.llm_service._call_model",
        AsyncMock(return_value=_EMPTY_LLM),
    )
    return tmp_path


# --------------------------------------------------------------------------- #
# 1. DATA LAYER — every observed message is persisted under ONE project_id and
#    is available at invocation time. This is the "always vigilant" guarantee:
#    silent ingest never drops a message, so nothing is lost before a reply.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_silent_ingest_persists_whole_discussion(enabled, isolated_stores):
    from core.operational_memory import event_store
    from core.operational_memory.whatsapp_operational import (
        maybe_handle_whatsapp_operational,
    )

    sent: list = []

    async def send(to, text, *a, **k):
        sent.append((to, text))

    # The group talks; Genesi is silent but listening (reply flag OFF by default).
    for mid, sender, text, reply_to in _DISCUSSION:
        handled = await maybe_handle_whatsapp_operational(
            GROUP_JID, SENDER_JID, sender, text, send,
            message_id=mid, reply_to_id=reply_to,
        )
        assert handled is True  # operational-dominant: claimed, empathic suppressed

    await _drain_background_tasks()

    events = await event_store.list_events(PROJECT)
    stored_ids = {e.event_id for e in events}
    expected_ids = {mid for mid, *_ in _DISCUSSION}

    # Continuity guarantee: the FULL recent discussion is available, not just the
    # last message — and it is all under the single resolved project_id.
    assert expected_ids <= stored_ids
    assert all(e.project_id == PROJECT for e in events)
    assert sent == []  # silent: reply flag OFF, nothing sent live


@pytest.mark.asyncio
async def test_reply_to_binds_parent_event(enabled, isolated_stores):
    """A reply/quote must carry the parent binding into the operational event, so
    the thread relation is preserved (not treated as an isolated last message)."""
    from core.operational_memory import event_store
    from core.operational_memory.whatsapp_operational import (
        maybe_handle_whatsapp_operational,
    )

    async def send(to, text, *a, **k):
        pass

    await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Anna", "problema alla fornitura", send, message_id="p1")
    await maybe_handle_whatsapp_operational(
        GROUP_JID, SENDER_JID, "Bruno", "confermo", send, message_id="p2", reply_to_id="p1")
    await _drain_background_tasks()

    events = {e.event_id: e for e in await event_store.list_events(PROJECT)}
    assert events["p2"].parent_event_id == "p1"
    assert events["p2"].reply_relation == "reply_to"


# --------------------------------------------------------------------------- #
# 2. STATE LAYER — an invocation reply reflects the WHOLE discussion (an issue
#    raised in the first message is still answered many turns later), proving the
#    persistent operational memory is fused into the reply, not a cold snapshot.
# --------------------------------------------------------------------------- #


def _discussion_state() -> OperationalState:
    st = OperationalState(project_id=PROJECT)
    st.issues.append(
        Issue(text="La fornitura di cavi al piano 3 è incompleta",
              source="m1", source_event_id="m1")
    )
    st.decisions.append(
        Decision(text="Il collaudo del piano 3 è spostato a mercoledì",
                 source="m3", source_event_id="m3")
    )
    st.tasks.append(
        OperationalTask(text="Verificare il quadro elettrico del piano 3",
                        source="m5", source_event_id="m5", owner="Marco")
    )
    st.open_questions.append(
        OperationalQuestion(text="Confermare l'orario del sopralluogo cliente",
                            source="m7", source_event_id="m7")
    )
    return st


def test_operational_invocation_reflects_early_discussion():
    st = _discussion_state()

    # Issue raised in the FIRST message is still surfaced when asked later.
    r_issues = answer_query(st, "problemi aperti")
    assert r_issues.intent == "open_issues"
    assert any("fornitura di cavi" in it.text for it in r_issues.items)

    # Decision + task + question from across the discussion are all reachable.
    assert any("mercoledì" in it.text for it in answer_query(st, "decisioni attive").items)
    r_open = answer_query(st, "cosa resta aperto?")
    texts = " | ".join(it.text for it in r_open.items)
    assert "quadro elettrico" in texts
    assert "fornitura di cavi" in texts


# --------------------------------------------------------------------------- #
# 3. THE COLD-START GAP — a conversational invocation that references the recent
#    discussion (but doesn't use operational keywords) is NOT understood: the
#    deterministic reply builder classifies it as `unknown` and returns a canned
#    deflection with zero items and zero awareness of what was just discussed.
#    This is the mechanism behind the "wakes from hibernation" symptom.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "conversational_query",
    [
        "e allora per quella storia come ci muoviamo?",
        "ma di quello che diceva Anna prima, com'è finita?",
        "ok ma con l'elettricista di Carla ci siamo sentiti?",
    ],
)
def test_conversational_invocation_falls_into_cold_start(conversational_query):
    st = _discussion_state()
    # Even with a rich, up-to-date state, a natural follow-up to the discussion
    # is not recognised → cold-start deflection, no thread awareness.
    assert classify_query_intent(conversational_query) == "unknown"
    result = answer_query(st, conversational_query)
    assert result.intent == "unknown"
    assert result.count == 0
    assert result.items == []
    assert "non riconosciuta" in result.summary.lower()


def test_operational_reply_builder_has_no_conversation_window():
    """Root cause (operational path): the reply builder is fed only the invocation
    query + the distilled state. There is no parameter through which the recent
    conversation window / thread could reach it — so a follow-up that depends on
    the last few messages cannot be answered in context."""
    import inspect

    from core.operational_memory.chat_presence import build_operational_reply

    params = set(inspect.signature(build_operational_reply).parameters)
    # It receives the query string, never the surrounding conversation.
    assert "query" in params
    assert not (params & {
        "recent_messages", "conversation", "history", "thread", "context_window",
    })


# --------------------------------------------------------------------------- #
# 4. EMPATHIC PATH CONTRACT (static) — the family/conversational path assembles a
#    rich recent-discussion + history context AND now instructs the model to use
#    it (enter "already informed", stay in the current thread) instead of the old
#    veto that made it answer only the last message. The anti-staleness concern is
#    kept as a SOFT guard (don't resurface long-closed topics unprompted), not a
#    blanket "reply only to the current message".
# --------------------------------------------------------------------------- #

# The hard veto that produced the "cold start" symptom — must NOT come back.
_HARD_VETO_MARKERS = (
    "Rispondi SOLO a ciò che viene detto ADESSO",
    "Rispondi SOLO a quello che viene detto adesso",
)


def test_shared_assembler_uses_context_instead_of_vetoing_it():
    src = open("core/telegram_group_memory.py", "r", encoding="utf-8").read()

    # The rich context IS assembled (recent discussion + Genesi's recent replies).
    assert "DISCUSSIONE IN CORSO" in src
    assert "RISPOSTE RECENTI DI GENESI" in src

    # Continuity contract present: follow the thread, enter already informed.
    assert "COERENZA CONVERSAZIONALE" in src
    assert "GIÀ INFORMATA" in src

    # The hard veto is gone; the soft anti-staleness guard remains.
    for marker in _HARD_VETO_MARKERS:
        assert marker not in src
    assert "non riesumare" in src.lower()


def test_whatsapp_inline_block_preserves_conversation_thread():
    src = open("core/whatsapp_bot.py", "r", encoding="utf-8").read()
    assert "COERENZA:" in src
    assert "restando nel filo della conversazione in corso" in src
    assert "Rispondi SOLO a quello che viene detto adesso" not in src


def test_telegram_inline_block_preserves_conversation_thread():
    src = open("core/telegram_bot.py", "r", encoding="utf-8").read()
    assert "entrando nel discorso già informata" in src
    assert "Rispondi SOLO al messaggio attuale" not in src
