from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from core.operational_memory.chat_profile_engine import build_adaptive_chat_profile
from core.operational_memory.daily_report import build_daily_report
from core.operational_memory.event_store import list_events
from core.operational_memory.importers.whatsapp_export import parse_whatsapp_export
from core.operational_memory.macro_thread_engine import build_macro_threads
from core.operational_memory.snapshot_store import create_snapshot
from core.operational_memory.state_store import load_state, save_state
from core.operational_memory.incremental_rebuild import incremental_rebuild
from core.operational_memory.thread_engine import rebuild_project_threads
from core.operational_memory.thread_relation_engine import build_thread_relation_candidates
from core.operational_memory.thread_validation import (
    calculate_false_macro_prevention_rate,
    calculate_isolated_thread_rate,
    calculate_macro_heterogeneity_score,
    calculate_rejected_relation_count,
    calculate_promoted_relation_count,
    calculate_candidate_relation_count,
    calculate_unassigned_thread_rate,
    calculate_useful_unassigned_thread_rate,
)
from core.operational_memory.watcher_engine import ingest_events_batch, process_pending_events


DEFAULT_PROJECT_ID = "tab-cefla-hq-enel-roma-long-relations-01"
DEFAULT_SHORT_PROJECT_ID = "tab-cefla-hq-enel-roma-boundary-02"
CHECKPOINT_DIR = Path("memory/operational_checkpoints")


