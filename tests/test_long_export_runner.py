from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from core.operational_memory.importers.whatsapp_export import parse_whatsapp_export
from core.operational_memory.models import OperationalEvent
from core.operational_memory.watcher_engine import ingest_events_batch, process_pending_events


def test_long_export_runner_missing_path_returns_clear_error():
    script = Path("scripts/run_whatsapp_long_export_demo.py")
    result = subprocess.run(
        [
            sys.executable,
            str(script),
            "--input",
            "C:/definitely/missing/whatsapp-export",
            "--output",
            "output/reports/missing.md",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )

    assert result.returncode == 2
    assert "WhatsApp export path not found" in result.stderr


def test_whatsapp_long_export_file_allegato_is_detected_without_media_analysis(tmp_path):
    media = tmp_path / "IMG-20260101-WA0001.jpg"
    media.write_bytes(b"fake-jpg")
    raw = "01/01/26, 08:00 - Persona A: IMG-20260101-WA0001.jpg (file allegato)\nCaption tecnica"

    result = parse_whatsapp_export(
        raw,
        project_id="long-fixture",
        media_dir=tmp_path,
        analyze_attachments=False,
    )

    assert result.media_detected == 1
    assert result.media_analyzed == 0
    assert result.events[0].attachment_path == str(media)
    assert result.events[0].attachment_metadata["analysis_skipped"] is True


@pytest.mark.asyncio
async def test_long_export_batch_processing_is_idempotent(monkeypatch, tmp_path):
    from core.operational_memory import event_store, state_store

    monkeypatch.setattr(event_store, "_BASE_DIR", tmp_path / "events")
    monkeypatch.setattr(state_store, "_BASE_DIR", tmp_path / "state")
    events = [
        OperationalEvent(
            event_id="long-evt-1",
            project_id="long-idempotent",
            source="fixture",
            sender="Persona A",
            content="ok",
            processed_status="pending",
        )
    ]

    first_import = await ingest_events_batch("long-idempotent", events)
    second_import = await ingest_events_batch("long-idempotent", events)
    first_processing = await process_pending_events("long-idempotent", limit=10, rebuild_threads=False)
    second_processing = await process_pending_events("long-idempotent", limit=10, rebuild_threads=False)

    assert first_import["accepted"] == 1
    assert second_import["duplicates"] == 1
    assert first_processing["processed"] == 1
    assert second_processing["processed"] == 0
