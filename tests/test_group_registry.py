import json


def _configure_registry_paths(tmp_path, monkeypatch):
    from core import group_controls, group_registry

    controls_path = tmp_path / "admin" / "group_controls.json"
    titles = tmp_path / "group_title"
    jids = tmp_path / "wa_group_jid"
    rosters = tmp_path / "group_roster"
    titles.mkdir(parents=True)
    jids.mkdir(parents=True)
    rosters.mkdir(parents=True)

    monkeypatch.setattr(group_controls, "GROUP_CONTROLS_PATH", controls_path)
    monkeypatch.setattr(group_controls, "_GROUP_TITLE_DIR", titles)
    monkeypatch.setattr(group_controls, "_WA_GROUP_JID_DIR", jids)
    monkeypatch.setattr(group_registry, "_GROUP_ROSTER_DIR", rosters)
    return group_controls, group_registry, controls_path, titles, jids, rosters


def test_group_registry_aggregates_whatsapp_and_telegram_read_only(tmp_path, monkeypatch):
    group_controls, group_registry, controls_path, titles, jids, rosters = _configure_registry_paths(
        tmp_path, monkeypatch
    )
    controls = {
        "whatsapp_reply_enabled_groups": {
            "120363407869433239@g.us": {
                "enabled": True,
                "label": "Prova Genesi",
                "updated_at": "2026-06-27T21:37:46+00:00",
                "observed_at": "2026-06-27T20:00:00+00:00",
            },
            "120363404290146040@g.us": {
                "enabled": False,
                "label": "TAB CEFLA",
                "updated_at": "",
                "observed_at": "",
            },
        },
        "telegram_reply_enabled_groups": {
            "-5007188402": {
                "enabled": True,
                "label": "Alfio and Alfio",
                "updated_at": "2026-06-28T09:10:10+00:00",
                "observed_at": "",
            }
        },
    }
    controls_path.parent.mkdir(parents=True, exist_ok=True)
    controls_path.write_text(json.dumps(controls, ensure_ascii=False, indent=2), encoding="utf-8")
    titles.joinpath("272555882.json").write_text(json.dumps("Prova Genesi"), encoding="utf-8")
    jids.joinpath("272555882.json").write_text(json.dumps("120363407869433239@g.us"), encoding="utf-8")
    titles.joinpath("-5007188402.json").write_text(json.dumps("Alfio and Alfio"), encoding="utf-8")
    rosters.joinpath("-600.json").write_text(json.dumps({"members": []}), encoding="utf-8")
    monkeypatch.setenv("WHATSAPP_CHAT_PROJECT_MAP", json.dumps({"120363407869433239@g.us": "wa-project"}))
    monkeypatch.setenv("TELEGRAM_CHAT_PROJECT_MAP", json.dumps({"-5007188402": "tg-project"}))

    before = controls_path.read_text(encoding="utf-8")
    groups = group_registry.list_groups()
    after = controls_path.read_text(encoding="utf-8")

    assert after == before
    by_key = {(g["platform"], g["group_id"]): g for g in groups}

    wa = by_key[("whatsapp", "120363407869433239@g.us")]
    assert wa["title"] == "Prova Genesi"
    assert wa["reply_enabled"] is True
    assert wa["observed_at"] == "2026-06-27T20:00:00+00:00"
    assert wa["project_id"] == "wa-project"
    assert wa["jid"] == "120363407869433239@g.us"
    assert wa["group_hash"] == "272555882"
    assert set(wa["sources"]) == {"group_title", "wa_group_jid"}

    tg = by_key[("telegram", "-5007188402")]
    assert tg["title"] == "Alfio and Alfio"
    assert tg["reply_enabled"] is True
    assert tg["project_id"] == "tg-project"
    assert tg["chat_id"] == "-5007188402"

    controls_only = by_key[("whatsapp", "120363404290146040@g.us")]
    assert controls_only["title"] == "TAB CEFLA"
    assert controls_only["reply_enabled"] is False
    assert controls_only["sources"] == ["group_controls"]

    roster_only = by_key[("telegram", "-600")]
    assert roster_only["title"] is None
    assert roster_only["reply_enabled"] is False
    assert roster_only["sources"] == ["group_roster"]


def test_group_registry_snapshot_splits_platforms(tmp_path, monkeypatch):
    _, group_registry, controls_path, titles, jids, _ = _configure_registry_paths(tmp_path, monkeypatch)
    controls_path.parent.mkdir(parents=True, exist_ok=True)
    controls_path.write_text(json.dumps({}), encoding="utf-8")
    titles.joinpath("272555882.json").write_text(json.dumps("Prova Genesi"), encoding="utf-8")
    jids.joinpath("272555882.json").write_text(json.dumps("120363407869433239@g.us"), encoding="utf-8")
    titles.joinpath("-5007188402.json").write_text(json.dumps("Alfio and Alfio"), encoding="utf-8")

    snap = group_registry.snapshot()

    assert len(snap["groups"]) == 2
    assert [g["platform"] for g in snap["known_groups"]["whatsapp"]] == ["whatsapp"]
    assert [g["platform"] for g in snap["known_groups"]["telegram"]] == ["telegram"]
    assert snap["known_groups"]["whatsapp"][0]["reply_enabled"] is False
    assert snap["known_groups"]["telegram"][0]["reply_enabled"] is False
