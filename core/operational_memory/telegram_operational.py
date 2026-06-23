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
import html as _html
import json
import os
import re
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
    ChatReply,
    InvocationConfig,
    normalize_media_category,
)
from core.operational_memory.query_engine import (
    classify_query_intent,
    is_pure_operational_invocation,
)


async def _telegram_attachments(
    media_type: str,
    media_path: str,
    filename: Optional[str],
    mime: Optional[str],
) -> list[ChatAttachment]:
    """Run the shared media/OCR core on a downloaded Telegram media file. The path
    is confined to its own directory via allowed_dirs (no traversal). No file →
    no attachment (text-only ingest). Generic — same core as every channel."""
    category = normalize_media_category(media_type, mime)
    if not media_path:
        return []
    allowed = [os.path.dirname(os.path.abspath(media_path))]
    att = await analyze_attachment(
        media_path,
        media_type=category or media_type,
        filename=filename,
        mime_type=mime,
        platform="telegram",
        allowed_dirs=allowed,
    )
    return [att]


# Label → focus section ID (generic, no domain/profession hardcoding).
_LABEL_FOCUS: dict[str, str] = {
    "Task aperti": "tasks-open",
    "Problemi aperti": "issues-open",
    "Problemi riaperti": "issues-reopened",
    "Decisioni attive": "decisions-active",
    "Domande aperte": "questions-open",
    "Cambiamenti dallo snapshot precedente": "snapshot-changes",
    "Priorita/Attenzione": "attention",
}

_CARD_LINE_RE = re.compile(r"^• (.+?): (\d+)$")


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


def _focus_url(base_url: str, section: str) -> str:
    sep = "&" if "?" in base_url else "?"
    return f"{base_url}{sep}focus={section}"


def _telegram_html(reply: ChatReply) -> str:
    """Convert plain-text reply_markdown to Telegram-safe HTML with focus links."""
    lines_out: list[str] = []
    for line in reply.reply_markdown.splitlines():
        stripped = line.strip()
        # Section headings → bold
        if stripped.startswith("📌 ") or stripped.startswith("🧭 "):
            emoji, rest = stripped[:2], stripped[2:].strip()
            lines_out.append(f"{emoji} <b>{_html.escape(rest)}</b>")
            continue
        # Card bullet lines → clickable links if report_url available
        m = _CARD_LINE_RE.match(stripped)
        if m and reply.report_url:
            label, count = m.group(1), m.group(2)
            focus_id = _LABEL_FOCUS.get(label)
            if focus_id:
                url = _html.escape(_focus_url(reply.report_url, focus_id))
                lines_out.append(f'• <a href="{url}">{_html.escape(label)}: {count}</a>')
                continue
        # Everything else → plain escaped
        lines_out.append(_html.escape(stripped) if stripped else "")
    return "\n".join(lines_out)


async def maybe_handle_operational(
    chat_id,
    from_id,
    first_name: str,
    text: str,
    send_message: SendMessage,
    message_id: Optional[str] = None,
    media_type: str = "",
    media_path: str = "",
    media_filename: Optional[str] = None,
    media_mime: Optional[str] = None,
    reply_to_id: Optional[str] = None,
    parent_text: str = "",
    parent_media_type: str = "",
    parent_attachment_summary: str = "",
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
        attachments = await _telegram_attachments(media_type, media_path, media_filename, media_mime)
        message = ChatMessage(
            project_id=project_id,
            message_id=str(message_id or f"tg_{chat_id}_{from_id}_{abs(hash(text)) % 10_000_000}"),
            sender=first_name or "",
            chat_id=str(chat_id),
            source="telegram",
            text=text or "",
            attachments=attachments,
            reply_to_id=(str(reply_to_id) if reply_to_id else None),
            parent_text=parent_text or "",
            parent_media_type=parent_media_type or "",
            parent_attachment_summary=parent_attachment_summary or "",
        )

        # Explicit invocation gate.
        decision = is_invoked(text, config)

        # Silent (non-invoked) OR reply disabled → ingest in the background and let
        # the existing pipeline proceed. No operational reply is produced.
        if not decision.respond or not reply_enabled():
            asyncio.create_task(_safe_update(update, message))
            if not decision.respond:
                log("OPERATIONAL_TELEGRAM_SILENT", chat_id=chat_id, project_id=project_id)
            return False  # ingested; existing pipeline keeps the update

        # Invoked + reply enabled → ingest + rebuild SYNCHRONOUSLY before building
        # the reply, so the answer reflects the just-ingested event and all prior
        # ones. Deterministic ordering: no race condition, no sleep/delay.
        intent = classify_query_intent(decision.query)
        log("OPERATIONAL_TELEGRAM_REBUILD_BEFORE_REPLY", project_id=project_id, mode=decision.mode)
        if is_pure_operational_invocation(decision.query):
            # Pure query: do NOT store the invocation text as a project item; just
            # rebuild the state already produced by previous messages.
            await flush_project(project_id)
            log("OPERATIONAL_TELEGRAM_INVOCATION_NOT_INGESTED",
                project_id=project_id, intent=intent, reason="pure_invocation")
        else:
            # Invocation carries a real operational update → ingest it, then rebuild.
            await _safe_update(update, message)
            log("OPERATIONAL_TELEGRAM_INVOCATION_INGESTED",
                project_id=project_id, intent=intent, reason="contains_operational_update")

        # Delegate reply construction to the operational service layer, then just
        # transport it. The bridge holds no operational/empathic brain.
        reply = await build_operational_reply(
            project_id, decision.query,
            report_base_url=_public_base_url(), invoked_by=first_name or "",
        )
        log("OPERATIONAL_TELEGRAM_REPLY_AFTER_REBUILD", project_id=project_id)
        reply_markup = None
        if reply.report_url:
            reply_markup = {
                "inline_keyboard": [[{"text": "Apri report completo", "url": reply.report_url}]]
            }
        text_html = _telegram_html(reply)
        await send_message(chat_id, text_html, reply_markup=reply_markup, parse_mode="HTML")
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
