"""
AUTOMATION FLAGS - Genesi (FASE 0)
==================================

Interruttore centralizzato e reversibile per tutte le automazioni proattive.

Fail-safe:
  - GENESI_PASSIVE_MODE default True: spegne ogni automazione proattiva.
  - I flag proattivi sono OFF di default.
  - Gli override admin sono persistiti in memory/admin/automation_flags.json e
    hanno precedenza sulle variabili ambiente.
  - Le funzioni su richiesta restano indipendenti dal passive mode.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core.log import log

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}
_OVERRIDES_PATH = Path("memory/admin/automation_flags.json")


def _load_overrides() -> dict[str, bool]:
    try:
        if not _OVERRIDES_PATH.exists():
            return {}
        data = json.loads(_OVERRIDES_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        return {str(k): bool(v) for k, v in data.items() if isinstance(v, bool)}
    except Exception as e:
        log("AUTOMATION_FLAGS_OVERRIDES_LOAD_ERROR", error=str(e))
        return {}


def _save_overrides(overrides: dict[str, bool]) -> None:
    _OVERRIDES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OVERRIDES_PATH.write_text(
        json.dumps(overrides, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    v = raw.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    return default


def _configured_bool(name: str, default: bool, overrides: dict[str, bool] | None = None) -> bool:
    values = _load_overrides() if overrides is None else overrides
    if name in values:
        return values[name]
    return _env_bool(name, default)


def passive_mode() -> bool:
    """True (default) = modalita passiva: tutte le automazioni proattive OFF."""
    return _configured_bool("GENESI_PASSIVE_MODE", True)


_UMBRELLAS = {
    "proactive_messages": "ENABLE_PROACTIVE_MESSAGES",
    "social_autopublish": "ENABLE_SOCIAL_AUTOPUBLISH",
}

_FLAGS: dict[str, dict[str, Any]] = {
    "morning_greetings":        {"env": "ENABLE_MORNING_GREETINGS",        "default": False, "umbrellas": ["proactive_messages"]},
    "birthday_greetings":       {"env": "ENABLE_BIRTHDAY_GREETINGS",       "default": False, "umbrellas": ["proactive_messages"]},
    "group_interventions":      {"env": "ENABLE_GROUP_INTERVENTIONS",      "default": False, "umbrellas": ["proactive_messages"]},
    "group_auto_presentation":  {"env": "ENABLE_GROUP_AUTO_PRESENTATION",  "default": False, "umbrellas": ["proactive_messages"]},
    "group_greeting_replies":   {"env": "ENABLE_GROUP_GREETING_REPLIES",   "default": False, "umbrellas": ["proactive_messages"]},

    "instagram_posting":        {"env": "ENABLE_INSTAGRAM_POSTING",        "default": False, "umbrellas": ["social_autopublish"]},
    "instagram_reels":          {"env": "ENABLE_INSTAGRAM_REELS",          "default": False, "umbrellas": ["social_autopublish"]},
    "instagram_comment_replies":{"env": "ENABLE_INSTAGRAM_COMMENT_REPLIES","default": False, "umbrellas": ["social_autopublish"]},
    "facebook_automation":      {"env": "ENABLE_FACEBOOK_AUTOMATION",      "default": False, "umbrellas": ["social_autopublish"]},
    "moltbook_autopublish":     {"env": "ENABLE_MOLTBOOK_AUTOPUBLISH",     "default": False, "umbrellas": ["social_autopublish"],
                                 "aliases": ["ENABLE_MOLTBOK_AUTOPUBLISH", "ENABLE_MULTBOOK_AUTOPUBLISH"]},

    "training_autopilot":       {"env": "ENABLE_TRAINING_AUTOPILOT",       "default": False, "umbrellas": []},
    "improvement_health":       {"env": "ENABLE_IMPROVEMENT_HEALTH",       "default": False, "umbrellas": []},

    "reminders":                {"env": "ENABLE_REMINDERS",                "default": False, "umbrellas": []},
    "proactive_email":          {"env": "ENABLE_PROACTIVE_EMAIL",          "default": False, "umbrellas": ["proactive_messages"]},

    "calendar_check":           {"env": "ENABLE_CALENDAR_CHECK",           "default": True,  "umbrellas": [], "on_request": True},
    "meta_dm_replies":          {"env": "ENABLE_META_DM_REPLIES",          "default": True,  "umbrellas": [], "on_request": True},
}


def _raw_flag(spec: dict[str, Any], overrides: dict[str, bool] | None = None) -> bool:
    if _configured_bool(spec["env"], spec["default"], overrides):
        return True
    for alias in spec.get("aliases", []):
        if _configured_bool(alias, False, overrides):
            return True
    return False


def flag_enabled(name: str, overrides: dict[str, bool] | None = None) -> bool:
    spec = _FLAGS.get(name)
    if spec is None:
        log("AUTOMATION_FLAG_UNKNOWN", flag=name)
        return False

    values = _load_overrides() if overrides is None else overrides

    if spec.get("on_request"):
        return _raw_flag(spec, values)

    if _configured_bool("GENESI_PASSIVE_MODE", True, values):
        return False

    for umb in spec.get("umbrellas", []):
        if not _configured_bool(_UMBRELLAS[umb], False, values):
            return False

    return _raw_flag(spec, values)


def ensure_active(name: str) -> bool:
    ok = flag_enabled(name)
    if not ok:
        log("AUTOMATION_SKIPPED", flag=name, passive=passive_mode())
    return ok


def snapshot() -> dict[str, Any]:
    overrides = _load_overrides()
    return {
        "passive_mode": _configured_bool("GENESI_PASSIVE_MODE", True, overrides),
        "overrides": overrides,
        "flags": {name: flag_enabled(name, overrides) for name in _FLAGS},
    }


def registry() -> dict[str, Any]:
    return {
        "master": {
            "env": "GENESI_PASSIVE_MODE",
            "default": True,
            "label": "Modalita passiva",
            "description": "Se attiva, spegne tutte le automazioni proattive.",
        },
        "umbrellas": {
            key: {"env": env, "default": False}
            for key, env in _UMBRELLAS.items()
        },
        "flags": {
            name: {
                "env": spec["env"],
                "default": spec["default"],
                "aliases": spec.get("aliases", []),
                "umbrellas": spec.get("umbrellas", []),
                "on_request": bool(spec.get("on_request")),
            }
            for name, spec in _FLAGS.items()
        },
    }


def _allowed_keys() -> set[str]:
    keys = {"GENESI_PASSIVE_MODE", *_UMBRELLAS.values()}
    for spec in _FLAGS.values():
        keys.add(spec["env"])
        keys.update(spec.get("aliases", []))
    return keys


def set_config(values: dict[str, bool]) -> dict[str, Any]:
    current = _load_overrides()
    allowed = _allowed_keys()
    for key, value in values.items():
        if key not in allowed:
            log("AUTOMATION_FLAG_CONFIG_REJECTED", key=key)
            continue
        current[key] = bool(value)
    _save_overrides(current)
    return snapshot()


def reset_config() -> dict[str, Any]:
    try:
        if _OVERRIDES_PATH.exists():
            _OVERRIDES_PATH.unlink()
    except Exception as e:
        log("AUTOMATION_FLAGS_OVERRIDES_RESET_ERROR", error=str(e))
    return snapshot()
