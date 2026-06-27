import asyncio
import inspect
from pathlib import Path

import pytest

from core.group_reactivity import (
    _EMOTIONAL_COOLDOWNS,
    clear_group_emotional_cooldown,
    detect_autonomous_group_trigger,
    should_allow_autonomous_group_intervention,
)


def setup_function():
    _EMOTIONAL_COOLDOWNS.clear()


class TestAutonomousGroupTriggerDetection:
    def test_auguri_compleanno_allowed(self):
        assert detect_autonomous_group_trigger("Tantissimi auguri Elena, buon compleanno!")["topic"] == "positive_social"

    def test_congratulations_celebration_allowed(self):
        assert detect_autonomous_group_trigger("Bravissima, finalmente libera!")["topic"] == "positive_social"
        assert detect_autonomous_group_trigger("Mi sono tolta finalmente questo peso")["topic"] == "positive_social"

    def test_grief_delicate_allowed(self):
        assert detect_autonomous_group_trigger("Siamo in lutto, è venuta a mancare stanotte")["topic"] == "delicate_support"

    def test_strong_support_need_allowed(self):
        assert detect_autonomous_group_trigger("Mi sento a pezzi, ho bisogno di supporto")["topic"] == "delicate_support"

    def test_normal_message_silent(self):
        assert detect_autonomous_group_trigger("Ragazzi ci vediamo alle otto per cena") is None

    def test_generic_emoji_only_silent(self):
        assert detect_autonomous_group_trigger("❤️❤️❤️🥰🥰") is None

    def test_generic_media_without_text_silent(self):
        assert detect_autonomous_group_trigger("", has_media=True) is None


class TestAutonomousGroupCooldown:
    def test_positive_cooldown_blocks_repeated_auguri(self):
        assert should_allow_autonomous_group_intervention("telegram", -1, "Tantissimi auguri!") is True
        assert should_allow_autonomous_group_intervention("telegram", -1, "Auguroni buon compleanno!") is False

    def test_delicate_cooldown_blocks_repeated_support_loop(self):
        assert should_allow_autonomous_group_intervention("whatsapp", 10, "È venuta a mancare ieri") is True
        assert should_allow_autonomous_group_intervention("whatsapp", 10, "Siamo in lutto, dolore immenso") is False

    def test_platform_and_group_cooldowns_are_isolated(self):
        assert should_allow_autonomous_group_intervention("telegram", 10, "Tantissimi auguri!") is True
        assert should_allow_autonomous_group_intervention("whatsapp", 10, "Tantissimi auguri!") is True
        assert should_allow_autonomous_group_intervention("telegram", 11, "Tantissimi auguri!") is True

    def test_clearing_cooldown_allows_next_event(self):
        assert should_allow_autonomous_group_intervention("telegram", 20, "Tantissimi auguri!") is True
        clear_group_emotional_cooldown("telegram", 20)
        assert should_allow_autonomous_group_intervention("telegram", 20, "Congratulazioni!") is True


def test_telegram_gate_allows_explicit_invocation():
    import core.telegram_bot as tg

    assert asyncio.run(tg._group_should_intervene(
        "Genesi mi aiuti?", "", -100, 1, "Ada", bot_mentioned=True
    )) is True


def test_telegram_gate_allows_autonomous_positive_before_passive_barrier():
    import core.telegram_bot as tg

    assert asyncio.run(tg._group_should_intervene(
        "Tantissimi auguri Elena!", "", -101, 1, "Ada"
    )) is True


def test_telegram_gate_blocks_generic_media_without_invocation():
    import core.telegram_bot as tg

    assert asyncio.run(tg._group_should_intervene(
        "", "", -102, 1, "Ada", has_media=True
    )) is False


def test_whatsapp_gate_allows_explicit_invocation():
    import core.whatsapp_bot as wa

    assert asyncio.run(wa._group_should_intervene(
        "Genesi mi aiuti?", "", 100, "u1", "Ada", bot_mentioned=True
    )) is True


