from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from core.operational_memory.models import OperationalEvent


_LINE_PATTERNS = [
    re.compile(
        r"^\[(?P<date>\d{1,2}/\d{1,2}/\d{2,4}),\s*(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\]\s*(?P<body>.*)$"
    ),
    re.compile(
        r"^(?P<date>\d{1,2}/\d{1,2}/\d{2,4}),\s*(?P<time>\d{1,2}:\d{2}(?::\d{2})?)\s*-\s*(?P<body>.*)$"
    ),
]

_SYSTEM_MARKERS = (
    "messages and calls are end-to-end encrypted",
    "i messaggi e le chiamate sono crittografati",
    "ha creato il gruppo",
    "hai creato il gruppo",
    "ha aggiunto",
    "ha rimosso",
    "ha abbandonato",
    "ha cambiato",
    "security code changed",
    "codice di sicurezza",
)

_MEDIA_MARKERS = (
    "<media omessi>",
    "<media omesso>",
    "media omitted",
    "<attached:",
    "<allegato:",
)


@dataclass
class WhatsAppParseResult:
    events: list[OperationalEvent]
    ignored: int = 0


def _parse_timestamp(date_part: str, time_part: str, timezone: str) -> str:
    day, month, year = [int(part) for part in date_part.split("/")]
    if year < 100:
        year += 2000
    pieces = [int(part) for part in time_part.split(":")]
    hour = pieces[0]
    minute = pieces[1]
    second = pieces[2] if len(pieces) > 2 else 0
    tz = ZoneInfo(timezone)
    return datetime(year, month, day, hour, minute, second, tzinfo=tz).isoformat()


def _split_sender(body: str) -> tuple[str, str] | None:
    if ": " not in body:
        return None
    sender, content = body.split(": ", 1)
    sender = sender.strip()
    content = content.strip()
    if not sender or not content:
        return None
    return sender, content


def _is_system_message(body: str) -> bool:
    low = body.strip().lower()
    if not low:
        return True
    if _split_sender(body) is None:
        return True
    return any(marker in low for marker in _SYSTEM_MARKERS)


def _is_media_message(content: str) -> bool:
    low = content.lower()
    return any(marker in low for marker in _MEDIA_MARKERS)


def _event_type_for_media(content: str) -> str:
    low = content.lower()
    if ".pdf" in low:
        return "pdf"
    if any(ext in low for ext in (".doc", ".docx", ".xls", ".xlsx")):
        return "document"
    return "image"


def _stable_event_id(project_id: str, timestamp: str, sender: str, content: str) -> str:
    raw = f"{project_id}|{timestamp}|{sender}|{content}"
    return "wa_" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _match_line(line: str):
    for pattern in _LINE_PATTERNS:
        match = pattern.match(line)
        if match:
            return match
    return None


def parse_whatsapp_export(
    raw_text: str,
    project_id: str,
    source_name: str = "whatsapp-export",
    timezone: str = "Europe/Rome",
) -> WhatsAppParseResult:
    events: list[OperationalEvent] = []
    ignored = 0
    current: dict | None = None

    def flush_current() -> None:
        nonlocal current, ignored
        if current is None:
            return
        body = current["body"].strip()
        if _is_system_message(body):
            ignored += 1
            current = None
            return
        split = _split_sender(body)
        if split is None:
            ignored += 1
            current = None
            return
        sender, content = split
        event_type = "text"
        attachment_metadata = {}
        if _is_media_message(content):
            event_type = _event_type_for_media(content)
            attachment_metadata = {
                "raw_media_marker": content,
                "description": f"Allegato WhatsApp importato offline: {content}",
            }
        timestamp = _parse_timestamp(current["date"], current["time"], timezone)
        events.append(
            OperationalEvent(
                event_id=_stable_event_id(project_id, timestamp, sender, content),
                project_id=project_id,
                source=source_name or "whatsapp-export",
                sender=sender,
                timestamp=timestamp,
                type=event_type,
                content=content,
                attachment_metadata=attachment_metadata,
                processed_status="pending",
            )
        )
        current = None

    for raw_line in raw_text.splitlines():
        line = raw_line.rstrip("\n")
        match = _match_line(line)
        if match:
            flush_current()
            current = {
                "date": match.group("date"),
                "time": match.group("time"),
                "body": match.group("body"),
            }
            continue
        if current is None:
            if line.strip():
                ignored += 1
            continue
        current["body"] += "\n" + line.strip()

    flush_current()
    return WhatsAppParseResult(events=events, ignored=ignored)
