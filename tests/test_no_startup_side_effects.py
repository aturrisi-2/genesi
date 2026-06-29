import asyncio
import builtins
import importlib
import os
import subprocess
import sys
from pathlib import Path

import pytest


FROZEN_IMPORT_SAFE_MODULES = [
    "core.training_engine",
    "core.training_autopilot",
    "core.lab_feedback_cycle",
    "core.auto_evolution_engine",
    "core.moltbook_service",
    "core.instagram_publisher",
    "lab.supervisor",
]


FROZEN_FLAGS = {
    "training_autopilot": "ENABLE_TRAINING_AUTOPILOT",
    "moltbook_autopublish": "ENABLE_MOLTBOOK_AUTOPUBLISH",
    "instagram_posting": "ENABLE_INSTAGRAM_POSTING",
    "instagram_reels": "ENABLE_INSTAGRAM_REELS",
    "instagram_comment_replies": "ENABLE_INSTAGRAM_COMMENT_REPLIES",
    "morning_greetings": "ENABLE_MORNING_GREETINGS",
    "birthday_greetings": "ENABLE_BIRTHDAY_GREETINGS",
}


RISKY_ROOTS = ("memory", "data", "lab", "static/ig_posts")


def _is_risky_path(value) -> bool:
    try:
        path = str(value)
    except Exception:
        return False
    normalized = path.replace("\\", "/").lstrip("./")
    return any(
        normalized == root
        or normalized.startswith(root + "/")
        or ("/" + root + "/") in normalized
        for root in RISKY_ROOTS
    )


