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
from pathlib import Path
from typing import Awaitable, Callable, Optional

from core.log import log
from core.operational_memory.chat_presence import (
    build_operational_reply,
    flush_project,
    silent_update,
)
from core.operational_memory.invocation_router import is_invoked
from core.operational_memory.media_processor import analyze_attachment
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
    # Conservative placeholder: no OCR (no file info), just record media presence.
    return [ChatAttachment(type=norm, metadata={"placeholder": True, "source": "whatsapp"})]


async def _build_attachments(
    media_type: str,
    media_id: str,
    media_dir: str,
    filename: Optional[str],
    mime_type: Optional[str],
) -> list[ChatAttachment]:
    """Run the shared media/OCR core on the downloaded file (if available) and
    return a normalised attachment. No file info → conservative placeholder."""
    if media_type not in _MEDIA_TYPES:
        return []
    if media_id and media_dir:
        path = str(Path(media_dir) / media_id)
        att = await analyze_attachment(
            path,
            media_type=media_type,
            filename=filename,
            mime_type=mime_type,
            message_id=media_id,
            platform="whatsapp",
            allowed_dirs=[media_dir],
        )
        return [att]
    return _attachments_for(media_type)


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
    media_id: str = "",
    media_dir: str = "",
    filename: Optional[str] = None,
    mime_type: Optional[str] = None,
    reply_to_id: Optional[str] = None,
    parent_text: str = "",
    parent_media_type: str = "",
    parent_attachment_summary: str = "",
    config: Optional[InvocationConfig] = None,
    updater: Optional[Updater] = None,
    result: Optional[dict] = None,
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
        attachments = await _build_attachments(media_type, media_id, media_dir, filename, mime_type)
        message = ChatMessage(
            project_id=project_id,
            message_id=str(message_id or _fallback_message_id(group_jid, sender_jid, text)),
            sender=first_name or "",
            chat_id=group_jid,
            source="whatsapp",
            text=text or "",
            attachments=attachments,
            reply_to_id=(str(reply_to_id) if reply_to_id else None),
            parent_text=parent_text or "",
            parent_media_type=parent_media_type or "",
            parent_attachment_summary=parent_attachment_summary or "",
        )

        decision = is_invoked(text, config)
        reply_enabled = is_whatsapp_operational_reply_enabled()

        def _set_action(action: str) -> None:
            if result is not None:
                result["action"] = action

        # Normal (non-invocation) message → silent ingest, claim (suppress empathic).
        if not decision.respond:
            asyncio.create_task(_safe_update(update, message))
            log("OPERATIONAL_WHATSAPP_SILENT", chat_id=group_jid, project_id=project_id)
            _set_action("silent_ingest")
            return True  # operational-dominant: no parallel empathic reply

        # Invocation. Pure queries are NEVER stored as items (even when reply is
        # disabled); update-bearing invocations are ingested.
        intent = classify_query_intent(decision.query)
        pure = is_pure_operational_invocation(decision.query)
        if pure:
            log("OPERATIONAL_WHATSAPP_INVOCATION_NOT_INGESTED",
                project_id=project_id, intent=intent, reason="pure_invocation")
        elif reply_enabled:
            await _safe_update(update, message)
            log("OPERATIONAL_WHATSAPP_INVOCATION_INGESTED",
                project_id=project_id, intent=intent, reason="contains_operational_update")
        else:
            # No live reply, but still capture the update silently.
            asyncio.create_task(_safe_update(update, message))
            log("OPERATIONAL_WHATSAPP_INVOCATION_INGESTED",
                project_id=project_id, intent=intent, reason="contains_operational_update")

        if not reply_enabled:
            # Distinguish: a pure query was claimed but NOT ingested vs an update
            # that was captured. Neither sent a reply (reply OFF).
            _set_action("claim_no_reply" if pure else "ingest_update")
            return True  # claimed, no live reply (reply flag OFF)

        # Reply enabled → rebuild before reply (deterministic ordering), send to GROUP JID.
        log("OPERATIONAL_WHATSAPP_REBUILD_BEFORE_REPLY", project_id=project_id, mode=decision.mode)
        if pure:
            await flush_project(project_id)
        reply = await build_operational_reply(
            project_id, decision.query,
            report_base_url=_public_base_url(), invoked_by=first_name or "",
        )
        log("OPERATIONAL_WHATSAPP_REPLY_AFTER_REBUILD", project_id=project_id)
        await send_message(group_jid, render_whatsapp_reply(reply))  # GROUP JID, never sender
        log("OPERATIONAL_WHATSAPP_REPLY", chat_id=group_jid, project_id=project_id,
            intent=reply.intent, report_id=reply.report_id)
        _set_action("reply")
        return True
    except Exception as exc:  # never break the existing WhatsApp bot
        log("OPERATIONAL_WHATSAPP_ERROR", chat_id=group_jid, error=str(exc))
        return False
