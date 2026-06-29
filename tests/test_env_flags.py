from core.env_flags import env_flag


def test_env_flag_uses_default_when_missing(monkeypatch):
    monkeypatch.delenv("GENESI_TEST_FLAG", raising=False)

    assert env_flag("GENESI_TEST_FLAG") is False
    assert env_flag("GENESI_TEST_FLAG", default=True) is True


def test_env_flag_accepts_known_true_values(monkeypatch):
    for value in ("1", "true", "TRUE", "yes", "on", " On "):
        monkeypatch.setenv("GENESI_TEST_FLAG", value)
        assert env_flag("GENESI_TEST_FLAG") is True


def test_env_flag_rejects_other_values(monkeypatch):
    for value in ("", "0", "false", "no", "off", "anything"):
        monkeypatch.setenv("GENESI_TEST_FLAG", value)
        assert env_flag("GENESI_TEST_FLAG", default=True) is False
