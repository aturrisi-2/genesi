import json
from pathlib import Path

import pytest


def _configure_group_control_paths(tmp_path, monkeypatch):
    from core import group_controls

    controls_path = tmp_path / "admin" / "group_controls.json"
    titles = tmp_path / "group_title"
    jids = tmp_path / "wa_group_jid"
    titles.mkdir(parents=True)
    jids.mkdir(parents=True)

    monkeypatch.setattr(group_controls, "GROUP_CONTROLS_PATH", controls_path)
    monkeypatch.setattr(group_controls, "_GROUP_TITLE_DIR", titles)
    monkeypatch.setattr(group_controls, "_WA_GROUP_JID_DIR", jids)
    return group_controls, controls_path, titles, jids


def test_group_controls_whatsapp_backward_compatibility(tmp_path, monkeypatch):
    group_controls, controls_path, titles, jids = _configure_group_control_paths(tmp_path, monkeypatch)
    titles.joinpath("272555882.json").write_text(json.dumps("Prova Genesi"), encoding="utf-8")
    jids.joinpath("272555882.json").write_text(json.dumps("120363407869433239@g.us"), encoding="utf-8")

    assert group_controls.is_whatsapp_reply_enabled_by_admin("120363407869433239@g.us") is False
    assert group_controls.is_group_reply_enabled("whatsapp", "120363407869433239@g.us") is False

    group_controls.set_whatsapp_reply_enabled("120363407869433239@g.us", True, label="Prova Genesi")

    saved = json.loads(controls_path.read_text(encoding="utf-8"))
    assert saved["whatsapp_reply_enabled_groups"]["120363407869433239@g.us"]["enabled"] is True
    assert group_controls.is_whatsapp_reply_enabled_by_admin("120363407869433239@g.us") is True

    snap = group_controls.snapshot()
    assert snap["known_whatsapp_groups"][0]["title"] == "Prova Genesi"
    assert snap["known_whatsapp_groups"][0]["admin_reply_enabled"] is True
    assert snap["known_groups"]["whatsapp"][0]["platform"] == "whatsapp"


def test_group_controls_defaults_unknown_groups_off(tmp_path, monkeypatch):
    group_controls, *_ = _configure_group_control_paths(tmp_path, monkeypatch)

    assert group_controls.is_group_reply_enabled("whatsapp", "120363407869433239@g.us") is False
    assert group_controls.is_group_reply_enabled("telegram", "-5007188402") is False


def test_group_controls_telegram_toggle_persists_and_appears_in_snapshot(tmp_path, monkeypatch):
    group_controls, controls_path, titles, _ = _configure_group_control_paths(tmp_path, monkeypatch)
    titles.joinpath("-5007188402.json").write_text(json.dumps("Alfio and Alfio"), encoding="utf-8")

    assert group_controls.is_group_reply_enabled("telegram", "-5007188402") is False
    group_controls.set_group_reply_enabled("telegram", "-5007188402", True, title="Alfio and Alfio")

    saved = json.loads(controls_path.read_text(encoding="utf-8"))
    assert saved["telegram_reply_enabled_groups"]["-5007188402"]["enabled"] is True
    assert group_controls.is_group_reply_enabled("telegram", -5007188402) is True

    snap = group_controls.snapshot()
    assert snap["known_telegram_groups"][0]["title"] == "Alfio and Alfio"
    assert snap["known_telegram_groups"][0]["admin_reply_enabled"] is True
    assert snap["known_telegram_groups"][0]["ingest_enabled"] is True
    assert snap["known_groups"]["telegram"][0]["platform"] == "telegram"


def test_group_controls_project_id_is_read_only_metadata(tmp_path, monkeypatch):
    group_controls, _, titles, jids = _configure_group_control_paths(tmp_path, monkeypatch)
    titles.joinpath("-5007188402.json").write_text(json.dumps("Alfio and Alfio"), encoding="utf-8")
    titles.joinpath("272555882.json").write_text(json.dumps("Prova Genesi"), encoding="utf-8")
    jids.joinpath("272555882.json").write_text(json.dumps("120363407869433239@g.us"), encoding="utf-8")
    monkeypatch.setenv("TELEGRAM_CHAT_PROJECT_MAP", json.dumps({"-5007188402": "tg-project"}))
    monkeypatch.setenv("WHATSAPP_CHAT_PROJECT_MAP", json.dumps({"120363407869433239@g.us": "wa-project"}))

    snap = group_controls.snapshot()

    assert snap["known_telegram_groups"][0]["project_id"] == "tg-project"
    assert snap["known_whatsapp_groups"][0]["project_id"] == "wa-project"


@pytest.mark.asyncio
async def test_admin_group_controls_platform_aware_endpoint(tmp_path, monkeypatch):
    from api.admin import automation

    group_controls, _, titles, _ = _configure_group_control_paths(tmp_path, monkeypatch)
    titles.joinpath("-5007188402.json").write_text(json.dumps("Alfio and Alfio"), encoding="utf-8")

    payload = automation.GroupReplyPayload(
        platform="telegram",
        group_id="-5007188402",
        enabled=True,
        title="Alfio and Alfio",
    )
    snap = await automation.automation_group_controls_reply(payload, None)

    assert group_controls.is_group_reply_enabled("telegram", "-5007188402") is True
    assert snap["known_telegram_groups"][0]["admin_reply_enabled"] is True


@pytest.mark.asyncio
async def test_admin_group_controls_whatsapp_endpoint_stays_compatible(tmp_path, monkeypatch):
    from api.admin import automation
    from core import group_controls

    _, _, titles, jids = _configure_group_control_paths(tmp_path, monkeypatch)
    titles.joinpath("272555882.json").write_text(json.dumps("Prova Genesi"), encoding="utf-8")
    jids.joinpath("272555882.json").write_text(json.dumps("120363407869433239@g.us"), encoding="utf-8")

    payload = automation.WhatsAppGroupReplyPayload(
        jid="120363407869433239@g.us",
        enabled=True,
        label="Prova Genesi",
    )
    snap = await automation.automation_group_controls_whatsapp_reply(payload, None)

    assert group_controls.is_whatsapp_reply_enabled_by_admin("120363407869433239@g.us") is True
    assert snap["known_whatsapp_groups"][0]["admin_reply_enabled"] is True


def test_telegram_admin_reply_gate_blocks_and_allows(tmp_path, monkeypatch):
    group_controls, _, _, _ = _configure_group_control_paths(tmp_path, monkeypatch)
    import core.telegram_bot as telegram_bot

    assert telegram_bot._telegram_group_reply_allowed_by_admin(-5007188402) is False

    group_controls.set_group_reply_enabled("telegram", "-5007188402", True, title="Alfio and Alfio")

    assert telegram_bot._telegram_group_reply_allowed_by_admin(-5007188402) is True


def test_admin_html_contains_unified_group_controls():
    html = Path("static/admin.html").read_text(encoding="utf-8")

    assert "Gruppi e risposte" in html
    assert "WhatsApp" in html
    assert "Telegram" in html
    assert "group-controls/reply" in html
    assert "REPLY ADMIN ON" in html
    assert "REPLY ADMIN OFF" in html
