"""
SYSTEM DIAGNOSTICS API — Genesi
Endpoint privato per lettura log senza SSH.
Token: variabile d'ambiente LIVE_LOGS_TOKEN, oppure file memory/.live_logs_token.
Accesso via header 'Authorization: Bearer <token>' o query param '?token=<token>'.
Se nessun token è configurato, risponde 503.
"""

import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Header

from core.log import log

router = APIRouter(prefix="/api/system", tags=["system-diagnostics"])

_LOG_PATH = Path(os.getenv("GENESI_LOG_PATH", Path(__file__).parent.parent / "genesi.log"))
_TOKEN_FILE = Path(__file__).parent.parent / "memory" / ".live_logs_token"
_DEFAULT_KEYWORDS = [
    "FACE", "PIZZA", "BIOMETRIC", "VISION", "TELEGRAM",
    "CAPTION", "PHOTO", "AWAITING", "CHAT_INPUT", "CHAT_OUTPUT",
]


def _load_token() -> str | None:
    t = os.getenv("LIVE_LOGS_TOKEN", "").strip()
    if t:
        return t
    if _TOKEN_FILE.exists():
        return _TOKEN_FILE.read_text(encoding="utf-8").strip() or None
    return None


def _check_token(authorization: str | None, token: str | None) -> None:
    active = _load_token()
    if not active:
        raise HTTPException(status_code=503, detail="LIVE_LOGS_TOKEN not configured on this server")
    candidate = ""
    if authorization and authorization.startswith("Bearer "):
        candidate = authorization[7:]
    elif token:
        candidate = token
    if not candidate or candidate != active:
        raise HTTPException(status_code=403, detail="Forbidden")


@router.get("/live-logs")
async def live_logs(
    keywords: str = Query(
        ",".join(_DEFAULT_KEYWORDS),
        description="Parole chiave separate da virgola (OR, case-insensitive)",
    ),
    lines: int = Query(150, ge=10, le=500, description="Max righe da restituire"),
    authorization: str | None = Header(default=None),
    token: str | None = Query(default=None, description="Token alternativo via query param"),
):
    """Ultime N righe di genesi.log filtrate per keyword. Auth via LIVE_LOGS_TOKEN."""
    _check_token(authorization, token)

    if not _LOG_PATH.exists():
        return {"ok": False, "error": "log_not_found", "path": str(_LOG_PATH), "lines": []}

    kws = [k.strip().lower() for k in keywords.split(",") if k.strip()]

    try:
        all_lines = _LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
        matched = [ln for ln in all_lines if not kws or any(k in ln.lower() for k in kws)]
        result_lines = matched[-lines:]
        log("LIVE_LOGS_ACCESS", total=len(all_lines), matched=len(matched), returned=len(result_lines), kws=",".join(kws))
        return {
            "ok": True,
            "total_in_file": len(all_lines),
            "matched": len(matched),
            "returned": len(result_lines),
            "keywords": kws,
            "lines": result_lines,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc), "lines": []}
