from core import automation_flags


def test_passive_mode_disables_proactive_flags_by_default(monkeypatch):
    monkeypatch.delenv("GENESI_PASSIVE_MODE", raising=False)
    monkeypatch.delenv("ENABLE_SOCIAL_AUTOPUBLISH", raising=False)
    monkeypatch.delenv("ENABLE_INSTAGRAM_POSTING", raising=False)
    monkeypatch.delenv("ENABLE_MOLTBOOK_AUTOPUBLISH", raising=False)

    assert automation_flags.passive_mode() is True
    assert automation_flags.flag_enabled("instagram_posting") is False
    assert automation_flags.flag_enabled("moltbook_autopublish") is False
    assert automation_flags.flag_enabled("reminders") is False


def test_proactive_flags_require_master_and_umbrella(monkeypatch):
    monkeypatch.setenv("GENESI_PASSIVE_MODE", "false")
    monkeypatch.setenv("ENABLE_SOCIAL_AUTOPUBLISH", "true")
    monkeypatch.setenv("ENABLE_INSTAGRAM_POSTING", "true")

    assert automation_flags.flag_enabled("instagram_posting") is True

    monkeypatch.setenv("ENABLE_SOCIAL_AUTOPUBLISH", "false")
    assert automation_flags.flag_enabled("instagram_posting") is False


def test_moltbook_aliases_are_accepted(monkeypatch):
    monkeypatch.setenv("GENESI_PASSIVE_MODE", "false")
    monkeypatch.setenv("ENABLE_SOCIAL_AUTOPUBLISH", "true")
    monkeypatch.delenv("ENABLE_MOLTBOOK_AUTOPUBLISH", raising=False)
    monkeypatch.delenv("ENABLE_MOLTBOK_AUTOPUBLISH", raising=False)
    monkeypatch.setenv("ENABLE_MULTBOOK_AUTOPUBLISH", "true")

    assert automation_flags.flag_enabled("moltbook_autopublish") is True


def test_on_request_meta_replies_ignore_passive_mode(monkeypatch):
    monkeypatch.setenv("GENESI_PASSIVE_MODE", "true")
    monkeypatch.delenv("ENABLE_META_DM_REPLIES", raising=False)

    assert automation_flags.flag_enabled("meta_dm_replies") is True

    monkeypatch.setenv("ENABLE_META_DM_REPLIES", "false")
    assert automation_flags.flag_enabled("meta_dm_replies") is False
