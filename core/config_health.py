"""Read-only configuration health checks.

The snapshot intentionally exposes only booleans/status flags, never raw secret
or token values. It is safe to call from tests or future admin-only endpoints.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from typing import Any

_JWT_DEFAULT = "dev_secret_key_for_testing_only_32b"


def _present(env: Mapping[str, str], name: str) -> bool:
    return bool(str(env.get(name, "")).strip())


def _json_object_status(env: Mapping[str, str], name: str) -> dict[str, bool]:
    raw = str(env.get(name, "")).strip()
    if not raw:
        return {"present": False, "valid_json_object": False}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {"present": True, "valid_json_object": False}
    return {"present": True, "valid_json_object": isinstance(data, dict)}


def config_health_snapshot(env: Mapping[str, str] | None = None) -> dict[str, Any]:
    source = env if env is not None else os.environ
    jwt_secret = str(source.get("JWT_SECRET", "")).strip()
    admin_emails = [
        item.strip()
        for item in str(source.get("ADMIN_EMAILS", "")).split(",")
        if item.strip()
    ]
    return {
        "auth": {
            "jwt_secret_configured": bool(jwt_secret and jwt_secret != _JWT_DEFAULT),
            "admin_emails_configured": bool(admin_emails),
            "admin_email_count": len(admin_emails),
        },
        "llm": {
            "openai_api_key_present": _present(source, "OPENAI_API_KEY"),
        },
        "telegram": {
            "bot_token_present": _present(source, "TELEGRAM_BOT_TOKEN"),
            "chat_project_map": _json_object_status(source, "TELEGRAM_CHAT_PROJECT_MAP"),
        },
        "whatsapp": {
            "chat_project_map": _json_object_status(source, "WHATSAPP_CHAT_PROJECT_MAP"),
            "baileys_send_url_present": _present(source, "BAILEYS_SEND_URL"),
            "baileys_send_secret_present": _present(source, "BAILEYS_SEND_SECRET"),
        },
        "runtime": {
            "public_base_url_present": _present(source, "PUBLIC_BASE_URL"),
        },
    }
