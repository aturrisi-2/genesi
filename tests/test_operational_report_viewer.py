"""HTML viewer for the operational daily report.

`GET /operational-report/{project_id}/latest` → print-friendly HTML rendered from
the same build_daily_report markdown as the JSON endpoint. Read-only, no auth
beyond the existing operational routes, no store mutation.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.operational_memory.models import (
    Issue, LifecycleHistoryEntry, LifecycleState, OperationalState, OperationalTask,
)

PROJECT = "viewer-proj"


def _lc(cat, status):
    return LifecycleState(category=cat, current_status=status, confidence="high",
                          status_reason="r", evidence_event_ids=["e1"],
                          lifecycle_history=[LifecycleHistoryEntry(status=status, changed_at="2026-06-23T08:00:00+00:00")])


def _seed():
    return OperationalState(
        project_id=PROJECT,
        tasks=[OperationalTask(id="t1", text="verificare quadro QF-01 sala tecnica",
                               source="m", source_event_id="e1", lifecycle=_lc("task", "open"))],
        issues=[Issue(id="i1", text="intercetti vela chiusi sala T7 L01",
                      source="m", source_event_id="e2", lifecycle=_lc("issue", "open"))],
    )


@pytest.fixture
def app(monkeypatch, tmp_path):
    from core.operational_memory import state_store, snapshot_store, event_store
    import api.operational as operational_api
    monkeypatch.setattr(state_store, "_BASE_DIR", tmp_path / "state")
    monkeypatch.setattr(snapshot_store, "_LIFECYCLE_BASE_DIR", tmp_path / "lc")
    monkeypatch.setattr(event_store, "_BASE_DIR", tmp_path / "events")
    asyncio.run(state_store.save_state(PROJECT, _seed()))
    application = FastAPI()
    application.include_router(operational_api.router)
    return application


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_report_viewer_returns_html(app):
    async with _client(app) as c:
        r = await c.get(f"/operational-report/{PROJECT}/latest")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert "<html" in body.lower()
    assert "Aggiornamento giornaliero" in body
    assert "window.print()" in body                 # print button
    assert f"/operational-state/{PROJECT}/daily-report" in body  # JSON link


@pytest.mark.asyncio
async def test_report_viewer_contains_sections(app):
    async with _client(app) as c:
        r = await c.get(f"/operational-report/{PROJECT}/latest")
    body = r.text
    # Markdown rendered to HTML headings/content (sections present in the report).
    assert "Task" in body and "aperti" in body.lower()
    assert "intercetti vela" in body.lower() or "T7" in body   # issue content rendered


@pytest.mark.asyncio
async def test_json_endpoint_unchanged(app):
    async with _client(app) as c:
        r = await c.get(f"/operational-state/{PROJECT}/daily-report")
    assert r.status_code == 200
    body = r.json()
    assert "markdown" in body and body["title"]      # still JSON, with markdown field


@pytest.mark.asyncio
async def test_missing_project_no_crash(app):
    async with _client(app) as c:
        r = await c.get("/operational-report/does-not-exist-xyz/latest")
    assert r.status_code == 200                       # empty report, no crash
    assert "<html" in r.text.lower()
