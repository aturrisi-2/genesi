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
import re
from pathlib import Path
from typing import Awaitable, Callable, Optional

from core.env_flags import env_flag
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
    _STRONG_UPDATE_RE,
    classify_query_intent,
    is_pure_operational_invocation,
)


Updater = Callable[[ChatMessage], Awaitable[None]]
SendMessage = Callable[..., Awaitable[object]]

_MEDIA_TYPES = {"image", "document", "video", "audio", "voice"}

# TAB bridge (B5): read-only cross-project query from a designated origin group.
# Disabled by default — both env vars must be set to enable. Fail-closed: any
# origin mismatch → bridge does not activate; never writes or messages TAB JID.
_TAB_BRIDGE_ORIGIN_JID = os.environ.get("OPERATIONAL_TAB_BRIDGE_ORIGIN_JID", "").strip()
_TAB_BRIDGE_PROJECT_ID = os.environ.get("OPERATIONAL_TAB_BRIDGE_PROJECT_ID", "").strip()
# Matches bare "TAB" and "nel/del/di TAB" — strips the preposition too so the
# stripped query doesn't end with dangling "nel ?" or "del ?".
_TAB_QUERY_RE = re.compile(r"\b(?:nel|del|di|in)\s+TAB\b|\bTAB\b", re.IGNORECASE)
# B8.3 canary console mode: with the flag ON, pure operational queries from the
# bridge origin WITHOUT an explicit target default to the TAB bridge (the origin
# group acts as a read-only console for the TAB project). OFF → B8.2 behaviour.
_TAB_BRIDGE_DEFAULT_NO_TARGET = env_flag("OPERATIONAL_TAB_BRIDGE_DEFAULT_NO_TARGET", False)
# Escape hatch: "canary" keyword pins the query to the origin group's own project
# even in console mode ("stato canary", "nel canary cosa manca?").
_CANARY_KEEP_RE = re.compile(r"\b(?:nel|del|di|in)\s+canary\b|\bprogetto\s+canary\b|\bcanary\b", re.IGNORECASE)


# --------------------------------------------------------------------------- #
# Config (env-driven, default OFF)
# --------------------------------------------------------------------------- #


def is_whatsapp_operational_enabled() -> bool:
    return env_flag("OPERATIONAL_MEMORY_WHATSAPP_ENABLED", False)


def is_whatsapp_operational_reply_enabled(group_jid: str | None = None) -> bool:
    """Whether the operational handler may produce a live reply for a chat.

    Two sources, both default OFF:
    - global env ``WHATSAPP_OPERATIONAL_REPLY_ENABLED`` (all mapped chats), and
    - per-group Admin control (``group_controls.whatsapp_reply_enabled_groups``),
      the same toggle the Admin web / Baileys reply gate already use.

    Per-group keeps activation scoped: enabling the canary never enables TAB.
    """
    if env_flag("WHATSAPP_OPERATIONAL_REPLY_ENABLED", False):
        return True
    if group_jid:
        try:
            from core.group_controls import is_group_reply_enabled
            return is_group_reply_enabled("whatsapp", group_jid)
        except Exception:
            return False
    return False


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


_REPORT_LINK_INTENTS = {"briefing", "digest", "cmd_report"}