def test_whatsapp_gate_allows_autonomous_positive_before_passive_barrier():
    import core.whatsapp_bot as wa

    assert asyncio.run(wa._group_should_intervene(
        "Tantissimi auguri Elena!", "", 101, "u1", "Ada"
    )) is True


def test_whatsapp_gate_blocks_generic_media_without_invocation():
    import core.whatsapp_bot as wa

    assert asyncio.run(wa._group_should_intervene(
        "", "", 102, "u1", "Ada", has_media=True
    )) is False


def test_reply_to_genesi_is_allowed_by_upstream_contract():
    import core.telegram_bot as tg
    import core.whatsapp_bot as wa

    tg_src = inspect.getsource(tg.handle_update)
    wa_src = inspect.getsource(wa._process_message)
    assert "if _reply_to_genesi:" in tg_src
    assert "should = True" in tg_src
    assert "if _reply_to_genesi:" in wa_src
    assert "should = True" in wa_src


async def _fake_group_should_respond_llm(*a, **k):
    return '{"intervieni": false, "motivo": "legacy"}'


@pytest.mark.asyncio
async def test_baileys_should_respond_allows_whatsapp_auguri(monkeypatch):
    import api.chat as apichat
    import core.llm_service as llm

    monkeypatch.setattr(llm.llm_service, "_call_model", _fake_group_should_respond_llm)
    req = apichat.ShouldRespondRequest(
        text="Tantissimi auguri Elena, buon compleanno!",
        group_id="120363407869433239@g.us",
        sender_name="Ada",
    )

    resp = await apichat.group_should_respond(req, user=None)

    assert resp.intervieni is True
    assert resp.motivo == "autonomous_positive_social"


@pytest.mark.asyncio
async def test_baileys_should_respond_allows_whatsapp_delicate(monkeypatch):
    import api.chat as apichat
    import core.llm_service as llm

    monkeypatch.setattr(llm.llm_service, "_call_model", _fake_group_should_respond_llm)
    req = apichat.ShouldRespondRequest(
        text="Oggi sono molto giù, mi sento a pezzi e ho bisogno di supporto.",
        group_id="120363407869433240@g.us",
        sender_name="Ada",
    )

    resp = await apichat.group_should_respond(req, user=None)

    assert resp.intervieni is True
    assert resp.motivo == "autonomous_delicate_support"


@pytest.mark.asyncio
async def test_baileys_should_respond_keeps_normal_message_silent(monkeypatch):
    import api.chat as apichat
    import core.llm_service as llm

    monkeypatch.setattr(llm.llm_service, "_call_model", _fake_group_should_respond_llm)
    req = apichat.ShouldRespondRequest(
        text="Sto facendo una prova, vediamo se il gruppo resta normale.",
        group_id="120363407869433241@g.us",
        sender_name="Ada",
    )

    resp = await apichat.group_should_respond(req, user=None)

    assert resp.intervieni is False
    assert resp.motivo == "legacy"


@pytest.mark.asyncio
async def test_baileys_should_respond_keeps_emoji_only_silent(monkeypatch):
    import api.chat as apichat
    import core.llm_service as llm

    monkeypatch.setattr(llm.llm_service, "_call_model", _fake_group_should_respond_llm)
    req = apichat.ShouldRespondRequest(
        text="❤️❤️❤️🥳🥳🥳",
        group_id="120363407869433242@g.us",
        sender_name="Ada",
    )

    resp = await apichat.group_should_respond(req, user=None)

    assert resp.intervieni is False
    assert resp.motivo == "legacy"


