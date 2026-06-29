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

    async def offline_image_description(path):
        return {
            "image_status": "image_no_content",
            "text": "",
            "description": "",
            "error": "",
        }

    async def fail_real_vision_provider(path):
        raise AssertionError("test must not call the real image vision provider")

    monkeypatch.setattr(
        "core.operational_memory.media_processor.describe_image_file",
        offline_image_description,
    )
    monkeypatch.setattr(
        "core.operational_memory.image_describer.describe_image_file",
        offline_image_description,
    )
    monkeypatch.setattr(
        "core.image_vision_service.describe_image",
        fail_real_vision_provider,
    )

    asyncio.run(state_store.save_state(PROJECT, _seed()))
    monkeypatch.setenv("OPERATIONAL_MEMORY_TELEGRAM_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_OPERATIONAL_REPLY_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_CHAT_PROJECT_MAP", json.dumps({str(CHAT_ID): PROJECT}))
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://genesi.example.com/")
    return monkeypatch


def _spies():
    sent = []   # list of (chat_id, text, reply_markup, parse_mode)
    ingested = []

    async def send(chat_id, text, reply_markup=None, parse_mode=None, **k):
        sent.append((chat_id, text, reply_markup, parse_mode))

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
    assert ingested == []                         # pure briefing query → not ingested as event
    assert len(sent) == 1
    chat_id, text, reply_markup, parse_mode = sent[0]
    assert chat_id == CHAT_ID
    assert parse_mode == "HTML"
    assert "Quadro operativo" in text
    # Telegram HTML: headings are bold
    assert "<b>Quadro operativo</b>" in text
    # Category links with focus parameter
    assert 'focus=tasks-open' in text
    assert 'focus=decisions-active' in text
    assert '• <a href=' in text                     # clickable category links
    # Structured synthesis
    assert "<b>Sintesi operativa</b>" in text
    # URL is NOT shown as plain text — only in links/button
    assert "| Categoria | N |" not in text          # no pipe table in chat message
    # inline button carries the full report URL
    assert reply_markup is not None
    kb = reply_markup["inline_keyboard"]
    assert len(kb) == 1 and len(kb[0]) == 1
    btn = kb[0][0]
    assert btn["text"] == "Apri report completo"
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
    assert sent[0][2] == {"inline_keyboard": [[{"text": "Apri report completo", "url": "u"}]]}


@pytest.mark.asyncio
async def test_invocation_rebuilds_before_reply(env, monkeypatch):
    # On an update-bearing invocation the ingest must be AWAITED before the reply
    # is built, so the answer reflects the just-ingested event (no race).
    import core.operational_memory.telegram_operational as mod
    from core.operational_memory.models import ChatReply

    order = []

    async def ordered_updater(message):
        order.append("update")

    async def fake_reply(project_id, query, report_base_url="", invoked_by="", save=True):
        order.append("reply")
        return ChatReply(project_id=project_id, intent="unknown", reply_markdown="X", report_id="r", report_url="u")

    monkeypatch.setattr(mod, "build_operational_reply", fake_reply)
    sent, ingested, send, _ = _spies()
    handled = await mod.maybe_handle_operational(
        CHAT_ID, 1, "Ann", "Genesi, segna che il materiale è confermato", send, message_id="ord1", updater=ordered_updater
    )
    assert handled is True
    assert order == ["update", "reply"]   # ingest strictly before reply


@pytest.mark.asyncio
async def test_rebuild_still_happens_before_reply_for_pure_invocation(env, monkeypatch):
    # Pure invocation: NO event ingest, but a flush/rebuild must still run BEFORE
    # the reply so it reflects previously ingested messages.
    import core.operational_memory.telegram_operational as mod
    from core.operational_memory.models import ChatReply

    order = []

    async def fake_flush(project_id, rebuild=True):
        order.append("flush")

    async def fake_reply(project_id, query, report_base_url="", invoked_by="", save=True):
        order.append("reply")
        return ChatReply(project_id=project_id, intent="briefing", reply_markdown="X", report_id="r", report_url="u")

    monkeypatch.setattr(mod, "flush_project", fake_flush)
    monkeypatch.setattr(mod, "build_operational_reply", fake_reply)
    sent, ingested, send, updater = _spies()
    handled = await mod.maybe_handle_operational(
        CHAT_ID, 1, "Ann", "Genesi, fammi il punto", send, message_id="pf1", updater=updater
    )
    assert handled is True
    assert order == ["flush", "reply"]   # rebuild before reply, no ingest
    assert ingested == []                # invocation text NOT stored


