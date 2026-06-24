"""Secure thumbnail generation for operational media (report viewer V2).

A media file is served ONLY when its id (the basename of an event's
attachment_path) matches an image event of the requested project AND the resolved
path stays inside the allowed media directories. No arbitrary path, no traversal,
no filesystem path exposed in HTML. Fail-safe: returns None on any problem.
"""

from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Optional

from core.log import log

# Directories that may contain operational media (kept in sync with the adapters).
ALLOWED_MEDIA_DIRS = (
    "/opt/genesi-baileys/media-cache",
    "/tmp/genesi-telegram-media",
    "/tmp/genesi-whatsapp-media",
)

MAX_THUMB_PX = 240


def _within_allowed(path: str) -> bool:
    try:
        resolved = Path(path).resolve()
    except Exception:
        return False
    for base in ALLOWED_MEDIA_DIRS:
        try:
            if resolved.is_relative_to(Path(base).resolve()):
                return True
        except Exception:
            continue
    return False


def resolve_media_path(events, media_id: str) -> Optional[str]:
    """Return the on-disk path for `media_id` ONLY if it is the basename of an
    image event's attachment_path in `events` AND inside an allowed dir. Generic;
    no project/chat token. Rejects traversal (media_id must be a bare basename)."""
    mid = (media_id or "").strip()
    if not mid or mid != os.path.basename(mid) or ".." in mid:
        return None
    for e in events:
        att_path = getattr(e, "attachment_path", None)
        att_type = (getattr(e, "attachment_type", None) or getattr(e, "type", "") or "")
        if not att_path:
            continue
        if os.path.basename(att_path) != mid:
            continue
        if "image" not in str(att_type).lower():
            return None  # only images get a thumbnail
        if not _within_allowed(att_path) or not os.path.exists(att_path):
            return None
        return att_path
    return None


def make_thumbnail_bytes(path: str, max_px: int = MAX_THUMB_PX) -> Optional[bytes]:
    """Downscaled JPEG bytes for an image path. Fail-safe → None (caller shows a
    placeholder). Never raises. Caps memory by capping decode + output size."""
    try:
        from PIL import Image
    except Exception:
        return None
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((max_px, max_px))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=80)
            return buf.getvalue()
    except Exception as exc:
        log("OPERATIONAL_THUMBNAIL_ERROR", error=str(exc))
        return None
