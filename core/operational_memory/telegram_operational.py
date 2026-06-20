"""FASE 9b — Telegram ↔ Operational Memory wiring (non-destructive, flag-gated).

The existing Telegram bot (core/telegram_bot.py) is preserved as-is. This module
is an OPT-IN bridge: when enabled AND the chat is mapped to an operational
project, every received message is folded into the operational memory silently,
and an explicit operational invocation ("Genesi, fammi il punto", "cosa resta
aperto?", "report"...) is answered with the compact operational briefing + a
report link. Everything else falls through to the existing bot behaviour.

Defaults are OFF, so real groups are unaffected until explicitly enabled.
Mapping telegram_chat_id → project_id is configurable, never hardcoded."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Awaitable, Callable, Optional

from core.log import log
from core.operational_memory.chat_presence import build_operational_reply, silent_update
from core.operational_memory.invocation_router import is_invoked
from core.operational_memory.models import ChatMessage, InvocationConfig


_CONFIG_FILE = Path("config/telegram_operational.json")


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def operational_enabled() -> bool:
    return _env_flag("OPERATIONAL_MEMORY_TELEGRAM_ENABLED", False)


def reply_enabled() -> bool:
    # Reply is allowed by default once the integration is enabled; can be turned
    # off to run pure silent-ingest mode.
    return _env_flag("TELEGRAM_OPERATIONAL_REPLY_ENABLED", True)


def _public_base_url() -> str:
    return (os.getenv("PUBLIC_BASE_URL") or "").rstrip("/")


def _load_chat_project_map() -> dict[str, str]:
    """telegram_chat_id (str) -> operational project_id. From env JSON first,
    then an optional config file. Generic and configurable; no hardcoding."""
    raw = os.getenv("TELEGRAM_CHAT_PROJECT_MAP")
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except json.JSONDecodeError:
            pass
    if _CONFIG_FILE.exists():
        try:
            data = json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
            mapping = data.get("chat_project_map", data) if isinstance(data, dict) else {}
            if isinstance(mapping, dict):
                return {str(k): str(v) for k, v in mapping.items()}
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def project_for_chat(chat_id) -> Optional[str]:
    return _load_chat_project_map().get(str(chat_id))


SendMessage = Callable[..., Awaitable[None]]
Updater = Callable[[ChatMessage], Awaitable[None]]


async def maybe_handle_operational(
    chat_id,
    from_id,
    first_name: str,
    text: str,
    send_message: SendMessage,
    message_id: Optional[str] = None,
    config: Optional[InvocationConfig] = None,
    updater: Optional[Updater] = None,
) -> bool:
    """Returns True if this message was handled by the operational layer (and a
    reply was sent), so the caller should stop. Returns False to let the existing
    Telegram pipeline proceed (the message may still have been ingested silently).

    Never raises into the caller's flow — failures degrade to False."""
    try:
        if not operational_enabled():
            return False
        project_id = project_for_chat(chat_id)
        if not project_id:
            return False  # chat not opted-in → existing behaviour, no operational side effects

        update = updater or silent_update
        message = ChatMessage(
            project_id=project_id,
            message_id=str(message_id or f"tg_{chat_id}_{from_id}_{abs(hash(text)) % 10_000_000}"),
            sender=first_name or "",
            chat_id=str(chat_id),
            source="telegram",
            text=text or "",
        )

        # 1. Always ingest + update memory silently (background, non-blocking).
        asyncio.create_task(_safe_update(update, message))

        # 2. Explicit invocation gate.
        decision = is_invoked(text, config)
        if not decision.respond:
            log("OPERATIONAL_TELEGRAM_SILENT", chat_id=chat_id, project_id=project_id)
            return False  # silent: ingested, no reply, existing pipeline also stays silent on non-invocation
        if not reply_enabled():
            return False  # invoked but operational reply disabled → let existing pipeline answer

        # 3. Delegate reply construction to the operational service layer, then
        #    just transport it. The bridge holds no operational/empathic brain.
        reply = await build_operational_reply(
            project_id, decision.query,
            report_base_url=_public_base_url(), invoked_by=first_name or "",
        )
        reply_markup = None
        if reply.report_url:
            reply_markup = {
                "inline_keyboard": [[{"text": "Apri report", "url": reply.report_url}]]
            }
        await send_message(chat_id, reply.reply_markdown, reply_markup=reply_markup)
        log("OPERATIONAL_TELEGRAM_REPLY", chat_id=chat_id, project_id=project_id,
            intent=reply.intent, report_id=reply.report_id)
        return True
    except Exception as exc:  # never break the existing bot
        log("OPERATIONAL_TELEGRAM_ERROR", chat_id=chat_id, error=str(exc))
        return False


async def _safe_update(update: Updater, message: ChatMessage) -> None:
    try:
        await update(message)
    except Exception as exc:
        log("OPERATIONAL_TELEGRAM_INGEST_ERROR", chat_id=message.chat_id, error=str(exc))