@pytest.mark.asyncio
async def test_pure_briefing_invocation_not_ingested_as_event(env):
    from core.operational_memory.telegram_operational import maybe_handle_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_operational(CHAT_ID, 1, "Ann", "Genesi, fammi il punto", send, message_id="pb1", updater=updater)
    assert handled is True
    assert len(sent) == 1
    assert ingested == []   # pure query → not stored as operational event


@pytest.mark.asyncio
async def test_pure_remaining_open_invocation_not_ingested_as_question(env):
    from core.operational_memory import state_store
    from core.operational_memory.telegram_operational import maybe_handle_operational
    sent, ingested, send, updater = _spies()
    await maybe_handle_operational(CHAT_ID, 1, "Ann", "Genesi, cosa resta aperto?", send, message_id="pr1", updater=updater)
    assert ingested == []   # the query itself is not ingested
    state = await state_store.load_state(PROJECT)
    # no new open_question created just for the invocation phrase
    assert all("resta aperto" not in q.text.lower() for q in state.open_questions)


@pytest.mark.asyncio
async def test_pure_active_decisions_invocation_not_ingested_as_question(env):
    from core.operational_memory import state_store
    from core.operational_memory.telegram_operational import maybe_handle_operational
    sent, ingested, send, updater = _spies()
    await maybe_handle_operational(CHAT_ID, 1, "Ann", "Genesi, quali decisioni sono attive?", send, message_id="pa1", updater=updater)
    assert ingested == []
    state = await state_store.load_state(PROJECT)
    assert all("decisioni sono attive" not in q.text.lower() for q in state.open_questions)


@pytest.mark.asyncio
async def test_update_invocation_is_ingested(env):
    from core.operational_memory.telegram_operational import maybe_handle_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_operational(
        CHAT_ID, 1, "Ann", "Genesi, segna che il materiale è confermato", send, message_id="up1", updater=updater
    )
    assert handled is True
    assert ingested == ["up1"]   # carries a real update → ingested


@pytest.mark.asyncio
async def test_silent_non_invocation_still_ingested(env):
    from core.operational_memory.telegram_operational import maybe_handle_operational
    sent, ingested, send, updater = _spies()
    handled = await maybe_handle_operational(CHAT_ID, 1, "Ann", "ragazzi domani portiamo i pezzi", send, message_id="si1", updater=updater)
    await asyncio.sleep(0)
    assert handled is False
    assert sent == []
    assert ingested == ["si1"]   # normal message still silently ingested


def test_no_domain_hardcoding_for_invocation_filter():
    import re
    import core.operational_memory.query_engine as mod
    body = open(mod.__file__, "r", encoding="utf-8").read().lower()
    for token in ["test tab", "-5408248562", "corridoio", "pane", "quadro elettrico", "tab cefla", "cantiere"]:
        assert not re.search(rf"\b{re.escape(token)}\b", body), f"hardcoded token: {token}"


@pytest.mark.asyncio
async def test_telegram_ux_unchanged(env):
    # parse_mode HTML, inline report button and focus links survive the fix.
    from core.operational_memory.telegram_operational import maybe_handle_operational
    sent, ingested, send, updater = _spies()
    await maybe_handle_operational(CHAT_ID, 1, "Ann", "Genesi, fammi il punto", send, message_id="ux1", updater=updater)
    chat_id, text, reply_markup, parse_mode = sent[0]
    assert parse_mode == "HTML"
    assert reply_markup is not None
    assert "focus=" in text


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


# =========================================================================== #
# T3.1 — Telegram media → operational memory (shared media/OCR core)
# =========================================================================== #

from unittest.mock import AsyncMock


def _capture():
    msgs = []

    async def updater(message):
        msgs.append(message)

    return msgs, updater


def _png_no_ext(tmp_path, name="tg_blob", text="DELIVERY DONE"):
    from PIL import Image, ImageDraw
    f = tmp_path / name
    img = Image.new("RGB", (500, 160), "white")
    ImageDraw.Draw(img).text((20, 70), text, fill="black")
    img.save(f, format="PNG")   # real PNG bytes, NO extension (like a downloaded file)
    return f


