"""FASE 7 — Report Storage.

Persist full operational reports on the host where Genesi runs (the VPS). The
chat only ever receives a link/attachment, never a wall of text. Reports are
downloadable / printable / re-usable outside the chat."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from core.operational_memory.models import StoredReport, utc_now_iso


_BASE_DIR = Path("memory/operational_reports")
_SAFE_RE = re.compile(r"[^a-zA-Z0-9_.-]+")
DEFAULT_REPORT_RETENTION = 50


def _safe(value: str) -> str:
    return _SAFE_RE.sub("_", (value or "").strip()).strip("._") or "default"


def _project_dir(project_id: str) -> Path:
    return _BASE_DIR / _safe(project_id)


def _dump(model: Any) -> dict[str, Any]:
    return model.model_dump() if hasattr(model, "model_dump") else model.dict()


def _report_id(project_id: str, generated_at: str, markdown: str) -> str:
    digest = hashlib.sha1(f"{project_id}|{generated_at}|{len(markdown)}".encode("utf-8")).hexdigest()[:10]
    stamp = _safe(generated_at)
    return f"report_{stamp}_{digest}"


def save_report(project_id: str, markdown: str, retention: int = DEFAULT_REPORT_RETENTION) -> StoredReport:
    generated_at = utc_now_iso()
    report = StoredReport(
        report_id=_report_id(project_id, generated_at, markdown),
        project_id=project_id,
        generated_at=generated_at,
        markdown=markdown,
    )
    directory = _project_dir(project_id)
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{_safe(report.report_id)}.json").write_text(
        json.dumps(_dump(report), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"
    )
    _prune(project_id, retention)
    return report


def load_report(project_id: str, report_id: str) -> StoredReport | None:
    path = _project_dir(project_id) / f"{_safe(report_id)}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return StoredReport(**data) if isinstance(data, dict) else None


def list_reports(project_id: str) -> list[StoredReport]:
    directory = _project_dir(project_id)
    if not directory.exists():
        return []
    reports: list[StoredReport] = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            reports.append(StoredReport(**data))
    return sorted(reports, key=lambda report: report.generated_at)


def _prune(project_id: str, retention: int) -> None:
    if retention <= 0:
        return
    paths = sorted(_project_dir(project_id).glob("*.json"))
    for path in paths[: max(0, len(paths) - retention)]:
        try:
            path.unlink()
        except OSError:
            pass
