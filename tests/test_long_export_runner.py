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


@pytest.mark.asyncio
async def test_long_export_runner_resume_processes_pending_without_duplicates(monkeypatch, tmp_path):
    from argparse import Namespace
    from core.operational_memory import event_store, state_store
    from core.operational_memory.event_store import list_events
    import scripts.run_whatsapp_long_export_demo as runner
    from scripts.run_whatsapp_long_export_demo import _run

    monkeypatch.setattr(event_store, "_BASE_DIR", tmp_path / "events")
    monkeypatch.setattr(state_store, "_BASE_DIR", tmp_path / "state")
    monkeypatch.setattr(runner, "CHECKPOINT_DIR", tmp_path / "checkpoints")
    export = tmp_path / "chat"
    export.mkdir()
    (export / "chat.txt").write_text(
        "\n".join(
            [
                "01/01/26, 08:00 - Persona A: ok",
                "01/01/26, 08:01 - Persona B: grazie",
                "01/01/26, 08:02 - Persona A: perfetto",
            ]
        ),
        encoding="utf-8",
    )
    output = tmp_path / "report.md"

    base = dict(
        input=str(export),
        output=str(output),
        project_id="resume-fixture",
        short_project_id="resume-fixture",
        source_name="fixture",
        timezone="Europe/Rome",
        report_mode="OPERATIVE_ONLY",
        process_batch_size=1,
        max_events=0,
        max_process_events=0,
        detect_media=True,
        analyze_media=False,
        skip_media_analysis=True,
        relation_window_days=21,
        relation_max_candidates_per_thread=20,
        create_snapshot=False,
        verbose=False,
        incremental=False,
        force_full_rebuild=False,
    )

    first = await _run(Namespace(**base, resume=False, max_batches=1))
    second = await _run(Namespace(**base, resume=True, max_batches=0))
    events = await list_events("resume-fixture")

    assert first["run_status"] == "RESUMABLE_PENDING"
    assert second["run_status"] == "COMPLETE"
    assert len(events) == 3
    assert len({event.event_id for event in events}) == 3
    assert all(event.processed_status == "processed" for event in events)
