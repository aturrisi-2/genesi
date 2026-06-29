"""
ADMIN AUTOMATION API - Genesi

Endpoint per mettere in pausa o riattivare le automazioni proattive senza
modificare manualmente le variabili ambiente.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from pathlib import Path
import os

from auth.models import AuthUser
from auth.router import require_admin
from core import automation_flags
from core import group_controls
from core import group_registry

router = APIRouter(prefix="/admin/automation", tags=["admin-automation"])

_LOG_PATH = Path(os.getenv("GENESI_LOG_PATH", Path(__file__).parent.parent.parent / "genesi.log"))
_DIAGNOSTIC_KEYWORDS = (
    "AUTOMATION_SKIPPED",
    "AUTOMATION",
    "MOLTBOOK",
    "FACEBOOK",
    "IG_",
    "BIRTHDAY",
    "GROUP",
)
_ON_REQUEST_FLAGS = {"calendar_check", "meta_dm_replies"}


class AutomationConfigPayload(BaseModel):
    values: dict[str, bool]


class WhatsAppGroupReplyPayload(BaseModel):
    jid: str
    enabled: bool
    label: str = ""


class GroupReplyPayload(BaseModel):
    platform: str
    group_id: str
    enabled: bool
    title: str = ""


@router.get("/status")
async def automation_status(_: AuthUser = Depends(require_admin)):
    return {
        "registry": automation_flags.registry(),
        "state": automation_flags.snapshot(),
    }


@router.post("/config")
async def automation_config(payload: AutomationConfigPayload, _: AuthUser = Depends(require_admin)):
    return {
        "registry": automation_flags.registry(),
        "state": automation_flags.set_config(payload.values),
    }


@router.post("/reset")
async def automation_reset(_: AuthUser = Depends(require_admin)):
    return {
        "registry": automation_flags.registry(),
        "state": automation_flags.reset_config(),
    }


@router.get("/group-controls")
async def automation_group_controls(_: AuthUser = Depends(require_admin)):
    return _group_controls_snapshot()


def _group_controls_snapshot():
    registry_snapshot = group_registry.snapshot()
    registry_snapshot["controls"] = group_controls.load_group_controls()
    registry_snapshot["known_whatsapp_groups"] = registry_snapshot["known_groups"]["whatsapp"]
    registry_snapshot["known_telegram_groups"] = registry_snapshot["known_groups"]["telegram"]
    return registry_snapshot


@router.post("/group-controls/whatsapp-reply")
async def automation_group_controls_whatsapp_reply(
    payload: WhatsAppGroupReplyPayload,
    _: AuthUser = Depends(require_admin),
):
    group_controls.set_whatsapp_reply_enabled(
        payload.jid,
        payload.enabled,
        label=payload.label,
    )
    return _group_controls_snapshot()


@router.post("/group-controls/reply")
async def automation_group_controls_reply(
    payload: GroupReplyPayload,
    _: AuthUser = Depends(require_admin),
):
    group_controls.set_group_reply_enabled(
        payload.platform,
        payload.group_id,
        payload.enabled,
        title=payload.title,
    )
    return _group_controls_snapshot()


@router.post("/group-controls/telegram-reply")
async def automation_group_controls_telegram_reply(
    payload: GroupReplyPayload,
    _: AuthUser = Depends(require_admin),
):
    group_controls.set_group_reply_enabled(
        "telegram",
        payload.group_id,
        payload.enabled,
        title=payload.title,
    )
    return _group_controls_snapshot()


@router.get("/diagnostics")
async def automation_diagnostics(_: AuthUser = Depends(require_admin)):
    registry = automation_flags.registry()
    state = automation_flags.snapshot()
    flags = state.get("flags", {})
    overrides = state.get("overrides", {})

    proactive_flags = [
        name for name, spec in registry.get("flags", {}).items()
        if name not in _ON_REQUEST_FLAGS and not spec.get("on_request")
    ]
    active_proactive = [name for name in proactive_flags if flags.get(name)]
    paused_proactive = [name for name in proactive_flags if not flags.get(name)]
    enabled_overrides = [key for key, value in overrides.items() if value is True]

    log_lines: list[str] = []
    log_error = ""
    try:
        if _LOG_PATH.exists():
            raw_lines = _LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
            matched = [
                line for line in raw_lines
                if any(keyword.lower() in line.lower() for keyword in _DIAGNOSTIC_KEYWORDS)
            ]
            log_lines = matched[-80:]
        else:
            log_error = f"log_not_found:{_LOG_PATH}"
    except Exception as exc:
        log_error = str(exc)

    return {
        "ok": True,
        "passive_mode": state.get("passive_mode"),
        "all_proactive_paused": len(active_proactive) == 0,
        "active_proactive": active_proactive,
        "paused_proactive": paused_proactive,
        "enabled_overrides": enabled_overrides,
        "on_request_active": {
            name: flags.get(name)
            for name in _ON_REQUEST_FLAGS
        },
        "log_path": str(_LOG_PATH),
        "log_error": log_error,
        "log_lines": log_lines,
    }