@pytest.mark.asyncio
async def test_telegram_mapped_image_media_ingested_as_image(env, tmp_path):
    from core.operational_memory.telegram_operational import maybe_handle_operational
    from core.operational_memory.chat_presence import _event_from_message
    f = _png_no_ext(tmp_path)
    msgs, updater = _capture()
    sent = []

    async def send(*a, **k):
        sent.append(a)

    handled = await maybe_handle_operational(
        CHAT_ID, 1, "Ann", "", send, message_id="m1",
        media_type="image", media_path=str(f), updater=updater)
    await asyncio.sleep(0)
    assert handled is False and sent == []        # not invoked → silent, no reply
    att = msgs[0].attachments[0]
    assert att.type == "image"                     # OCR path (hint), not unknown
    assert _event_from_message(msgs[0]).type == "image"


@pytest.mark.asyncio
async def test_telegram_unmapped_media_no_analyzer(env):
    from core.operational_memory.telegram_operational import maybe_handle_operational
    msgs, updater = _capture()
    handled = await maybe_handle_operational(
        -999, 1, "Ann", "", AsyncMock(), message_id="m2",
        media_type="image", media_path="/tmp/whatever", updater=updater)
    await asyncio.sleep(0)
    assert handled is False and msgs == []         # unmapped → no operational ingest


@pytest.mark.asyncio
async def test_telegram_media_download_failed_text_only(env):
    from core.operational_memory.telegram_operational import maybe_handle_operational
    msgs, updater = _capture()
    handled = await maybe_handle_operational(
        CHAT_ID, 1, "Ann", "verifica documento", AsyncMock(), message_id="m3",
        media_type="image", media_path="", updater=updater)   # empty path = download failed
    await asyncio.sleep(0)
    assert handled is False
    assert msgs[0].attachments == []               # text-only, no crash
    assert msgs[0].text == "verifica documento"


@pytest.mark.asyncio
async def test_telegram_media_path_traversal_rejected(env):
    from core.operational_memory.telegram_operational import maybe_handle_operational
    msgs, updater = _capture()
    await maybe_handle_operational(
        CHAT_ID, 1, "Ann", "", AsyncMock(), message_id="m4",
        media_type="image", media_path="/tmp/genesi-telegram-media/../../etc/passwd", updater=updater)
    await asyncio.sleep(0)
    assert msgs[0].attachments[0].metadata["extraction_status"] == "rejected_path"


@pytest.mark.asyncio
async def test_telegram_media_ocr_failure_no_crash(env, tmp_path, monkeypatch):
    monkeypatch.setattr("core.operational_memory.media_processor.analyze_media",
                        lambda p, h="": (_ for _ in ()).throw(RuntimeError("ocr boom")))
    f = _png_no_ext(tmp_path)
    from core.operational_memory.telegram_operational import maybe_handle_operational
    msgs, updater = _capture()
    await maybe_handle_operational(
        CHAT_ID, 1, "Ann", "", AsyncMock(), message_id="m5",
        media_type="image", media_path=str(f), updater=updater)
    await asyncio.sleep(0)
    assert msgs[0].attachments[0].metadata["extraction_status"] == "analysis_error"


@pytest.mark.asyncio
async def test_telegram_pure_invocation_with_media_not_ingested(env, tmp_path, monkeypatch):
    import core.operational_memory.telegram_operational as mod

    async def fake_flush(project_id, rebuild=True):
        return None

    async def fake_reply(project_id, query, report_base_url="", invoked_by="", save=True):
        from core.operational_memory.models import ChatReply
        return ChatReply(project_id=project_id, intent="remaining_open", reply_markdown="X", report_id="", report_url="")

    monkeypatch.setattr(mod, "flush_project", fake_flush)
    monkeypatch.setattr(mod, "build_operational_reply", fake_reply)
    f = _png_no_ext(tmp_path)
    msgs, updater = _capture()
    sent = []

    async def send(*a, **k):
        sent.append(a)

    handled = await mod.maybe_handle_operational(
        CHAT_ID, 1, "Ann", "Genesi, cosa resta aperto?", send, message_id="m6",
        media_type="image", media_path=str(f), updater=updater)
    await asyncio.sleep(0)
    assert handled is True            # invoked + reply enabled → answered
    assert msgs == []                 # pure invocation NOT ingested (even with media)


def test_no_hardcoding_telegram_media():
    import re
    import core.operational_memory.telegram_operational as mod
    body = open(mod.__file__, "r", encoding="utf-8").read().lower()
    for token in ["test tab", "tab cefla", "cantiere", "corridoio", "pane", "quadro elettrico", "-1001234567890", "120363"]:
        assert not re.search(rf"{re.escape(token)}", body), f"hardcoded: {token}"