def _read_text(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "utf-16", "cp1252"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text()


def _resolve_input(path: Path) -> tuple[Path, Path | None]:
    if not path.exists():
        raise FileNotFoundError(f"WhatsApp export path not found: {path}")
    if path.is_file():
        return path, path.parent
    txt_files = sorted(path.glob("*.txt"))
    if not txt_files:
        raise FileNotFoundError(f"No WhatsApp .txt export found in: {path}")
    preferred = [candidate for candidate in txt_files if "chat" in candidate.name.lower()]
    return (preferred[0] if preferred else txt_files[0]), path


def _checkpoint_path(project_id: str) -> Path:
    safe = "".join(char if char.isalnum() or char in "._-" else "_" for char in project_id).strip("._")
    return CHECKPOINT_DIR / f"{safe or 'default'}_long_export.json"


def _load_checkpoint(project_id: str) -> dict:
    path = _checkpoint_path(project_id)
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _save_checkpoint(project_id: str, data: dict) -> None:
    path = _checkpoint_path(project_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _run_status(pending: int, max_batches_reached: bool, timeout_seconds: float | None = None) -> str:
    if timeout_seconds is not None:
        return "TIMEOUT"
    if pending > 0:
        return "RESUMABLE_PENDING" if max_batches_reached else "PARTIAL"
    return "COMPLETE"


def _metrics_for_state(project_id: str, state, events_count: int | None = None) -> dict:
    relations = state.thread_relation_candidates
    macros = state.macro_threads
    return {
        "project_id": project_id,
        "events": events_count,
        "threads": len(state.threads),
        "macro_threads": len(macros),
        "largest_macro": max((len(macro.child_thread_ids) for macro in macros), default=0),
        "relation_candidates": calculate_candidate_relation_count(relations),
        "promoted_relations": calculate_promoted_relation_count(relations),
        "rejected_relations": calculate_rejected_relation_count(relations),
        "stored_relations": len(relations),
        "useful_unassigned_thread_rate": calculate_useful_unassigned_thread_rate(state.threads, macros, relations),
        "isolated_thread_rate": calculate_isolated_thread_rate(state.threads, macros, relations),
        "macro_heterogeneity_score": calculate_macro_heterogeneity_score(macros),
        "false_macro_prevention_rate": calculate_false_macro_prevention_rate(state.threads, macros, relations),
        "unassigned_thread_rate": calculate_unassigned_thread_rate(state.threads, macros),
    }


async def _rebuild_profile_macro_relations(
    project_id: str,
    relation_window_days: int,
    relation_max_candidates_per_thread: int,
) -> dict:
    started = time.perf_counter()
    threads = await rebuild_project_threads(project_id)
    thread_engine_seconds = time.perf_counter() - started

    events = await list_events(project_id)
    state = await load_state(project_id)

    started = time.perf_counter()
    profile = build_adaptive_chat_profile(project_id, events, threads)
    profile_seconds = time.perf_counter() - started

    started = time.perf_counter()
    macros = build_macro_threads(project_id, threads, events, profile)
    macro_seconds = time.perf_counter() - started

    started = time.perf_counter()
    relation_stats: dict = {}
    relations = build_thread_relation_candidates(
        project_id,
        threads,
        events,
        profile,
        relation_window_days=relation_window_days,
        relation_max_candidates_per_thread=relation_max_candidates_per_thread,
        stats=relation_stats,
    )
    relation_seconds = time.perf_counter() - started

    state.threads = threads
    state.adaptive_chat_profile = profile
    state.macro_threads = macros
    state.thread_relation_candidates = relations
    await save_state(project_id, state)
    return {
        "thread_engine_seconds": thread_engine_seconds,
        "profile_seconds": profile_seconds,
        "macro_engine_seconds": macro_seconds,
        "relation_engine_seconds": relation_seconds,
        "relation_stats": relation_stats,
    }


def _append_incremental_diagnostics(summary: dict) -> list[str]:
    inc = summary.get("incremental", {})
    timings = summary.get("timings", {})
    broad = inc.get("broad_canonical_terms", []) or []
    canonical = inc.get("canonical_distribution", []) or []
    lines = [
        "",
        "## Diagnostica incremental rebuild",
        f"- run mode: {inc.get('mode')}",
        f"- full rebuild avoided: {'yes' if inc.get('full_rebuild_avoided') else 'no'}",
        f"- reason if full rebuild happened: {inc.get('rebuild_reason') or '(nessuno)'}",
        f"- events processed this run: {inc.get('events_processed_this_run')}",
        f"- dirty threads: {inc.get('dirty_threads')}",
        f"- dirty canonical terms: {inc.get('dirty_canonical_terms')}",
        f"- dirty relation pairs: {inc.get('dirty_relation_pairs')}",
        f"- relation pairs recalculated: {inc.get('relation_pairs_recalculated')}",
        f"- relation pairs reused: {inc.get('relation_pairs_reused')}",
        f"- macros rebuilt: {inc.get('macros_rebuilt')}",
        f"- macros reused: {inc.get('macros_reused')}",
        "",
        "## Diagnostica canonical term distribution",
        "| termine canonico | thread coverage | pair generation count | discriminative power | broad | weak context |",
        "| --- | ---: | ---: | ---: | :---: | :---: |",
    ]
    for row in canonical[:15]:
        lines.append(
            f"| {row['label']} | {row['thread_coverage']} | {row['pair_generation_count']} | "
            f"{row['discriminative_power']} | {'yes' if row['broad_canonical_term'] else 'no'} | "
            f"{'yes' if row['weak_context_term'] else 'no'} |"
        )
    if broad:
        lines.append("")
        lines.append(f"- broad canonical terms emersi (non hardcoded): {', '.join(row['label'] for row in broad[:10])}")
    lines.extend(
        [
            "",
            "## Diagnostica performance",
            f"- import time: {timings.get('import_seconds', 0.0):.2f}s",
            f"- processing time: {timings.get('processing_seconds', 0.0):.2f}s",
            f"- thread engine time: {timings.get('thread_engine_seconds', 0.0):.2f}s",
            f"- profile time: {timings.get('profile_seconds', 0.0):.2f}s",
            f"- macro engine time: {timings.get('macro_engine_seconds', 0.0):.2f}s",
            f"- relation engine time: {timings.get('relation_engine_seconds', 0.0):.2f}s",
            f"- report time: {timings.get('report_seconds', 0.0):.2f}s",
            f"- total time: {sum(timings.values()):.2f}s",
            "",
            f"- Stato run: {summary.get('run_status')} "
            f"(mode={inc.get('mode')}, full rebuild avoided={'yes' if inc.get('full_rebuild_avoided') else 'no'})",
        ]
    )
    return lines


def _append_long_diagnostics(markdown: str, summary: dict, short_metrics: dict, long_metrics: dict) -> str:
    lines = [
        markdown.rstrip(),
        "",
        "## Diagnostica Long Export",
        "- Questo dataset e usato come stress test reale, non come hardcoding di dominio.",
        f"- Messaggi importati: {summary['import']['accepted']}",
        f"- Eventi processati: {summary['processing']['processed']}",
        f"- Media rilevati: {summary['import']['media_detected']}",
        f"- Media analizzati: {summary['import']['media_analyzed']}",
        f"- Media ignorati/skippati: {summary['import']['media_ignored']}",
        f"- Tempo import: {summary['timings']['import_seconds']:.2f}s",
        f"- Tempo processing: {summary['timings']['processing_seconds']:.2f}s",
        f"- Tempo thread engine: {summary['timings']['thread_engine_seconds']:.2f}s",
        f"- Tempo relation engine: {summary['timings']['relation_engine_seconds']:.2f}s",
        f"- Tempo report: {summary['timings']['report_seconds']:.2f}s",
        f"- Stato run: {summary['run_status']}",
        f"- Eventi pending: {summary['processing']['pending_after']}",
        f"- Batch completati: {summary['processing']['batches_completed']}",
        "",
        "## Diagnostica scalabilita relation candidates",
        f"- Candidate raw prima del pruning: {summary['relation_scaling']['raw_pairs']}",
        f"- Candidate dopo pruning: {summary['relation_scaling']['kept_pairs']}",
        f"- Candidate pruned: {summary['relation_scaling']['pruned_pairs']}",
        f"- Max candidates per thread: {summary['relation_scaling']['relation_max_candidates_per_thread']}",
        f"- Relation window days: {summary['relation_scaling']['relation_window_days']}",
        f"- Top pruning reasons: {json.dumps(summary['relation_scaling']['pruning_reasons'], ensure_ascii=False)}",
        f"- Canonical terms penalizzati: {json.dumps(summary['relation_scaling']['penalized_canonical_terms'], ensure_ascii=False)}",
        "",
        "## Confronto Short vs Long",
        "| metrica | short | long |",
        "| --- | ---: | ---: |",
    ]
    keys = [
        "events",
        "threads",
        "macro_threads",
        "largest_macro",
        "relation_candidates",
        "promoted_relations",
        "rejected_relations",
        "useful_unassigned_thread_rate",
        "isolated_thread_rate",
        "macro_heterogeneity_score",
        "false_macro_prevention_rate",
    ]
    for key in keys:
        lines.append(f"| {key} | {short_metrics.get(key)} | {long_metrics.get(key)} |")
    lines.extend(_append_incremental_diagnostics(summary))
    return "\n".join(lines).strip()


async def _run(args: argparse.Namespace) -> dict:
    input_path, media_dir = _resolve_input(Path(args.input))
    output_path = Path(args.output)
    timings: dict[str, float] = {}
    checkpoint = _load_checkpoint(args.project_id) if args.resume else {}
    checkpoint.update(
        {
            "project_id": args.project_id,
            "input": str(input_path),
            "output": str(output_path),
            "resume_enabled": bool(args.resume),
            "started_at": checkpoint.get("started_at") or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
    )

    started = time.perf_counter()
    raw_text = _read_text(input_path)
    parsed = parse_whatsapp_export(
        raw_text,
        project_id=args.project_id,
        source_name=args.source_name,
        timezone=args.timezone,
        media_dir=media_dir if args.detect_media else None,
        analyze_attachments=args.analyze_media and not args.skip_media_analysis,
    )
    if args.max_events and args.max_events > 0:
        parsed.events = parsed.events[: args.max_events]
    import_result = await ingest_events_batch(args.project_id, parsed.events)
    timings["import_seconds"] = time.perf_counter() - started
    checkpoint["last_import"] = {
        "parsed": len(parsed.events),
        "accepted": import_result["accepted"],
        "duplicates": import_result["duplicates"],
        "failed": import_result["failed"],
        "media_detected": parsed.media_detected,
        "media_analyzed": parsed.media_analyzed,
        "media_ignored": parsed.media_ignored,
    }
    _save_checkpoint(args.project_id, checkpoint)

    started = time.perf_counter()
    processed_total = 0
    failed_total = 0
    batches_completed = 0
    max_batches_reached = False
    while True:
        if args.verbose:
            batch_result = await process_pending_events(
                args.project_id,
                limit=args.process_batch_size,
                rebuild_threads=False,
            )
        else:
            with contextlib.redirect_stdout(io.StringIO()):
                batch_result = await process_pending_events(
                    args.project_id,
                    limit=args.process_batch_size,
                    rebuild_threads=False,
                )
        processed_total += batch_result["processed"]
        failed_total += batch_result["failed"]
        batches_completed += 1
        checkpoint["last_processing"] = {
            "processed_total": processed_total,
            "failed_total": failed_total,
            "pending_remaining": batch_result["pending_remaining"],
            "batches_completed": batches_completed,
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        _save_checkpoint(args.project_id, checkpoint)
        print(
            json.dumps(
                {
                    "phase": "processing",
                    "processed_total": processed_total,
                    "failed_total": failed_total,
                    "pending_remaining": batch_result["pending_remaining"],
                    "batch": batches_completed,
                },
                ensure_ascii=True,
            ),
            flush=True,
        )
        if batch_result["pending_remaining"] == 0:
            break
        if args.max_process_events and processed_total >= args.max_process_events:
            break
        if args.max_batches and batches_completed >= args.max_batches:
            max_batches_reached = True
            break
    timings["processing_seconds"] = time.perf_counter() - started

    if args.incremental or args.force_full_rebuild:
        rebuild_metrics = await incremental_rebuild(
            args.project_id,
            relation_window_days=args.relation_window_days,
            relation_max_candidates_per_thread=args.relation_max_candidates_per_thread,
            force_full_rebuild=args.force_full_rebuild,
        )
        timings.update(rebuild_metrics.pop("timings", {}))
        relation_stats = dict(rebuild_metrics.pop("relation_stats", {}))
        incremental_metrics = rebuild_metrics
    else:
        timings.update(
            await _rebuild_profile_macro_relations(
                args.project_id,
                relation_window_days=args.relation_window_days,
                relation_max_candidates_per_thread=args.relation_max_candidates_per_thread,
            )
        )
        relation_stats = dict(timings.pop("relation_stats", {}))
        incremental_metrics = {
            "mode": "full",
            "full_rebuild": True,
            "full_rebuild_avoided": False,
            "rebuild_reason": "legacy full rebuild (flag --incremental assente)",
            "events_processed_this_run": processed_total,
            "dirty_threads": None,
            "dirty_canonical_terms": None,
            "dirty_relation_pairs": None,
            "relation_pairs_recalculated": relation_stats.get("kept_pairs"),
            "relation_pairs_reused": 0,
            "macros_rebuilt": None,
            "macros_reused": None,
            "canonical_distribution": [],
            "broad_canonical_terms": [],
            "weak_context_terms": [],
        }

    snapshot_id = None
    if args.create_snapshot:
        snapshot = await create_snapshot(args.project_id)
        snapshot_id = snapshot.snapshot_id

    started = time.perf_counter()
    report = await build_daily_report(args.project_id, report_mode=args.report_mode)
    timings["report_seconds"] = time.perf_counter() - started

    events = await list_events(args.project_id)
    state = await load_state(args.project_id)
    long_metrics = _metrics_for_state(args.project_id, state, len(events))

    short_state = await load_state(args.short_project_id)
    short_events = await list_events(args.short_project_id)
    short_metrics = _metrics_for_state(args.short_project_id, short_state, len(short_events))

    summary = {
        "project_id": args.project_id,
        "input_path": str(input_path),
        "media_dir": str(media_dir) if media_dir else None,
        "import": {
            "parsed": len(parsed.events),
            "accepted": import_result["accepted"],
            "duplicates": import_result["duplicates"],
            "ignored": parsed.ignored,
            "failed": import_result["failed"],
            "media_detected": parsed.media_detected,
            "media_analyzed": parsed.media_analyzed,
            "media_text_extracted": parsed.media_text_extracted,
            "media_ignored": parsed.media_ignored,
        },
        "processing": {
            "processed": processed_total,
            "failed": failed_total,
            "pending_after": len([event for event in events if event.processed_status == "pending"]),
            "batches_completed": batches_completed,
            "max_batches_reached": max_batches_reached,
        },
        "timings": timings,
        "run_status": _run_status(
            len([event for event in events if event.processed_status == "pending"]),
            max_batches_reached,
        ),
        "checkpoint_path": str(_checkpoint_path(args.project_id)),
        "relation_scaling": relation_stats,
        "incremental": incremental_metrics,
        "snapshot_id": snapshot_id,
        "short_metrics": short_metrics,
        "long_metrics": long_metrics,
        "report_path": str(output_path),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(_append_long_diagnostics(report.markdown, summary, short_metrics, long_metrics), encoding="utf-8")
    checkpoint["last_report"] = {
        "path": str(output_path),
        "run_status": summary["run_status"],
        "pending_after": summary["processing"]["pending_after"],
        "relation_scaling": relation_stats,
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    checkpoint["incremental"] = {
        "incremental_mode": bool(args.incremental),
        "force_full_rebuild": bool(args.force_full_rebuild),
        "mode": incremental_metrics.get("mode"),
        "full_rebuild_avoided": incremental_metrics.get("full_rebuild_avoided"),
        "rebuild_reason": incremental_metrics.get("rebuild_reason"),
        "events_processed_this_run": incremental_metrics.get("events_processed_this_run"),
        "dirty_threads": incremental_metrics.get("dirty_threads"),
        "dirty_canonical_terms": incremental_metrics.get("dirty_canonical_terms"),
        "dirty_relation_pairs": incremental_metrics.get("dirty_relation_pairs"),
        "relation_pairs_recalculated": incremental_metrics.get("relation_pairs_recalculated"),
        "relation_pairs_reused": incremental_metrics.get("relation_pairs_reused"),
        "macros_rebuilt": incremental_metrics.get("macros_rebuilt"),
        "macros_reused": incremental_metrics.get("macros_reused"),
    }
    checkpoint["timings"] = timings
    checkpoint["thread_metrics"] = {
        "threads": long_metrics.get("threads"),
        "macro_threads": long_metrics.get("macro_threads"),
        "largest_macro": long_metrics.get("largest_macro"),
    }
    checkpoint["relation_metrics"] = {
        "relation_candidates": long_metrics.get("relation_candidates"),
        "promoted_relations": long_metrics.get("promoted_relations"),
        "rejected_relations": long_metrics.get("rejected_relations"),
        "stored_relations": long_metrics.get("stored_relations"),
    }
    checkpoint["status"] = summary["run_status"]
    checkpoint["last_processed_event_id"] = (events[-1].event_id if events else None)
    _save_checkpoint(args.project_id, checkpoint)
    return summary


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run long offline WhatsApp export validation.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID)
    parser.add_argument("--short-project-id", default=DEFAULT_SHORT_PROJECT_ID)
    parser.add_argument("--source-name", default="whatsapp-long-export-offline")
    parser.add_argument("--timezone", default="Europe/Rome")
    parser.add_argument("--report-mode", choices=("OPERATIVE_ONLY", "OPERATIVE_PLUS_LOGISTICS", "FULL_CONTEXT"), default="OPERATIVE_ONLY")
    parser.add_argument("--process-batch-size", type=int, default=100)
    parser.add_argument("--max-events", type=int, default=0)
    parser.add_argument("--max-process-events", type=int, default=0)
    parser.add_argument("--max-batches", type=int, default=0)
    parser.add_argument("--resume", action="store_true", default=False)
    parser.add_argument("--incremental", action="store_true", default=False)
    parser.add_argument("--force-full-rebuild", action="store_true", default=False)
    parser.add_argument("--detect-media", action="store_true", default=True)
    parser.add_argument("--analyze-media", action="store_true", default=False)
    parser.add_argument("--skip-media-analysis", action="store_true", default=True)
    parser.add_argument("--relation-window-days", type=int, default=21)
    parser.add_argument("--relation-max-candidates-per-thread", type=int, default=40)
    parser.add_argument("--create-snapshot", action="store_true", default=False)
    parser.add_argument("--verbose", action="store_true", default=False)
    parser.add_argument("--force-exit", action="store_true", default=False)
    return parser


def main() -> int:
    parser = _parser()
    args = parser.parse_args()
    try:
        summary = asyncio.run(_run(args))
    except FileNotFoundError as exc:
        parser.error(str(exc))
        return 2
    print(json.dumps(summary, ensure_ascii=True, indent=2))
    sys.stdout.flush()
    if args.force_exit:
        os._exit(0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