def render_whatsapp_reply(reply) -> str:
    """Plain-text WhatsApp body. Report URL appended only for full-report
    intents (briefing/digest/cmd_report); suppressed for focused queries."""
    body = reply.reply_markdown or ""
    if reply.report_url and getattr(reply, "intent", "") in _REPORT_LINK_INTENTS:
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
        reply_enabled = is_whatsapp_operational_reply_enabled(group_jid)

        def _set_action(action: str) -> None:
            if result is not None:
                result["action"] = action

        # Normal (non-invocation) message → silent ingest, claim (suppress empathic).
        if not decision.respond:
            asyncio.create_task(_safe_update(update, message))
            log("OPERATIONAL_WHATSAPP_SILENT", chat_id=group_jid, project_id=project_id)
            _set_action("silent_ingest")
            return True  # operational-dominant: no parallel empathic reply

        # Invocation. B5 TAB bridge detection runs first — before ingestion — so a
        # "stato TAB" query is never stored as a canary item. Strip the "TAB" keyword,
        # re-evaluate purity on the remainder; if pure, override `pure=True`.
        # B8.1: also detect TAB-targeted queries that don't match any known intent
        # (_tab_targeted) — those get fail-closed reply, never ingested as canary.
        _tab_query = ""
        _tab_targeted = False  # TAB keyword present but intent unknown → fail-closed
        _own_query = ""  # console escape hatch: "canary" keyword pins own project
        _bridge_origin = (_TAB_BRIDGE_ORIGIN_JID and _TAB_BRIDGE_PROJECT_ID
                          and group_jid == _TAB_BRIDGE_ORIGIN_JID)
        if _bridge_origin and _TAB_QUERY_RE.search(decision.query):
            _q = _TAB_QUERY_RE.sub("", decision.query).strip()
            if _q and is_pure_operational_invocation(_q):
                _tab_query = _q  # bridge will fire after reply_enabled check
            elif _q:
                # TAB keyword present, intent unknown — guard: no ingest, fail-closed reply.
                _tab_targeted = True
        elif _bridge_origin and _TAB_BRIDGE_DEFAULT_NO_TARGET:
            # B8.3 console mode: no explicit target in the query.
            if _CANARY_KEEP_RE.search(decision.query):
                _q = re.sub(r"\s{2,}", " ", _CANARY_KEEP_RE.sub("", decision.query)).strip()
                if _q and is_pure_operational_invocation(_q):
                    _own_query = _q  # explicit own-project query, keyword stripped
            elif is_pure_operational_invocation(decision.query):
                _tab_query = decision.query.strip()  # console default → TAB bridge
                log("OPERATIONAL_TAB_BRIDGE_DEFAULT", origin_jid=group_jid,
                    query=decision.query[:120])
            elif (classify_query_intent(decision.query) == "unknown"
                    and not _STRONG_UPDATE_RE.search(decision.query)):
                # Ambiguous console query (no intent, no update payload) →
                # fail-closed, never ingested as a canary item.
                _tab_targeted = True
            # else: recognised update payload → normal own-project ingest flow

        intent = classify_query_intent(_own_query or decision.query)
        pure = (is_pure_operational_invocation(decision.query) or bool(_tab_query)
                or _tab_targeted or bool(_own_query))
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

        # B5 TAB bridge: canary-only read-only cross-project query.
        # Never writes TAB state; never sends a message to the TAB JID.
        if _tab_query:
            tab_intent = classify_query_intent(_tab_query)
            tab_reply = await build_operational_reply(
                _TAB_BRIDGE_PROJECT_ID, _tab_query,
                report_base_url=_public_base_url(), invoked_by=first_name or "",
                save=(tab_intent == "cmd_report"),
            )
            await send_message(group_jid, f"Vista TAB reale:\n{render_whatsapp_reply(tab_reply)}")
            log("OPERATIONAL_TAB_BRIDGE_REPLY", origin_jid=group_jid,
                tab_project=_TAB_BRIDGE_PROJECT_ID, tab_intent=tab_intent)
            _set_action("tab_bridge")
            return True

        # B8.1 TAB routing guard: TAB-targeted query with unknown intent → fail-closed.
        # Never ingests into canary state; never produces a generic operational reply.
        if _tab_targeted:
            await send_message(group_jid,
                "Query TAB non riconosciuta. Esempi supportati:\n"
                "stato TAB / problemi aperti TAB / cosa manca nel TAB?\n"
                "fammi il quadro TAB / dove siamo scoperti nel TAB?\n"
                "cosa devo controllare nel TAB? / report TAB"
            )
            log("OPERATIONAL_TAB_BRIDGE_UNKNOWN", origin_jid=group_jid,
                tab_project=_TAB_BRIDGE_PROJECT_ID, query=decision.query[:120])
            _set_action("tab_unknown_fail_closed")
            return True

        # Reply enabled → rebuild before reply (deterministic ordering), send to GROUP JID.
        log("OPERATIONAL_WHATSAPP_REBUILD_BEFORE_REPLY", project_id=project_id, mode=decision.mode)
        if pure:
            await flush_project(project_id)
        reply = await build_operational_reply(
            project_id, _own_query or decision.query,
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
