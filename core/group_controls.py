"""Admin-controlled group reply settings."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.log import log

GROUP_CONTROLS_PATH = Path("memory/admin/group_controls.json")
_GROUP_TITLE_DIR = Path("memory/group_title")
_WA_GROUP_JID_DIR = Path("memory/wa_group_jid")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def normalize_whatsapp_group_jid(jid: str) -> str:
    return (jid or "").strip()


def normalize_platform(platform: str) -> str:
    normalized = (platform or "").strip().lower()
    if normalized not in {"whatsapp", "telegram"}:
        raise ValueError("invalid_group_platform")
    return normalized


def normalize_group_id(platform: str, group_id: str | int) -> str:
    platform = normalize_platform(platform)
    value = str(group_id or "").strip()
    if not value:
        raise ValueError("invalid_group_id")
    if platform == "whatsapp":
        value = normalize_whatsapp_group_jid(value)
        if "@" not in value:
            raise ValueError("invalid_whatsapp_group_jid")
    return value


def _default_controls() -> dict[str, Any]:
    return {
        "whatsapp_reply_enabled_groups": {},
        "telegram_reply_enabled_groups": {},
    }


def _controls_key(platform: str) -> str:
    platform = normalize_platform(platform)
    return f"{platform}_reply_enabled_groups"


def _normalize_control_entries(raw_groups: Any, platform: str) -> dict[str, dict[str, Any]]:
    normalized: dict[str, dict[str, Any]] = {}
    if not isinstance(raw_groups, dict):
        return normalized
    for raw_id, raw_info in raw_groups.items():
        try:
            group_id = normalize_group_id(platform, raw_id)
        except ValueError:
            continue
        info = raw_info if isinstance(raw_info, dict) else {}
        normalized[group_id] = {
            "enabled": bool(info.get("enabled", False)),
            "label": str(info.get("label", "")),
            "updated_at": str(info.get("updated_at", "")),
            "observed_at": str(info.get("observed_at", "")),
        }
    return normalized


def load_group_controls() -> dict[str, Any]:
    try:
        if not GROUP_CONTROLS_PATH.exists():
            return _default_controls()
        data = json.loads(GROUP_CONTROLS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _default_controls()
        controls = _default_controls()
        for platform in ("whatsapp", "telegram"):
            key = _controls_key(platform)
            controls[key] = _normalize_control_entries(data.get(key), platform)
        return controls
    except Exception as exc:
        log("GROUP_CONTROLS_LOAD_ERROR", error=str(exc))
        return _default_controls()


def _fsync_directory(path: Path) -> None:
    try:
        fd = os.open(str(path), os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _write_text_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=str(path.parent),
        text=True,
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, path)
        _fsync_directory(path.parent)
    except Exception:
        try:
            tmp_path.unlink()
        except FileNotFoundError:
            pass
        raise


def save_group_controls(controls: dict[str, Any]) -> dict[str, Any]:
    _write_text_atomic(
        GROUP_CONTROLS_PATH,
        json.dumps(controls, ensure_ascii=False, indent=2, sort_keys=True),
    )
    return controls


def is_whatsapp_reply_enabled_by_admin(jid: str) -> bool:
    try:
        return is_group_reply_enabled("whatsapp", jid)
    except ValueError:
        return False


def is_group_reply_enabled(platform: str, group_id: str | int) -> bool:
    try:
        platform = normalize_platform(platform)
        group_key = normalize_group_id(platform, group_id)
    except ValueError:
        return False
    info = load_group_controls().get(_controls_key(platform), {}).get(group_key, {})
    return bool(info.get("enabled", False))


def set_group_reply_enabled(
    platform: str,
    group_id: str | int,
    enabled: bool,
    title: str | None = None,
) -> dict[str, Any]:
    platform = normalize_platform(platform)
    group_key = normalize_group_id(platform, group_id)
    controls = load_group_controls()
    groups = controls.setdefault(_controls_key(platform), {})
    current = groups.get(group_key, {})
    groups[group_key] = {
        "enabled": bool(enabled),
        "label": (title or current.get("label") or "").strip(),
        "updated_at": _now_iso(),
        "observed_at": str(current.get("observed_at", "")),
    }
    save_group_controls(controls)
    log(
        "GROUP_CONTROLS_REPLY_SET",
        platform=platform,
        group_id=group_key[:24],
        enabled=bool(enabled),
        label=(title or "")[:40],
    )
    return controls


def set_whatsapp_reply_enabled(jid: str, enabled: bool, label: str = "") -> dict[str, Any]:
    return set_group_reply_enabled("whatsapp", jid, enabled, title=label)


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _load_project_map(env_name: str) -> dict[str, str]:
    raw = os.getenv(env_name, "")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        return {}
    return {}


def _mask_whatsapp_jid(jid: str) -> str:
    local, sep, domain = jid.partition("@")
    if len(local) <= 6:
        return f"{local[:2]}***{sep}{domain}" if sep else f"{local[:2]}***"
    return f"{local[:3]}***{local[-2:]}{sep}{domain}" if sep else f"{local[:3]}***{local[-2:]}"


def _mask_telegram_chat_id(chat_id: str) -> str:
    value = str(chat_id)
    if len(value) <= 6:
        return value
    return f"{value[:4]}***{value[-3:]}"


def _known_group_payload(
    *,
    platform: str,
    group_id: str,
    title: str,
    admin_info: dict[str, Any],
    project_id: str = "",
    group_hash: str = "",
) -> dict[str, Any]:
    masked_id = _mask_whatsapp_jid(group_id) if platform == "whatsapp" else _mask_telegram_chat_id(group_id)
    payload = {
        "platform": platform,
        "group_id": group_id,
        "masked_id": masked_id,
        "title": title,
        "admin_reply_enabled": bool(admin_info.get("enabled", False)),
        "reply_enabled": bool(admin_info.get("enabled", False)),
        "admin_label": admin_info.get("label", ""),
        "updated_at": admin_info.get("updated_at", ""),
        "observed_at": admin_info.get("observed_at", ""),
        "ingest_enabled": True,
        "project_id": project_id,
    }
    if group_hash:
        payload["group_hash"] = group_hash
    return payload


def known_whatsapp_groups() -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    controls = load_group_controls().get("whatsapp_reply_enabled_groups", {})
    project_map = _load_project_map("WHATSAPP_CHAT_PROJECT_MAP")
    if not _WA_GROUP_JID_DIR.exists():
        return groups
    for jid_path in sorted(_WA_GROUP_JID_DIR.glob("*.json")):
        group_hash = jid_path.stem
        jid = normalize_whatsapp_group_jid(str(_read_json(jid_path, "")))
        if not jid:
            continue
        title = _read_json(_GROUP_TITLE_DIR / f"{group_hash}.json", "") or ""
        admin_info = controls.get(jid, {})
        item = _known_group_payload(
            platform="whatsapp",
            group_id=jid,
            title=title or "WhatsApp Group",
            admin_info=admin_info,
            project_id=project_map.get(jid, ""),
            group_hash=group_hash,
        )
        item["jid"] = jid
        groups.append(item)
    return groups


def known_telegram_groups() -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    controls = load_group_controls().get("telegram_reply_enabled_groups", {})
    project_map = _load_project_map("TELEGRAM_CHAT_PROJECT_MAP")
    if not _GROUP_TITLE_DIR.exists():
        return groups
    for title_path in sorted(_GROUP_TITLE_DIR.glob("*.json")):
        chat_id = title_path.stem
        if not chat_id.startswith("-"):
            continue
        title = _read_json(title_path, "") or ""
        admin_info = controls.get(chat_id, {})
        groups.append(_known_group_payload(
            platform="telegram",
            group_id=chat_id,
            title=title or "Telegram Group",
            admin_info=admin_info,
            project_id=project_map.get(chat_id, ""),
        ))
    return groups


def snapshot() -> dict[str, Any]:
    whatsapp_groups = known_whatsapp_groups()
    telegram_groups = known_telegram_groups()
    return {
        "controls": load_group_controls(),
        "known_whatsapp_groups": whatsapp_groups,
        "known_telegram_groups": telegram_groups,
        "known_groups": {
            "whatsapp": whatsapp_groups,
            "telegram": telegram_groups,
        },
    }
