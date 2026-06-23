"""Video description core for Operational Memory (platform-independent).

Thin async wrapper over the existing video vision pipeline
(`core.video_vision_service.describe_video`: ffmpeg frame extraction + GPT-4o
vision). Path-based to match the media boundary (`media_processor`): it analyses
a local video file and returns a normalised, fail-silent result.

Guarantees:
  * never raises into the caller — every failure degrades to a status;
  * never logs the video description — only status / frames / length;
  * adds no new dependency (reuses the vision stack already in the project);
  * produces NO reply — analysis only. Reply suppression stays in the bridges.

Generic: no channel/domain logic here. Adapters only pass a path + mime.
"""

from __future__ import annotations

import os
from typing import Optional

from core.log import log


def _result(
    status: str,
    text: str = "",
    description: str = "",
    frames_count: int = 0,
    confidence=None,
    error: str = "",
) -> dict:
    return {
        "video_status": status,
        "text": text or "",
        "description": description or "",
        "frames_count": frames_count,
        "confidence": confidence,
        "error": error,
    }


async def describe_video_file(
    path: Optional[str],
    mime_type: Optional[str] = None,
) -> dict:
    """Describe a video file by path. Always returns a dict; never raises.

    `video_status`:
      * video_analyzed     — frames described, `text`/`description` populated;
      * video_no_content   — frames extracted but no usable description;
      * video_unavailable  — no frames / vision produced nothing;
      * missing            — no path / file absent;
      * video_analysis_failed — unexpected error (see `error`).
    """
    if not path or not os.path.exists(path):
        return _result("missing", error="file_not_found")

    try:
        from core.video_vision_service import describe_video
        analysis = await describe_video(path)
    except Exception as exc:  # describe_video is fail-safe; stay defensive anyway
        log("OPERATIONAL_VIDEO_DESCRIBE_ERROR", error=str(exc))
        return _result("video_analysis_failed", error=f"describe_error:{exc}")

    analysis = analysis or {}
    description = (analysis.get("description") or "").strip()
    frames = int(analysis.get("frames_count") or 0)

    if description:
        status = "video_analyzed"
    elif frames == 0:
        status = "video_unavailable"   # no frames extracted at all
    else:
        status = "video_no_content"    # frames seen, but no description

    # Privacy: status / frames / length only — NEVER the description text.
    log("OPERATIONAL_VIDEO_DESCRIBED", status=status, frames=frames, text_len=len(description))
    return _result(status, text=description, description=description, frames_count=frames)
