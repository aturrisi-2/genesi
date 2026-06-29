import importlib
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _runtime_files_snapshot() -> tuple[tuple[str, int, int], ...]:
    rows: list[tuple[str, int, int]] = []
    for root_name in ("memory", "data"):
        root = REPO_ROOT / root_name
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if path.is_file():
                try:
                    stat = path.stat()
                except FileNotFoundError:
                    continue
                rows.append((str(path.relative_to(REPO_ROOT)), stat.st_size, stat.st_mtime_ns))
    return tuple(rows)


def _fresh_import(module_name: str):
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def test_storage_import_initializes_only_configured_cwd_memory(monkeypatch, tmp_path):
    before = _runtime_files_snapshot()
    monkeypatch.chdir(tmp_path)

    module = _fresh_import("core.storage")

    expected_dirs = {
        tmp_path / "memory" / "short_term_chat",
        tmp_path / "memory" / "long_term_profile",
        tmp_path / "memory" / "relational_state",
        tmp_path / "memory" / "semantic_facts",
        tmp_path / "memory" / "episodes",
    }
    assert expected_dirs <= {path for path in tmp_path.rglob("*") if path.is_dir()}
    assert module.storage.base_path == "memory"
    assert _runtime_files_snapshot() == before


def test_auth_config_import_initializes_only_configured_cwd_auth_dir(monkeypatch, tmp_path):
    before = _runtime_files_snapshot()
    monkeypatch.chdir(tmp_path)

    module = _fresh_import("auth.config")

    assert module.DB_DIR == Path("data/auth")
    assert (tmp_path / "data" / "auth").is_dir()
    assert str(module.DATABASE_URL).endswith("data/auth/genesi_auth.db")
    assert _runtime_files_snapshot() == before


def test_fallback_engine_import_loads_legacy_records_from_configured_cwd(monkeypatch, tmp_path):
    before = _runtime_files_snapshot()
    fallback_dir = tmp_path / "memory" / "admin"
    fallback_dir.mkdir(parents=True)
    (fallback_dir / "fallbacks.json").write_text(
        json.dumps([
            {
                "id": "legacy-1",
                "timestamp": "2026-01-01T00:00:00",
                "user_message": "ciao",
                "fallback_type": "legacy",
                "possible_solution": "ok",
            }
        ]),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)

    module = _fresh_import("core.fallback_engine")
    summary = module.fallback_engine.get_summary()

    assert (tmp_path / "memory" / "admin").is_dir()
    assert len(summary) == 1
    assert summary[0]["count"] == 1
    assert summary[0]["type"] == "legacy"
    assert _runtime_files_snapshot() == before


def test_document_memory_import_is_confined_to_configured_cwd(monkeypatch, tmp_path):
    before = _runtime_files_snapshot()
    monkeypatch.chdir(tmp_path)

    module = _fresh_import("core.document_memory")

    assert module._DOCUMENTS_DIR == "memory/documents"
    assert (tmp_path / "memory" / "documents").is_dir()
    assert module.load_document("missing") is None
    assert _runtime_files_snapshot() == before


def test_reminder_engine_import_is_confined_to_configured_cwd(monkeypatch, tmp_path):
    before = _runtime_files_snapshot()
    monkeypatch.chdir(tmp_path)

    module = _fresh_import("core.reminder_engine")

    assert module.reminder_engine.reminders_dir == Path("data/reminders")
    assert (tmp_path / "data" / "reminders").is_dir()
    assert module.reminder_engine._load_reminders("missing-user") == []
    assert _runtime_files_snapshot() == before

