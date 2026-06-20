from __future__ import annotations

import asyncio
import json

import pytest

from core.operational_memory.models import (
    Issue,
    LifecycleHistoryEntry,
    LifecycleState,
    OperationalState,
    OperationalTask,
)


CHAT_ID = -1001234567890
PROJECT = "tg-proj-generic"


def _lc(category, status):
    return LifecycleState(category=category, current_status=status, evidence_event_ids=["ev1"],
                          lifecycle_history=[LifecycleHistoryEntry(status=status, changed_at="2026-06-12T08:00:00+00:00")])


def _seed():
    return OperationalState(
        project_id=PROJECT,
        tasks=[OperationalTask(id="t1", text="ordinare materiale", source="m", source_event_id="e1", lifecycle=_lc("task", "open"))],
        issues=[Issue(id="i1", text="consegna in ritardo", source="m", source_event_id="e2", lifecycle=_lc("issue", "open"))],
    )


@pytest.fixture
def env(monkeypatch, tmp_path):
    from core.operational_memory import state_store, report_store

    monkeypatch.setattr(state_store, "_BASE_DIR", tmp_path / "state")
    monkeypatch.setattr(report_store, "_BASE_DIR", tmp_path / "reports")
    asyncio.run(state_store.save_state(PROJECT, _seed()))
    monkeypatch.setenv("OPERATIONAL_MEMORY_TELEGRAM_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_OPERATIONAL_REPLY_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_CHAT_PROJECT_MAP", json.dumps({str(CHAT_ID): PROJECT}))
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://genesi.example.com/")
    return monkeypatch


def _spies():
    sent = []   # list of (chat_id, text, reply_markup)
    ingested = []

    async def send(chat_id, text, reply_markup=None, **k):
        sent.append((chat_id, text, reply_markup))

    async def updater(message):
        ingested.append(message.message_id)

    return sent, ingested, send, updater


@pytest.mark.asyncio
async def test_disabled_is_noop(monkeypatch):
    from core.operational_memory.telegram_operational import maybe_handle_operational
    monkeypatch.setenv("OPERATIONAL_MEMORY_TELEGRAM_ENABLED", "false")
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_operational(CHAT_ID, 1, "Ann", "Genesi, fammi il punto", send, updater=updater)
    await asyncio.sleep(0)
    assert handled is False and sent == [] and ingested == []


@pytest.mark.asyncio
async def test_unmapped_chat_is_noop(env):
    from core.operational_memory.telegram_operational import maybe_handle_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_operational(-999, 1, "Ann", "Genesi, fammi il punto", send, updater=updater)
    await asyncio.sleep(0)
    assert handled is False and sent == [] and ingested == []


@pytest.mark.asyncio
async def test_normal_message_silent_but_ingested(env):
    from core.operational_memory.telegram_operational import maybe_handle_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_operational(CHAT_ID, 1, "Ann", "ragazzi domani portiamo i pezzi", send,
                                             message_id="m1", updater=updater)
    await asyncio.sleep(0)
    assert handled is False        # not invoked → existing pipeline proceeds
    assert sent == []              # no operational reply
    assert ingested == ["m1"]      # but memory was updated


@pytest.mark.asyncio
async def test_invocation_sends_reply_with_report_link(env):
    from core.operational_memory.telegram_operational import maybe_handle_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_operational(CHAT_ID, 1, "Ann", "Genesi, fammi il punto", send,
                                             message_id="m2", updater=updater)
    await asyncio.sleep(0)
    assert handled is True
    assert ingested == ["m2"]                     # ingested even when replying
    assert len(sent) == 1
    chat_id, text, reply_markup = sent[0]
    assert chat_id == CHAT_ID
    assert "Quadro operativo" in text
    # URL is NOT in the message text — it goes in the inline button
    assert "https://genesi.example.com" not in text
    assert "| Categoria | N |" not in text        # no pipe table in chat message
    assert "•" in text                             # mobile card bullet format
    # inline button carries the report URL
    assert reply_markup is not None
    kb = reply_markup["inline_keyboard"]
    assert len(kb) == 1 and len(kb[0]) == 1
    btn = kb[0][0]
    assert btn["text"] == "Apri report"
    assert "https://genesi.example.com/api/operational/projects/" in btn["url"]
    assert "/view" in btn["url"]


@pytest.mark.asyncio
async def test_specific_query_excludes_resolved(env, monkeypatch):
    from core.operational_memory import state_store
    from core.operational_memory.telegram_operational import maybe_handle_operational
    # add a resolved issue; it must not be shown as active
    state = _seed()
    state.issues.append(Issue(id="i2", text="accesso non funzionante", source="m", source_event_id="e3", lifecycle=_lc("issue", "resolved")))
    await state_store.save_state(PROJECT, state)
    sent, ingested, send, updater = _spies()
    await maybe_handle_operational(CHAT_ID, 1, "Ann", "Genesi, quali problemi sono aperti?", send, message_id="m3", updater=updater)
    await asyncio.sleep(0)
    text = sent[0][1]
    assert "consegna in ritardo" in text
    assert "accesso non funzionante" not in text


@pytest.mark.asyncio
async def test_reply_disabled_falls_through(env, monkeypatch):
    from core.operational_memory.telegram_operational import maybe_handle_operational
    monkeypatch.setenv("TELEGRAM_OPERATIONAL_REPLY_ENABLED", "false")
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_operational(CHAT_ID, 1, "Ann", "Genesi, fammi il punto", send, message_id="m4", updater=updater)
    await asyncio.sleep(0)
    assert handled is False          # let existing pipeline answer
    assert sent == []
    assert ingested == ["m4"]        # still ingested


