"""FASE WHATSAPP 1 — WhatsApp ↔ Operational Memory bridge (skeleton, flag-gated).

Parallel transport adapter to the (already validated) Telegram one. It reuses the
platform-independent operational core (chat_presence / query_engine / invocation
router) and adds only WhatsApp-specific transport:

  * config + chat→project mapping keyed on the WhatsApp group JID ("…@g.us");
  * a plain-text reply renderer (WhatsApp has no inline buttons on the Baileys
    send path → the report link is a text line, never a button);
  * group-JID reply target (never the sender JID).

Safety: DEFAULT OFF. With OPERATIONAL_MEMORY_WHATSAPP_ENABLED unset/false the
bridge is a no-op and the existing WhatsApp behaviour is unchanged. When enabled,
only chats explicitly mapped are touched; unmapped (personal/family) groups are
never ingested nor answered. No chat/JID/profession token is hardcoded.
"""

from __future__ import annotations

import asyncio
import json
import os
from typing import Awaitable, Callable, Optional

from core.log import log
from core.operational_memory.chat_presence import (
    build_operational_reply,
    flush_project,
    silent_update,
)
from core.operational_memory.invocation_router import is_invoked
from core.operational_memory.models import (
    ChatAttachment,
    ChatMessage,
    InvocationConfig,
)
from core.operational_memory.query_engine import (
    classify_query_intent,
    is_pure_operational_invocation,
)


Updater = Callable[[ChatMessage], Awaitable[None]]
SendMessage = Callable[..., Awaitable[object]]

_MEDIA_TYPES = {"image", "document", "video", "audio", "voice"}


# --------------------------------------------------------------------------- #
# Config (env-driven, default OFF)
# --------------------------------------------------------------------------- #


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def is_whatsapp_operational_enabled() -> bool:
    return _env_flag("OPERATIONAL_MEMORY_WHATSAPP_ENABLED", False)


def is_whatsapp_operational_reply_enabled() -> bool:
    # Default OFF in this phase: ingest may run on mapped chats, but no live reply
    # is sent unless explicitly enabled.
    return _env_flag("WHATSAPP_OPERATIONAL_REPLY_ENABLED", False)


def get_whatsapp_chat_project_map() -> dict[str, str]:
    """group JID (str, e.g. '…@g.us') -> operational project_id. From env JSON.
    Generic and configurable; no JID hardcoded."""
    raw = os.getenv("WHATSAPP_CHAT_PROJECT_MAP")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v) for k, v in data.items()}


def resolve_whatsapp_project_id(chat_jid: str) -> Optional[str]:
    return get_whatsapp_chat_project_map().get(str(chat_jid)) if chat_jid else None


def _public_base_url() -> str:
    return (os.getenv("PUBLIC_BASE_URL") or "").rstrip("/")


# --------------------------------------------------------------------------- #
# Rendering (WhatsApp text — no inline buttons)
# --------------------------------------------------------------------------- #


def render_whatsapp_reply(reply) -> str:
    """Plain-text WhatsApp body. The report URL is appended as a text line because
    the Baileys send path carries no inline keyboard."""
    body = reply.reply_markdown or ""
    if reply.report_url:
        body = f"{body}\n\n📄 Report: {reply.report_url}".strip()
    return body


def _attachments_for(media_type: str) -> list[ChatAttachment]:
    if media_type not in _MEDIA_TYPES:
        return []
    norm = "document" if media_type == "document" else media_type
    # Conservative placeholder: no OCR yet, just record that media was present.
    return [ChatAttachment(type=norm, metadata={"placeholder": True, "source": "whatsapp"})]


def _fallback_message_id(group_jid: str, sender_jid: str, text: str) -> str:
    return f"wa_{group_jid}_{sender_jid}_{abs(hash(text)) % 10_000_000}"


async def _safe_update(update: Updater, message: ChatMessage) -> None:
    try:
        await update(message)
    except Exception as exc:  # never break the host bot
        log("OPERATIONAL_WHATSAPP_INGEST_ERROR", chat_id=message.chat_id, error=str(exc))


# --------------------------------------------------------------------------- #
# Bridge entry point
# --------------------------------------------------------------------------- #


async def maybe_handle_whatsapp_operational(
    group_jid: str,
    sender_jid: str,
    first_name: str,
    text: str,
    send_message: SendMessage,
    message_id: Optional[str] = None,
    media_type: str = "",
    config: Optional[InvocationConfig] = None,
    updater: Optional[Updater] = None,
) -> bool:
    """Returns True when the operational layer CLAIMS the message (the host bot
    must stop, avoiding a second/empathic reply); False to let the existing
    WhatsApp pipeline proceed unchanged.

    For a mapped operational group the layer is dominant: every message is claimed
    (silent ingest), the empathic auto-intervention never runs in parallel. Reply
    is sent ONLY on an explicit invocation AND when reply is enabled, to the GROUP
    JID. Never raises into the caller — failures degrade to False (legacy flow)."""
    try:
        if not is_whatsapp_operational_enabled():
            return False
        project_id = resolve_whatsapp_project_id(group_jid)
        if not project_id:
            return False  # unmapped (personal/family) → legacy behaviour, no operational side effects

        update = updater or silent_update
        message = ChatMessage(
            project_id=project_id,
            message_id=str(message_id or _fallback_message_id(group_jid, sender_jid, text)),
            sender=first_name or "",
            chat_id=group_jid,
            source="whatsapp",
            text=text or "",
            attachments=_attachments_for(media_type),
        )

        decision = is_invoked(text, config)

        # Silent (non-invoked) OR reply disabled → ingest in background and CLAIM
        # the message so the empathic pipeline does not answer the operational group.
        if not decision.respond or not is_whatsapp_operational_reply_enabled():
            asyncio.create_task(_safe_update(update, message))
            log("OPERATIONAL_WHATSAPP_SILENT", chat_id=group_jid, project_id=project_id,
                invoked=decision.respond, reply_enabled=is_whatsapp_operational_reply_enabled())
            return True  # operational-dominant: no parallel empathic reply

        # Invoked + reply enabled → rebuild before reply (deterministic ordering).
        intent = classify_query_intent(decision.query)
        log("OPERATIONAL_WHATSAPP_REBUILD_BEFORE_REPLY", project_id=project_id, mode=decision.mode)
        if is_pure_operational_invocation(decision.query):
            await flush_project(project_id)
            log("OPERATIONAL_WHATSAPP_INVOCATION_NOT_INGESTED",
                project_id=project_id, intent=intent, reason="pure_invocation")
        else:
            await _safe_update(update, message)
            log("OPERATIONAL_WHATSAPP_INVOCATION_INGESTED",
                project_id=project_id, intent=intent, reason="contains_operational_update")

        reply = await build_operational_reply(
            project_id, decision.query,
            report_base_url=_public_base_url(), invoked_by=first_name or "",
        )
        log("OPERATIONAL_WHATSAPP_REPLY_AFTER_REBUILD", project_id=project_id)
        # Reply goes to the GROUP JID, never the sender JID.
        await send_message(group_jid, render_whatsapp_reply(reply))
        log("OPERATIONAL_WHATSAPP_REPLY", chat_id=group_jid, project_id=project_id,
            intent=reply.intent, report_id=reply.report_id)
        return True
    except Exception as exc:  # never break the existing WhatsApp bot
        log("OPERATIONAL_WHATSAPP_ERROR", chat_id=group_jid, error=str(exc))
        return False
