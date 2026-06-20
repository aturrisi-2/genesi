from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.operational_memory.media_analyzer import analyze_media, attachment_type_for_path, is_supported_attachment
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
    media_detected: int = 0
    media_analyzed: int = 0
    media_text_extracted: int = 0
    media_ignored: int = 0


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


_ATTACHED_RE = re.compile(r"<(?:attached|allegato):\s*(?P<name>[^>]+)>", re.IGNORECASE)
_FILE_ATTACHED_RE = re.compile(
    r"(?P<name>[\w .()\-À-ÿ]+\.(?:jpe?g|png|webp|pdf|docx?|xlsx?|mp4|opus|vcf))\s*\(file allegato\)",
    re.IGNORECASE,
)
_LRM = "\u200e"


def _clean_whatsapp_control_chars(text: str) -> str:
    return (text or "").replace(_LRM, "").strip()


def _extract_attachment_name(content: str) -> str | None:
    match = _ATTACHED_RE.search(content or "")
    if match:
        return match.group("name").strip()
    match = _FILE_ATTACHED_RE.search(content or "")
    if match:
        return match.group("name").strip()
    return None


def _content_without_attachment_marker(content: str) -> str:
    cleaned = _ATTACHED_RE.sub("", content or "")
    cleaned = _FILE_ATTACHED_RE.sub("", cleaned)
    cleaned = re.sub(r"<media omess[oi]>", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"media omitted", "", cleaned, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", cleaned).strip()


def _resolve_attachment(media_dir: Path | None, attachment_name: str | None) -> Path | None:
    if media_dir is None or not attachment_name:
        return None
    direct = media_dir / attachment_name
    if direct.exists():
        return direct
    lowered = attachment_name.lower()
    for path in media_dir.iterdir():
        if path.is_file() and path.name.lower() == lowered:
            return path
    return None


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
    media_dir: str | Path | None = None,
    analyze_attachments: bool = True,
) -> WhatsAppParseResult:
    events: list[OperationalEvent] = []
    ignored = 0
    media_detected = 0
    media_analyzed = 0
    media_text_extracted = 0
    media_ignored = 0
    media_root = Path(media_dir) if media_dir else None
    current: dict | None = None

    def flush_current() -> None:
        nonlocal current, ignored, media_detected, media_analyzed, media_text_extracted, media_ignored
        if current is None:
            return
        body = _clean_whatsapp_control_chars(current["body"])
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
        attachment_name = _extract_attachment_name(content)
        attachment_path = _resolve_attachment(media_root, attachment_name)
        cleaned_content = _content_without_attachment_marker(content)
        event_type = "text"
        attachment_metadata = {}
        media_analysis = None
        if _is_media_message(content) or attachment_name:
            media_detected += 1
            event_type = _event_type_for_media(content)
            attachment_metadata = {
                "raw_media_marker": content,
                "description": f"Allegato WhatsApp importato offline: {content}",
            }
            if attachment_path is not None:
                attachment_type = attachment_type_for_path(attachment_path)
                attachment_metadata["file_name"] = attachment_path.name
                attachment_metadata["file_exists"] = True
                if is_supported_attachment(attachment_path) and analyze_attachments:
                    media_analysis = analyze_media(attachment_path)
                    media_analyzed += 1
                    if media_analysis.extracted_text.strip():
                        media_text_extracted += 1
                    event_type = "pdf" if media_analysis.attachment_type == "pdf" else "image"
                elif is_supported_attachment(attachment_path):
                    event_type = attachment_type if attachment_type in {"image", "pdf", "document"} else event_type
                    attachment_metadata["analysis_skipped"] = True
                else:
                    media_ignored += 1
                    if cleaned_content:
                        event_type = "text"
                    else:
                        current = None
                        return
            else:
                attachment_metadata["file_exists"] = False
                if not cleaned_content:
                    media_ignored += 1
        timestamp = _parse_timestamp(current["date"], current["time"], timezone)
        if media_analysis is not None:
            event_content = cleaned_content
        elif _is_media_message(content) or attachment_name:
            event_content = attachment_metadata.get("description", "") if media_root is None else cleaned_content
        else:
            event_content = cleaned_content or content
        if media_analysis is not None and media_analysis.extracted_text:
            event_content = f"{event_content}\n{media_analysis.extracted_text}".strip()
        events.append(
            OperationalEvent(
                event_id=_stable_event_id(project_id, timestamp, sender, content),
                project_id=project_id,
                source=source_name or "whatsapp-export",
                sender=sender,
                timestamp=timestamp,
                type=event_type,
                content=event_content,
                attachment_metadata={
                    **attachment_metadata,
                    **(media_analysis.metadata if media_analysis is not None else {}),
                },
                attachment_path=media_analysis.attachment_path if media_analysis is not None else (str(attachment_path) if attachment_path else None),
                attachment_type=media_analysis.attachment_type if media_analysis is not None else None,
                extracted_text=media_analysis.extracted_text if media_analysis is not None else None,
                media_description=media_analysis.media_description if media_analysis is not None else attachment_metadata.get("description"),
                extraction_status=media_analysis.extraction_status if media_analysis is not None else None,
                extraction_confidence=media_analysis.extraction_confidence if media_analysis is not None else None,
                processed_status="pending",
            )
        )
        current = None

    for raw_line in raw_text.splitlines():
        line = _clean_whatsapp_control_chars(raw_line.rstrip("\n"))
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
    return WhatsAppParseResult(
        events=events,
        ignored=ignored,
        media_detected=media_detected,
        media_analyzed=media_analyzed,
        media_text_extracted=media_text_extracted,
        media_ignored=media_ignored,
    )