def test_mapping_configurable_via_env(monkeypatch):
    from core.operational_memory.telegram_operational import project_for_chat
    monkeypatch.setenv("TELEGRAM_CHAT_PROJECT_MAP", json.dumps({"-100": "alpha", "-200": "beta"}))
    assert project_for_chat(-100) == "alpha"
    assert project_for_chat(-200) == "beta"
    assert project_for_chat(-300) is None


@pytest.mark.asyncio
async def test_no_double_reply_contract(env):
    # Contract: handled==True is the signal for the caller (telegram_bot) to stop,
    # so the empathic pipeline never sends a second reply on the same update.
    from core.operational_memory.telegram_operational import maybe_handle_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_operational(CHAT_ID, 1, "Ann", "Genesi, fammi il punto", send, message_id="d1", updater=updater)
    await asyncio.sleep(0)
    assert handled is True       # caller returns -> existing pipeline skipped
    assert len(sent) == 1        # exactly one (operational) reply, never two
    # And a non-invocation never claims the update (empathic pipeline keeps it).
    handled2 = await maybe_handle_operational(CHAT_ID, 1, "Ann", "ciao a tutti", send, message_id="d2", updater=updater)
    await asyncio.sleep(0)
    assert handled2 is False


def test_bridge_does_not_import_empathic_or_whatsapp():
    # The bridge must not IMPORT the empathic persona/proactor/chat pipeline or
    # WhatsApp. Inspect actual import statements (not doc comments).
    import core.operational_memory.telegram_operational as mod
    import_lines = [
        line.strip().lower()
        for line in open(mod.__file__, "r", encoding="utf-8")
        if line.lstrip().startswith(("import ", "from "))
    ]
    blob = "\n".join(import_lines)
    for forbidden in ["proactor", "simple_chat", "message_pipeline", "whatsapp",
                      "api.chat", "persona", "telegram_bot", "llm_service"]:
        assert forbidden not in blob, f"bridge imports forbidden dependency: {forbidden}"
    # It DOES delegate to the operational service layer.
    src = open(mod.__file__, "r", encoding="utf-8").read()
    assert "build_operational_reply" in src


@pytest.mark.asyncio
async def test_bridge_delegates_to_service(env, monkeypatch):
    # The bridge calls the service layer (build_operational_reply); stub it to
    # prove the bridge holds no reply-building logic of its own.
    import core.operational_memory.telegram_operational as mod
    from core.operational_memory.models import ChatReply

    called = {}

    async def fake_service(project_id, query, report_base_url="", invoked_by="", save=True):
        called["project_id"] = project_id
        called["query"] = query
        called["base"] = report_base_url
        return ChatReply(project_id=project_id, intent="briefing", reply_markdown="STUB-REPLY", report_id="r", report_url="u")

    monkeypatch.setattr(mod, "build_operational_reply", fake_service)
    sent, ingested, send, updater = _spies()
    handled = await mod.maybe_handle_operational(CHAT_ID, 1, "Ann", "Genesi, fammi il punto", send, message_id="s1", updater=updater)
    await asyncio.sleep(0)
    assert handled is True
    assert called["project_id"] == PROJECT and called["base"] == "https://genesi.example.com"
    # sent[0] = (chat_id, text, reply_markup); stub report_url="u" → inline button present
    assert sent[0][0] == CHAT_ID
    assert sent[0][1] == "STUB-REPLY"
    assert sent[0][2] == {"inline_keyboard": [[{"text": "Apri report", "url": "u"}]]}


def test_no_hardcoded_domain_tokens():
    import re
    import core.operational_memory.telegram_operational as mod
    body = open(mod.__file__, "r", encoding="utf-8").read().upper()
    for token in ["TAB CEFLA", "T6", "T7", "UTA", "EWC05", "SS01", "B02", "CANTIERE"]:
        assert not re.search(rf"\b{re.escape(token)}\b", body), f"hardcoded token: {token}"


@pytest.mark.asyncio
async def test_inline_button_absent_when_no_report_url(env, monkeypatch):
    """When report_url is empty, no inline button should be sent."""
    import core.operational_memory.telegram_operational as mod
    from core.operational_memory.models import ChatReply

    async def fake_no_url(project_id, query, report_base_url="", invoked_by="", save=True):
        return ChatReply(project_id=project_id, intent="briefing", reply_markdown="TEXT", report_id="", report_url="")

    monkeypatch.setattr(mod, "build_operational_reply", fake_no_url)
    sent, ingested, send, updater = _spies()
    await mod.maybe_handle_operational(CHAT_ID, 1, "Ann", "Genesi, fammi il punto", send, message_id="nb1", updater=updater)
    await asyncio.sleep(0)
    assert sent[0][2] is None   # no reply_markup


@pytest.mark.asyncio
async def test_normal_message_empathic_send_not_broken(env):
    """Non-invocation messages return False; the empathic pipeline is free to send
    without reply_markup — verifies no regression on existing send signature."""
    from core.operational_memory.telegram_operational import maybe_handle_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_operational(CHAT_ID, 1, "Bob", "buongiorno a tutti", send, message_id="nb2", updater=updater)
    await asyncio.sleep(0)
    assert handled is False
    assert sent == []   # empathic pipeline untouched
