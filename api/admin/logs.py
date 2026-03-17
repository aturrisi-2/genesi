"""
ADMIN LOGS API — Genesi
Streaming real-time di genesi.log via SSE + endpoint di ricerca storica.
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from auth.router import require_admin
from auth.models import AuthUser

logger = logging.getLogger(__name__)

# ── Path log ──────────────────────────────────────────────────────────────────
LOG_PATH = Path(os.getenv("GENESI_LOG_PATH", Path(__file__).parent.parent.parent / "genesi.log"))

router = APIRouter(prefix="/admin/logs", tags=["admin-logs"])

POLL_INTERVAL = 0.35   # secondi tra polling
MAX_TAIL_LINES = 2000  # max righe per /tail


def _extract_tag(line: str) -> str:
    """Estrae il tag da una riga di log. Formato: [TIMESTAMP] TAG key=value..."""
    parts = line.split(" ")
    return parts[1].upper() if len(parts) >= 2 else ""


def _matches(line: str, filter_tags: list[str]) -> bool:
    """True se la riga passa il filtro attivo (OR tra i tag)."""
    if not filter_tags:
        return True
    tag = _extract_tag(line)
    return any(tag.startswith(f) for f in filter_tags)


@router.get("/stream")
async def log_stream(
    filter: str = Query("", description="Prefissi tag separati da virgola, es: PREDICTIVE,AUTOPILOT"),
    lines: int  = Query(300, ge=50, le=1000, description="Righe storiche iniziali"),
    user: AuthUser = Depends(require_admin),
):
    """SSE stream di genesi.log in tempo reale."""
    filter_tags = [f.strip().upper() for f in filter.split(",") if f.strip()]

    async def _generator():
        # ── Batch iniziale: ultime N righe ───────────────────────────────
        if LOG_PATH.exists():
            try:
                all_lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
                initial   = [ln for ln in all_lines[-lines:] if ln.strip() and _matches(ln, filter_tags)]
                for ln in initial:
                    yield f"data: {json.dumps({'line': ln, 'initial': True})}\n\n"
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"

        # ── Keepalive iniziale ────────────────────────────────────────────
        yield f"data: {json.dumps({'status': 'ready'})}\n\n"

        # ── Tail live ────────────────────────────────────────────────────
        pos = LOG_PATH.stat().st_size if LOG_PATH.exists() else 0

        while True:
            await asyncio.sleep(POLL_INTERVAL)
            try:
                if not LOG_PATH.exists():
                    continue
                size = LOG_PATH.stat().st_size
                if size < pos:          # log ruotato
                    pos = 0
                if size > pos:
                    with open(LOG_PATH, encoding="utf-8", errors="replace") as f:
                        f.seek(pos)
                        new_content = f.read()
                    pos = size
                    for ln in new_content.splitlines():
                        if ln.strip() and _matches(ln, filter_tags):
                            yield f"data: {json.dumps({'line': ln})}\n\n"
                else:
                    # Keepalive ogni ~10s
                    yield ": ping\n\n"
            except Exception:
                yield f"data: {json.dumps({'error': 'read_error'})}\n\n"

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control":    "no-cache",
            "X-Accel-Buffering":"no",
            "Connection":       "keep-alive",
        },
    )


@router.get("/tail")
async def log_tail(
    lines:  int = Query(500, ge=10, le=MAX_TAIL_LINES),
    filter: str = Query(""),
    search: str = Query(""),
    user: AuthUser = Depends(require_admin),
):
    """Ultime N righe di genesi.log, con filtro tag e ricerca testuale opzionale."""
    filter_tags = [f.strip().upper() for f in filter.split(",") if f.strip()]
    search_lc   = search.strip().lower()

    if not LOG_PATH.exists():
        return {"lines": [], "total_in_file": 0, "log_path": str(LOG_PATH)}

    try:
        all_lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
        total     = len(all_lines)

        filtered = [
            ln for ln in all_lines
            if ln.strip()
            and _matches(ln, filter_tags)
            and (not search_lc or search_lc in ln.lower())
        ]
        return {
            "lines":       filtered[-lines:],
            "matched":     len(filtered),
            "total_in_file": total,
            "log_path":    str(LOG_PATH),
        }
    except Exception as e:
        return {"error": str(e), "lines": []}


@router.get("/stats")
async def log_stats(user: AuthUser = Depends(require_admin)):
    """Statistiche rapide del log (dimensione, righe totali, ultimi tag)."""
    if not LOG_PATH.exists():
        return {"exists": False, "path": str(LOG_PATH)}

    try:
        stat      = LOG_PATH.stat()
        all_lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
        total     = len(all_lines)

        # Conteggio per tag delle ultime 1000 righe
        tag_counts: dict[str, int] = {}
        for ln in all_lines[-1000:]:
            tag = _extract_tag(ln)
            if tag:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        top_tags = sorted(tag_counts.items(), key=lambda x: -x[1])[:15]

        return {
            "exists":       True,
            "path":         str(LOG_PATH),
            "size_kb":      round(stat.st_size / 1024, 1),
            "total_lines":  total,
            "top_tags":     [{"tag": t, "count": c} for t, c in top_tags],
            "last_lines":   all_lines[-5:],
        }
    except Exception as e:
        return {"error": str(e)}
