"""Read-only cross-platform group registry.

This module aggregates currently known Telegram and WhatsApp groups without
mutating memory files or Admin controls.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from core import group_controls

_GROUP_ROSTER_DIR = Path("memory/group_roster")


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
    except Exception:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def _admin_info(controls: dict[str, Any], platform: str, group_id: str) -> dict[str, Any]:
    return controls.get(f"{platform}_reply_enabled_groups", {}).get(group_id, {})


def _registry_item(
    *,
    platform: str,
    group_id: str,
    title: str | None,
    admin_info: dict[str, Any],
    project_id: str | None,
    sources: list[str],
    group_hash: str | None = None,
) -> dict[str, Any]:
    reply_enabled = bool(admin_info.get("enabled", False))
    masked_id = (
        group_controls._mask_whatsapp_jid(group_id)
        if platform == "whatsapp"
        else group_controls._mask_telegram_chat_id(group_id)
    )
    item = {
        "platform": platform,
        "group_id": group_id,
        "title": title or None,
        "masked_id": masked_id,
        "reply_enabled": reply_enabled,
        "admin_reply_enabled": reply_enabled,
        "admin_label": admin_info.get("label", ""),
        "ingest_enabled": True,
        "observed_at": admin_info.get("observed_at") or None,
        "updated_at": admin_info.get("updated_at") or None,
        "project_id": project_id or None,
        "source": ",".join(sorted(set(sources))),
        "sources": sorted(set(sources)),
    }
    if platform == "telegram":
        item["chat_id"] = group_id
    if platform == "whatsapp":
        item["jid"] = group_id
    if group_hash:
        item["group_hash"] = group_hash
    return item


def list_groups() -> list[dict[str, Any]]:
    """Return known WhatsApp/Telegram groups from existing read-only stores."""
    controls = group_controls.load_group_controls()
    groups: dict[tuple[str, str], dict[str, Any]] = {}
    wa_project_map = _load_project_map("WHATSAPP_CHAT_PROJECT_MAP")
    tg_project_map = _load_project_map("TELEGRAM_CHAT_PROJECT_MAP")

    title_dir = group_controls._GROUP_TITLE_DIR
    wa_jid_dir = group_controls._WA_GROUP_JID_DIR

    if wa_jid_dir.exists():
        for jid_path in sorted(wa_jid_dir.glob("*.json")):
            group_hash = jid_path.stem
            jid = group_controls.normalize_whatsapp_group_jid(str(_read_json(jid_path, "")))
            if not jid:
                continue
            title = _read_json(title_dir / f"{group_hash}.json", None)
            info = _admin_info(controls, "whatsapp", jid)
            groups[("whatsapp", jid)] = _registry_item(
                platform="whatsapp",
                group_id=jid,
                title=str(title) if title else None,
                admin_info=info,
                project_id=wa_project_map.get(jid),
                sources=["wa_group_jid", *("group_title" for _ in [title] if title)],
                group_hash=group_hash,
            )

    if title_dir.exists():
        for title_path in sorted(title_dir.glob("*.json")):
            chat_id = title_path.stem
            if not chat_id.startswith("-"):
                continue
            title = _read_json(title_path, None)
            info = _admin_info(controls, "telegram", chat_id)
            groups[("telegram", chat_id)] = _registry_item(
                platform="telegram",
                group_id=chat_id,
                title=str(title) if title else None,
                admin_info=info,
                project_id=tg_project_map.get(chat_id),
                sources=["group_title"],
            )

    if _GROUP_ROSTER_DIR.exists():
        for roster_path in sorted(_GROUP_ROSTER_DIR.glob("*.json")):
            chat_id = roster_path.stem
            if not chat_id.startswith("-"):
                continue
            key = ("telegram", chat_id)
            if key in groups:
                groups[key]["sources"] = sorted(set([*groups[key]["sources"], "group_roster"]))
                groups[key]["source"] = ",".join(groups[key]["sources"])
                continue
            info = _admin_info(controls, "telegram", chat_id)
            groups[key] = _registry_item(
                platform="telegram",
                group_id=chat_id,
                title=None,
                admin_info=info,
                project_id=tg_project_map.get(chat_id),
                sources=["group_roster"],
            )

    for jid, info in controls.get("whatsapp_reply_enabled_groups", {}).items():
        key = ("whatsapp", jid)
        if key not in groups:
            groups[key] = _registry_item(
                platform="whatsapp",
                group_id=jid,
                title=info.get("label") or None,
                admin_info=info,
                project_id=wa_project_map.get(jid),
                sources=["group_controls"],
            )

    for chat_id, info in controls.get("telegram_reply_enabled_groups", {}).items():
        key = ("telegram", chat_id)
        if key not in groups:
            groups[key] = _registry_item(
                platform="telegram",
                group_id=chat_id,
                title=info.get("label") or None,
                admin_info=info,
                project_id=tg_project_map.get(chat_id),
                sources=["group_controls"],
            )

    return sorted(groups.values(), key=lambda item: (item["platform"], item["group_id"]))


def snapshot() -> dict[str, Any]:
    groups = list_groups()
    return {
        "groups": groups,
        "known_groups": {
            "whatsapp": [g for g in groups if g["platform"] == "whatsapp"],
            "telegram": [g for g in groups if g["platform"] == "telegram"],
        },
    }
