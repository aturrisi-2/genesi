from core.config_health import config_health_snapshot


def test_config_health_exposes_only_status_without_values():
    env = {
        "JWT_SECRET": "super-secret-value",
        "ADMIN_EMAILS": "one@example.com,two@example.com",
        "OPENAI_API_KEY": "sk-secret",
        "TELEGRAM_BOT_TOKEN": "123:secret",
        "TELEGRAM_CHAT_PROJECT_MAP": '{"-1":"sensitive-map-value"}',
        "WHATSAPP_CHAT_PROJECT_MAP": '{"120@g.us":"sensitive-map-value"}',
        "BAILEYS_SEND_URL": "http://localhost:3001/send",
        "BAILEYS_SEND_SECRET": "bridge-secret",
        "PUBLIC_BASE_URL": "https://example.test",
    }

    snapshot = config_health_snapshot(env)
    rendered = repr(snapshot)

    assert snapshot["auth"]["jwt_secret_configured"] is True
    assert snapshot["auth"]["admin_email_count"] == 2
    assert snapshot["llm"]["openai_api_key_present"] is True
    assert snapshot["telegram"]["bot_token_present"] is True
    assert snapshot["telegram"]["chat_project_map"]["valid_json_object"] is True
    assert snapshot["whatsapp"]["chat_project_map"]["valid_json_object"] is True
    assert snapshot["whatsapp"]["baileys_send_secret_present"] is True
    for secret_fragment in (
        "super-secret-value",
        "sk-secret",
        "123:secret",
        "bridge-secret",
        "one@example.com",
        "sensitive-map-value",
    ):
        assert secret_fragment not in rendered


def test_config_health_flags_default_jwt_and_invalid_maps():
    snapshot = config_health_snapshot({
        "JWT_SECRET": "dev_secret_key_for_testing_only_32b",
        "ADMIN_EMAILS": "",
        "TELEGRAM_CHAT_PROJECT_MAP": "not-json",
        "WHATSAPP_CHAT_PROJECT_MAP": "[]",
    })

    assert snapshot["auth"]["jwt_secret_configured"] is False
    assert snapshot["auth"]["admin_emails_configured"] is False
    assert snapshot["telegram"]["chat_project_map"] == {
        "present": True,
        "valid_json_object": False,
    }
    assert snapshot["whatsapp"]["chat_project_map"] == {
        "present": True,
        "valid_json_object": False,
    }


def test_config_health_missing_values_are_false():
    snapshot = config_health_snapshot({})

    assert snapshot["auth"]["jwt_secret_configured"] is False
    assert snapshot["auth"]["admin_email_count"] == 0
    assert snapshot["llm"]["openai_api_key_present"] is False
    assert snapshot["telegram"]["bot_token_present"] is False
    assert snapshot["telegram"]["chat_project_map"]["present"] is False
    assert snapshot["whatsapp"]["chat_project_map"]["present"] is False
    assert snapshot["runtime"]["public_base_url_present"] is False