def test_group_controls_whatsapp_reply_toggle(tmp_path, monkeypatch):
    from core import group_controls

    controls_path = tmp_path / "admin" / "group_controls.json"
    titles = tmp_path / "group_title"
    jids = tmp_path / "wa_group_jid"
    titles.mkdir()
    jids.mkdir()
    (titles / "272555882.json").write_text('"Prova Genesi"', encoding="utf-8")
    (jids / "272555882.json").write_text('"120363407869433239@g.us"', encoding="utf-8")

    monkeypatch.setattr(group_controls, "GROUP_CONTROLS_PATH", controls_path)
    monkeypatch.setattr(group_controls, "_GROUP_TITLE_DIR", titles)
    monkeypatch.setattr(group_controls, "_WA_GROUP_JID_DIR", jids)

    assert group_controls.is_whatsapp_reply_enabled_by_admin("120363407869433239@g.us") is False
    group_controls.set_whatsapp_reply_enabled("120363407869433239@g.us", True, label="Prova Genesi")
    assert group_controls.is_whatsapp_reply_enabled_by_admin("120363407869433239@g.us") is True

    snap = group_controls.snapshot()
    assert snap["known_whatsapp_groups"][0]["title"] == "Prova Genesi"
    assert snap["known_whatsapp_groups"][0]["admin_reply_enabled"] is True


@pytest.mark.asyncio
async def test_admin_group_controls_endpoint_toggle(tmp_path, monkeypatch):
    from api.admin import automation
    from core import group_controls

    controls_path = tmp_path / "admin" / "group_controls.json"
    titles = tmp_path / "group_title"
    jids = tmp_path / "wa_group_jid"
    titles.mkdir()
    jids.mkdir()
    (titles / "272555882.json").write_text('"Prova Genesi"', encoding="utf-8")
    (jids / "272555882.json").write_text('"120363407869433239@g.us"', encoding="utf-8")

    monkeypatch.setattr(group_controls, "GROUP_CONTROLS_PATH", controls_path)
    monkeypatch.setattr(group_controls, "_GROUP_TITLE_DIR", titles)
    monkeypatch.setattr(group_controls, "_WA_GROUP_JID_DIR", jids)

    payload = automation.WhatsAppGroupReplyPayload(
        jid="120363407869433239@g.us",
        enabled=True,
        label="Prova Genesi",
    )
    snap = await automation.automation_group_controls_whatsapp_reply(payload, None)

    assert snap["known_whatsapp_groups"][0]["admin_reply_enabled"] is True
    assert group_controls.is_whatsapp_reply_enabled_by_admin("120363407869433239@g.us") is True


def _baileys_source() -> str:
    return Path("/opt/genesi/baileys-service/index.js").read_text(encoding="utf-8")


def test_baileys_engaged_is_not_total_bypass():
    src = _baileys_source()

    assert "ENGAGED_IGNORED_NOT_DIRECTED" in src
    assert "ENGAGED_FOLLOWUP_ALLOWED" in src
    assert "isClearlyDirectedFollowup(text)" in src
    assert "shouldRespondDecision(text, recentMsgs, token, groupId, senderName)" in src
    assert "Conversazione attiva con" not in src


def test_baileys_blocks_emoji_only_and_generic_media_before_backend():
    src = _baileys_source()

    assert "isEmojiOnlyMessage(originalText || text)" in src
    assert "reason=emoji_only" in src
    assert "genericMediaWithoutCaption" in src
    assert "reason=generic_media_without_caption" in src
    assert "bypasso filtro e intervengo" not in src


def test_baileys_autonomous_triggers_still_pass_through_should_respond():
    src = _baileys_source()

    assert "/api/chat/group/should_respond" in src
    assert "motivo: res.data.motivo" in src
    assert "motivo=${interventionReason}" in src
    assert "autonomous_positive_social" not in src  # reason comes from backend, not hardcoded bridge cases


def test_whatsapp_group_response_uses_prompt_leak_filter():
    import api.chat as apichat

    src = inspect.getsource(apichat.group_chat_endpoint)

    assert "filter_response(response or \"\"" in src
    assert "WA_GROUP_RESPONSE_FILTERED" in src


def test_prompt_leak_filter_removes_raw_internal_markers():
    from core.response_filter import filter_response

    raw = (
        "Sistema: devi rispondere come Genesi.\n"
        "[CONTESTO FAMIGLIA: testo interno]\n"
        "Genesi: Ti sono vicino con discrezione."
    )

    cleaned = filter_response(raw, "whatsapp_group:test")

    assert "Sistema:" not in cleaned
    assert "devi rispondere" not in cleaned.lower()
    assert "CONTESTO FAMIGLIA" not in cleaned
