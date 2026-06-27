"""Admin-controlled group reply settings."""

from __future__ import annotations

import json
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


def _default_controls() -> dict[str, Any]:
    return {"whatsapp_reply_enabled_groups": {}}


def load_group_controls() -> dict[str, Any]:
    try:
        if not GROUP_CONTROLS_PATH.exists():
            return _default_controls()
        data = json.loads(GROUP_CONTROLS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return _default_controls()
        controls = _default_controls()
        groups = data.get("whatsapp_reply_enabled_groups")
        if isinstance(groups, dict):
            normalized: dict[str, dict[str, Any]] = {}
            for raw_jid, raw_info in groups.items():
                jid = normalize_whatsapp_group_jid(str(raw_jid))
                if not jid:
                    continue
                info = raw_info if isinstance(raw_info, dict) else {}
                normalized[jid] = {
                    "enabled": bool(info.get("enabled", False)),
                    "label": str(info.get("label", "")),
                    "updated_at": str(info.get("updated_at", "")),
                }
            controls["whatsapp_reply_enabled_groups"] = normalized
        return controls
    except Exception as exc:
        log("GROUP_CONTROLS_LOAD_ERROR", error=str(exc))
        return _default_controls()


def save_group_controls(controls: dict[str, Any]) -> dict[str, Any]:
    GROUP_CONTROLS_PATH.parent.mkdir(parents=True, exist_ok=True)
    GROUP_CONTROLS_PATH.write_text(
        json.dumps(controls, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return controls


def is_whatsapp_reply_enabled_by_admin(jid: str) -> bool:
    jid = normalize_whatsapp_group_jid(jid)
    if not jid:
        return False
    info = load_group_controls().get("whatsapp_reply_enabled_groups", {}).get(jid, {})
    return bool(info.get("enabled", False))


def set_whatsapp_reply_enabled(jid: str, enabled: bool, label: str = "") -> dict[str, Any]:
    jid = normalize_whatsapp_group_jid(jid)
    if not jid or "@" not in jid:
        raise ValueError("invalid_whatsapp_group_jid")
    controls = load_group_controls()
    groups = controls.setdefault("whatsapp_reply_enabled_groups", {})
    groups[jid] = {
        "enabled": bool(enabled),
        "label": label.strip(),
        "updated_at": _now_iso(),
    }
    save_group_controls(controls)
    log("GROUP_CONTROLS_WHATSAPP_REPLY_SET", jid=jid[:24], enabled=bool(enabled), label=label[:40])
    return controls


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def known_whatsapp_groups() -> list[dict[str, Any]]:
    groups: list[dict[str, Any]] = []
    controls = load_group_controls().get("whatsapp_reply_enabled_groups", {})
    if not _WA_GROUP_JID_DIR.exists():
        return groups
    for jid_path in sorted(_WA_GROUP_JID_DIR.glob("*.json")):
        group_hash = jid_path.stem
        jid = normalize_whatsapp_group_jid(str(_read_json(jid_path, "")))
        if not jid:
            continue
        title = _read_json(_GROUP_TITLE_DIR / f"{group_hash}.json", "") or ""
        admin_info = controls.get(jid, {})
        groups.append({
            "group_hash": group_hash,
            "jid": jid,
            "title": title or "WhatsApp Group",
            "admin_reply_enabled": bool(admin_info.get("enabled", False)),
            "admin_label": admin_info.get("label", ""),
            "updated_at": admin_info.get("updated_at", ""),
        })
    return groups


def snapshot() -> dict[str, Any]:
    return {
        "controls": load_group_controls(),
        "known_whatsapp_groups": known_whatsapp_groups(),
    }