@pytest.fixture()
def no_startup_side_effects(monkeypatch):
    calls: list[str] = []

    # Known core boot prerequisites create their own directories at import time.
    # This phase guards frozen/legacy modules from adding extra side effects; it
    # does not refactor the existing storage/auth import behavior.
    importlib.import_module("core.storage")
    importlib.import_module("auth.config")
    importlib.import_module("core.fallback_engine")
    importlib.import_module("core.document_memory")

    monkeypatch.setenv("GENESI_PASSIVE_MODE", "true")
    for env_name in FROZEN_FLAGS.values():
        monkeypatch.setenv(env_name, "false")

    def blocked(label):
        def _inner(*args, **kwargs):
            calls.append(label)
            raise AssertionError(f"startup side effect blocked: {label}")

        return _inner

    monkeypatch.setattr(asyncio, "create_task", blocked("asyncio.create_task"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", blocked("asyncio.create_subprocess_exec"))
    monkeypatch.setattr(asyncio, "create_subprocess_shell", blocked("asyncio.create_subprocess_shell"))
    monkeypatch.setattr(subprocess, "Popen", blocked("subprocess.Popen"))
    monkeypatch.setattr(subprocess, "run", blocked("subprocess.run"))
    monkeypatch.setattr(subprocess, "call", blocked("subprocess.call"))
    monkeypatch.setattr(subprocess, "check_call", blocked("subprocess.check_call"))
    monkeypatch.setattr(subprocess, "check_output", blocked("subprocess.check_output"))

    original_open = builtins.open

    def guarded_open(file, mode="r", *args, **kwargs):
        if any(flag in mode for flag in ("w", "a", "x", "+")) and _is_risky_path(file):
            calls.append(f"write:{file}")
            raise AssertionError(f"startup write blocked: {file}")
        return original_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)

    original_makedirs = os.makedirs

    def guarded_makedirs(name, *args, **kwargs):
        if _is_risky_path(name):
            calls.append(f"makedirs:{name}")
            raise AssertionError(f"startup makedirs blocked: {name}")
        return original_makedirs(name, *args, **kwargs)

    monkeypatch.setattr(os, "makedirs", guarded_makedirs)

    original_write_text = Path.write_text
    original_write_bytes = Path.write_bytes
    original_mkdir = Path.mkdir
    original_unlink = Path.unlink
    original_replace = Path.replace
    original_rename = Path.rename

    def guarded_write_text(self, *args, **kwargs):
        if _is_risky_path(self):
            calls.append(f"write_text:{self}")
            raise AssertionError(f"startup write_text blocked: {self}")
        return original_write_text(self, *args, **kwargs)

    def guarded_write_bytes(self, *args, **kwargs):
        if _is_risky_path(self):
            calls.append(f"write_bytes:{self}")
            raise AssertionError(f"startup write_bytes blocked: {self}")
        return original_write_bytes(self, *args, **kwargs)

    def guarded_mkdir(self, *args, **kwargs):
        if _is_risky_path(self):
            calls.append(f"mkdir:{self}")
            raise AssertionError(f"startup mkdir blocked: {self}")
        return original_mkdir(self, *args, **kwargs)

    def guarded_unlink(self, *args, **kwargs):
        if _is_risky_path(self):
            calls.append(f"unlink:{self}")
            raise AssertionError(f"startup unlink blocked: {self}")
        return original_unlink(self, *args, **kwargs)

    def guarded_replace(self, *args, **kwargs):
        if _is_risky_path(self) or (args and _is_risky_path(args[0])):
            calls.append(f"replace:{self}")
            raise AssertionError(f"startup replace blocked: {self}")
        return original_replace(self, *args, **kwargs)

    def guarded_rename(self, *args, **kwargs):
        if _is_risky_path(self) or (args and _is_risky_path(args[0])):
            calls.append(f"rename:{self}")
            raise AssertionError(f"startup rename blocked: {self}")
        return original_rename(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", guarded_write_text)
    monkeypatch.setattr(Path, "write_bytes", guarded_write_bytes)
    monkeypatch.setattr(Path, "mkdir", guarded_mkdir)
    monkeypatch.setattr(Path, "unlink", guarded_unlink)
    monkeypatch.setattr(Path, "replace", guarded_replace)
    monkeypatch.setattr(Path, "rename", guarded_rename)

    try:
        import httpx

        monkeypatch.setattr(httpx.Client, "request", blocked("httpx.Client.request"))
        monkeypatch.setattr(httpx.Client, "get", blocked("httpx.Client.get"))
        monkeypatch.setattr(httpx.Client, "post", blocked("httpx.Client.post"))
        monkeypatch.setattr(httpx.AsyncClient, "request", blocked("httpx.AsyncClient.request"))
        monkeypatch.setattr(httpx.AsyncClient, "get", blocked("httpx.AsyncClient.get"))
        monkeypatch.setattr(httpx.AsyncClient, "post", blocked("httpx.AsyncClient.post"))
    except Exception:
        pass

    return calls


@pytest.fixture()
def no_external_startup_work(monkeypatch):
    calls: list[str] = []

    monkeypatch.setenv("GENESI_PASSIVE_MODE", "true")
    for env_name in FROZEN_FLAGS.values():
        monkeypatch.setenv(env_name, "false")

    def blocked(label):
        def _inner(*args, **kwargs):
            calls.append(label)
            raise AssertionError(f"startup side effect blocked: {label}")

        return _inner

    monkeypatch.setattr(asyncio, "create_task", blocked("asyncio.create_task"))
    monkeypatch.setattr(asyncio, "create_subprocess_exec", blocked("asyncio.create_subprocess_exec"))
    monkeypatch.setattr(asyncio, "create_subprocess_shell", blocked("asyncio.create_subprocess_shell"))
    monkeypatch.setattr(subprocess, "Popen", blocked("subprocess.Popen"))
    monkeypatch.setattr(subprocess, "run", blocked("subprocess.run"))
    monkeypatch.setattr(subprocess, "call", blocked("subprocess.call"))
    monkeypatch.setattr(subprocess, "check_call", blocked("subprocess.check_call"))
    monkeypatch.setattr(subprocess, "check_output", blocked("subprocess.check_output"))

    original_open = builtins.open

    def guarded_open(file, mode="r", *args, **kwargs):
        if any(flag in mode for flag in ("w", "a", "x", "+")) and _is_risky_path(file):
            calls.append(f"write:{file}")
            raise AssertionError(f"startup write blocked: {file}")
        return original_open(file, mode, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", guarded_open)

    original_makedirs = os.makedirs
    original_mkdir = Path.mkdir

    def no_op_risky_makedirs(name, *args, **kwargs):
        if _is_risky_path(name):
            return None
        return original_makedirs(name, *args, **kwargs)

    def no_op_risky_mkdir(self, *args, **kwargs):
        if _is_risky_path(self):
            return None
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(os, "makedirs", no_op_risky_makedirs)
    monkeypatch.setattr(Path, "mkdir", no_op_risky_mkdir)

    try:
        import httpx

        monkeypatch.setattr(httpx.Client, "request", blocked("httpx.Client.request"))
        monkeypatch.setattr(httpx.Client, "get", blocked("httpx.Client.get"))
        monkeypatch.setattr(httpx.Client, "post", blocked("httpx.Client.post"))
        monkeypatch.setattr(httpx.AsyncClient, "request", blocked("httpx.AsyncClient.request"))
        monkeypatch.setattr(httpx.AsyncClient, "get", blocked("httpx.AsyncClient.get"))
        monkeypatch.setattr(httpx.AsyncClient, "post", blocked("httpx.AsyncClient.post"))
    except Exception:
        pass

    return calls


def _fresh_import(module_name: str):
    sys.modules.pop(module_name, None)
    return importlib.import_module(module_name)


def test_frozen_legacy_modules_import_without_startup_side_effects(no_startup_side_effects):
    for module_name in FROZEN_IMPORT_SAFE_MODULES:
        _fresh_import(module_name)

    assert no_startup_side_effects == []


def test_main_import_does_not_start_frozen_background_work(no_external_startup_work):
    pytest.importorskip("jinja2")

    _fresh_import("main")

    assert no_external_startup_work == []


def test_frozen_automation_flags_default_off(monkeypatch):
    from core import automation_flags

    monkeypatch.setattr(automation_flags, "_OVERRIDES_PATH", Path("/tmp/no-startup-side-effects-flags.json"))
    monkeypatch.setenv("GENESI_PASSIVE_MODE", "true")
    for env_name in FROZEN_FLAGS.values():
        monkeypatch.delenv(env_name, raising=False)

    for flag_name in FROZEN_FLAGS:
        assert automation_flags.flag_enabled(flag_name) is False


def test_main_keeps_frozen_background_tasks_behind_flags():
    source = Path("main.py").read_text(encoding="utf-8")

    assert '"TRAINING_AUTOPILOT"' in source
    assert 'automation_flags.flag_enabled("training_autopilot")' in source
    assert '"MOLTBOOK_HEARTBEAT"' in source
    assert 'automation_flags.flag_enabled("moltbook_autopublish")' in source
    assert '"BIRTHDAY_SCHEDULER"' in source
    assert 'automation_flags.flag_enabled("birthday_greetings")' in source
    assert '"IG_PUBLISHER"' in source
    assert 'automation_flags.flag_enabled("instagram_posting")' in source
    assert '"LAB_CYCLE_SCHEDULER"' in source
    assert '"EVOLUTION_SCHEDULER"' in source
    assert "not passive" in source
