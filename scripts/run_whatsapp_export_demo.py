from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.operational_memory.demo_runner import (
    OfflineWhatsAppDemoError,
    OfflineWhatsAppDemoRequest,
    run_whatsapp_export_demo,
)


DEFAULT_SOURCE_NAME = "whatsapp-export-offline"
DEFAULT_TIMEZONE = "Europe/Rome"


def _read_text(path: Path) -> str:
    encodings = ("utf-8-sig", "utf-8", "utf-16", "cp1252")
    last_error: UnicodeDecodeError | None = None
    for encoding in encodings:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
    if last_error is not None:
        raise last_error
    return path.read_text()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the offline WhatsApp export operational-memory demo.",
    )
    parser.add_argument("--input", required=True, help="Path to the WhatsApp _chat.txt export")
    parser.add_argument("--project-id", required=True, help="Operational Memory project id")
    parser.add_argument("--output", required=True, help="Path where the markdown report will be saved")
    parser.add_argument("--source-name", default=DEFAULT_SOURCE_NAME)
    parser.add_argument("--timezone", default=DEFAULT_TIMEZONE)
    parser.add_argument("--report-format", choices=("markdown", "json"), default="markdown")
    parser.add_argument("--no-snapshot", action="store_true", help="Do not create a snapshot")
    parser.add_argument("--verbose", action="store_true", help="Show internal processing logs")
    return parser


async def _run(args: argparse.Namespace) -> dict:
    input_path = Path(args.input)
    output_path = Path(args.output)

    raw_text = _read_text(input_path)
    request = OfflineWhatsAppDemoRequest(
        raw_text=raw_text,
        source_name=args.source_name,
        timezone=args.timezone,
        create_snapshot=not args.no_snapshot,
        report_format=args.report_format,
    )
    if args.verbose:
        response = await run_whatsapp_export_demo(args.project_id, request)
    else:
        with contextlib.redirect_stdout(io.StringIO()):
            response = await run_whatsapp_export_demo(args.project_id, request)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(response.daily_report_markdown, encoding="utf-8")

    return {
        "project_id": response.project_id,
        "imported_messages": response.import_summary.accepted,
        "duplicates": response.import_summary.duplicates,
        "ignored": response.import_summary.ignored,
        "processed_events": response.processing.processed,
        "failed_events": response.processing.failed,
        "pending_after": response.processing.pending_after,
        "decisions": response.state_counts.decisions,
        "open_tasks": response.state_counts.open_tasks,
        "completed_tasks": response.state_counts.completed_tasks,
        "issues": response.state_counts.issues,
        "questions": response.state_counts.questions,
        "snapshot_created": response.snapshot.created,
        "snapshot_id": response.snapshot.snapshot_id,
        "report_path": str(output_path),
    }


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        summary = asyncio.run(_run(args))
    except FileNotFoundError as exc:
        parser.error(f"file not found: {exc.filename}")
        return 2
    except OfflineWhatsAppDemoError as exc:
        parser.error(str(exc))
        return 2

    print(json.dumps(summary, ensure_ascii=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
