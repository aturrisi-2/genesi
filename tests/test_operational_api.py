from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.operational_memory.models import (
    Decision,
    Issue,
    LifecycleHistoryEntry,
    LifecycleState,
    OperationalLifecycleSnapshot,
    OperationalQuestion,
    OperationalState,
    OperationalTask,
    OperationalThread,
    SnapshotDelta,
)


PROJECT = "api-proj"


def _lc(category, status):
    return LifecycleState(
        category=category, current_status=status, status_reason="r", evidence_event_ids=["ev1"],
        lifecycle_history=[LifecycleHistoryEntry(status=status, changed_at="2026-06-12T08:00:00+00:00")],
    )


def _seed_state() -> OperationalState:
    snap = OperationalLifecycleSnapshot(project_id=PROJECT, generated_at="2026-06-19T10:00:00+00:00")
    snap.snapshot_delta = SnapshotDelta(newly_resolved=["[issue] issue i2"], newly_opened=["[task] task t1"])
    return OperationalState(
        project_id=PROJECT,
        tasks=[OperationalTask(id="t1", text="task t1", source="m", source_event_id="e1", lifecycle=_lc("task", "open")),
               OperationalTask(id="t2", text="task t2", source="m", source_event_id="e2", lifecycle=_lc("task", "completed"))],
        issues=[Issue(id="i1", text="issue i1", source="m", source_event_id="e3", lifecycle=_lc("issue", "open")),
                Issue(id="i2", text="issue i2", source="m", source_event_id="e4", lifecycle=_lc("issue", "resolved"))],
        decisions=[Decision(id="d1", text="decision d1", source="m", source_event_id="e5", lifecycle=_lc("decision", "confirmed"))],
        open_questions=[OperationalQuestion(id="q1", text="question q1", source="m", source_event_id="e6", lifecycle=_lc("question", "open"))],
        threads=[OperationalThread(thread_id="th1", project_id=PROJECT, title="thread one",
                                   started_at="2026-06-12T08:00:00+00:00", last_updated_at="2026-06-12T09:00:00+00:00",
                                   project_impact_score=80, related_event_ids=["e1", "e3"])],
        lifecycle_snapshot=snap,
    )


@pytest.fixture
def app(monkeypatch, tmp_path):
    from core.operational_memory import state_store, snapshot_store, event_store
    import api.operational as operational_api

    monkeypatch.setattr(state_store, "_BASE_DIR", tmp_path / "state")
    monkeypatch.setattr(snapshot_store, "_LIFECYCLE_BASE_DIR", tmp_path / "lc")
    monkeypatch.setattr(event_store, "_BASE_DIR", tmp_path / "events")
    asyncio.run(state_store.save_state(PROJECT, _seed_state()))

    application = FastAPI()
    application.include_router(operational_api.router)
    return application


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _url(suffix: str) -> str:
    return f"/api/operational/projects/{PROJECT}{suffix}"


@pytest.mark.asyncio
async def test_briefing_endpoint(app):
    async with _client(app) as c:
        r = await c.get(_url("/briefing"))
    assert r.status_code == 200
    body = r.json()
    assert body["headline"] and body["rows"] and body["synthesis"]
    assert any(row["key"] == "open_tasks" for row in body["rows"])


@pytest.mark.asyncio
async def test_digest_endpoint(app):
    async with _client(app) as c:
        r = await c.get(_url("/digest"))
    assert r.status_code == 200
    assert "task aperti" in r.json()["headline"]


@pytest.mark.asyncio
async def test_snapshot_endpoint(app):
    async with _client(app) as c:
        r = await c.get(_url("/snapshot"))
    assert r.status_code == 200
    assert r.json()["project_id"] == PROJECT


@pytest.mark.asyncio
async def test_snapshot_404_when_missing(app):
    async with _client(app) as c:
        r = await c.get("/api/operational/projects/does-not-exist/snapshot")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delta_endpoint(app):
    async with _client(app) as c:
        r = await c.get(_url("/delta"))
    assert r.status_code == 200
    assert "[issue] issue i2" in r.json()["newly_resolved"]


@pytest.mark.asyncio
async def test_ask_endpoint_dispatch(app):
    async with _client(app) as c:
        r = await c.post(_url("/ask"), json={"query": "cosa resta da fare?"})
    assert r.status_code == 200
    body = r.json()
    assert body["intent"] == "open_tasks" and body["count"] == 1


@pytest.mark.asyncio
async def test_ask_endpoint_briefing(app):
    async with _client(app) as c:
        r = await c.post(_url("/ask"), json={"query": "fammi il punto"})
    assert r.status_code == 200
    assert r.json()["intent"] == "briefing"


@pytest.mark.asyncio
async def test_ask_empty_query_400(app):
    async with _client(app) as c:
        r = await c.post(_url("/ask"), json={"query": "   "})
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_items_filtered(app):
    async with _client(app) as c:
        r = await c.get(_url("/items"), params={"category": "task", "status": "open"})
    assert r.status_code == 200
    assert {it["item_id"] for it in r.json()} == {"t1"}


@pytest.mark.asyncio
async def test_items_all(app):
    async with _client(app) as c:
        r = await c.get(_url("/items"))
    assert r.status_code == 200
    assert len(r.json()) == 6  # 2 tasks + 2 issues + 1 decision + 1 question


@pytest.mark.asyncio
async def test_threads_endpoint(app):
    async with _client(app) as c:
        r = await c.get(_url("/threads"))
    assert r.status_code == 200
    assert r.json()[0]["thread_id"] == "th1"


@pytest.mark.asyncio
async def test_report_endpoint_markdown(app):
    async with _client(app) as c:
        r = await c.get(_url("/report"))
    assert r.status_code == 200
    assert "text/markdown" in r.headers["content-type"]
    assert "Briefing operativo" in r.text


@pytest.mark.asyncio
async def test_report_download_attachment(app):
    async with _client(app) as c:
        r = await c.get(_url("/report/download"))
    assert r.status_code == 200
    assert "attachment" in r.headers.get("content-disposition", "")
    assert ".md" in r.headers.get("content-disposition", "")


@pytest.mark.asyncio
async def test_ingest_test_endpoint(app):
    from core.operational_memory.models import OperationalEvent

    ev = OperationalEvent(event_id="newev1", project_id=PROJECT, sender="x", content="ciao", processed_status="pending")
    async with _client(app) as c:
        r = await c.post(_url("/ingest-test"), json={"events": [ev.model_dump()]})
    assert r.status_code == 200
    assert r.json()["accepted"] == 1


@pytest.mark.asyncio
async def test_resolved_not_reported_as_active_via_items(app):
    async with _client(app) as c:
        r = await c.get(_url("/items"), params={"category": "issue", "status": "open"})
    ids = {it["item_id"] for it in r.json()}
    assert "i2" not in ids and "i1" in ids


# --- FASE 7: chat presence + report storage endpoints --- #


@pytest.fixture
def app_with_reports(app, monkeypatch, tmp_path):
    from core.operational_memory import report_store
    monkeypatch.setattr(report_store, "_BASE_DIR", tmp_path / "reports")
    return app


@pytest.mark.asyncio
async def test_chat_endpoint_silent_for_normal_message(app_with_reports):
    # No-op updater so the endpoint does not run the heavy pipeline/LLM.
    import core.operational_memory.chat_presence as cp

    async def noop(message):
        return None

    orig = cp.silent_update
    cp.silent_update = noop
    try:
        async with _client(app_with_reports) as c:
            body = {"message": {"project_id": PROJECT, "message_id": "cm1", "text": "ragazzi a che ora?"}}
            r = await c.post(_url("/chat"), json=body)
    finally:
        cp.silent_update = orig
    assert r.status_code == 200
    assert r.json()["silent"] is True and r.json()["reply"] is None


@pytest.mark.asyncio
async def test_chat_endpoint_reply_on_invocation(app_with_reports):
    import core.operational_memory.chat_presence as cp

    async def noop(message):
        return None

    orig = cp.silent_update
    cp.silent_update = noop
    try:
        async with _client(app_with_reports) as c:
            body = {"message": {"project_id": PROJECT, "message_id": "cm2", "text": "Genesi, fammi il punto"}}
            r = await c.post(_url("/chat"), json=body)
    finally:
        cp.silent_update = orig
    assert r.status_code == 200
    payload = r.json()
    assert payload["silent"] is False
    assert payload["reply"]["report_url"] and "Quadro operativo" in payload["reply"]["reply_markdown"]


@pytest.mark.asyncio
async def test_chat_flat_body_inherits_project_id(app_with_reports):
    # Flat body (no "message" wrapper, no project_id) -> project_id from path.
    import core.operational_memory.chat_presence as cp

    async def noop(message):
        return None

    orig = cp.silent_update
    cp.silent_update = noop
    try:
        async with _client(app_with_reports) as c:
            normal = await c.post(_url("/chat"), json={"message_id": "flat-1", "sender": "t", "text": "messaggio normale"})
            invoked = await c.post(_url("/chat"), json={"message_id": "flat-2", "text": "Genesi, fammi il punto"})
            missing_id = await c.post(_url("/chat"), json={"text": "Genesi, fammi il punto"})
    finally:
        cp.silent_update = orig
    assert normal.status_code == 200 and normal.json()["silent"] is True
    assert invoked.status_code == 200 and invoked.json()["silent"] is False
    assert invoked.json()["reply"]["report_url"]
    assert missing_id.status_code == 400  # message_id required


@pytest.mark.asyncio
async def test_chat_nested_body_still_works(app_with_reports):
    import core.operational_memory.chat_presence as cp

    async def noop(message):
        return None

    orig = cp.silent_update
    cp.silent_update = noop
    try:
        async with _client(app_with_reports) as c:
            r = await c.post(_url("/chat"), json={"message": {"project_id": PROJECT, "message_id": "nest-1", "text": "ciao"}})
    finally:
        cp.silent_update = orig
    assert r.status_code == 200 and r.json()["silent"] is True


@pytest.mark.asyncio
async def test_stored_report_get_and_download(app_with_reports):
    from core.operational_memory.report_store import save_report

    rep = save_report(PROJECT, "# test report\n\ncontenuto")
    async with _client(app_with_reports) as c:
        r1 = await c.get(_url(f"/reports/{rep.report_id}"))
        r2 = await c.get(_url(f"/reports/{rep.report_id}/download"))
        r3 = await c.get(_url("/reports/does-not-exist"))
    assert r1.status_code == 200 and r1.json()["report_id"] == rep.report_id
    assert r2.status_code == 200 and "attachment" in r2.headers.get("content-disposition", "")
    assert r3.status_code == 404
