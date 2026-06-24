"""Report Viewer V2 — structured cards + media thumbnails + internal diary page.

Validates layout V2 + the secure thumbnail endpoint. No env/live/store mutation.
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.operational_memory.models import (
    Issue, LifecycleHistoryEntry, LifecycleState, OperationalEvent, OperationalState, OperationalTask,
)

PROJECT = "viewer2-proj"


def _lc(cat, status):
    return LifecycleState(category=cat, current_status=status, confidence="high",
                          status_reason="r", evidence_event_ids=["e1"],
                          lifecycle_history=[LifecycleHistoryEntry(status=status, changed_at="2026-06-24T08:00:00+00:00")])


def _seed_state():
    return OperationalState(
        project_id=PROJECT,
        tasks=[OperationalTask(id="t1", text="verificare distribuzione BM UTA SS01",
                               source="whatsapp", source_event_id="e1", source_timestamp="2026-06-24T08:00:00+00:00",
                               lifecycle=_lc("task", "open"))],   # no owner/due → "Da definire"
        issues=[Issue(id="i1", text="Manca BDF e da rifare sala T7 L01",
                      source="whatsapp", source_event_id="e2", lifecycle=_lc("issue", "open"))],
    )


def _seed_events(tmp_path):
    img = tmp_path / "media-cache"
    img.mkdir(parents=True, exist_ok=True)
    # tiny valid JPEG via PIL
    from PIL import Image
    p = img / "IMG123"
    Image.new("RGB", (60, 40), (200, 120, 80)).save(str(p), format="JPEG")
    return [OperationalEvent(event_id="m1", project_id=PROJECT, source="whatsapp", type="image",
                             attachment_type="image", attachment_path=str(p),
                             extracted_text="EWC-10 V10 da siliconare", media_description="quadro metallico")]


@pytest.fixture
def app(monkeypatch, tmp_path):
    from core.operational_memory import state_store, snapshot_store, event_store, media_thumbnail
    import api.operational as operational_api
    monkeypatch.setattr(state_store, "_BASE_DIR", tmp_path / "state")
    monkeypatch.setattr(snapshot_store, "_LIFECYCLE_BASE_DIR", tmp_path / "lc")
    monkeypatch.setattr(event_store, "_BASE_DIR", tmp_path / "events")
    # allow the temp media dir for the thumbnail resolver
    monkeypatch.setattr(media_thumbnail, "ALLOWED_MEDIA_DIRS", (str(tmp_path / "media-cache"),))
    asyncio.run(state_store.save_state(PROJECT, _seed_state()))
    asyncio.run(event_store.save_events(PROJECT, _seed_events(tmp_path)))
    application = FastAPI()
    application.include_router(operational_api.router)
    return application


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_v2_cards_and_sections(app):
    async with _client(app) as c:
        r = await c.get(f"/operational-report/{PROJECT}/latest")
    assert r.status_code == 200
    b = r.text
    assert 'class="card issue"' in b and "[ISSUE]" in b
    assert 'class="card task"' in b and "[TASK]" in b
    assert "Problema:" in b and "Azione richiesta:" in b
    assert "Da definire" in b                          # task lacks owner/due
    assert 'class="metablock"' in b                     # indented/italic metadata


@pytest.mark.asyncio
async def test_v2_media_card_has_img(app):
    async with _client(app) as c:
        r = await c.get(f"/operational-report/{PROJECT}/latest")
    b = r.text
    assert "[MEDIA]" in b
    assert f"/operational-report/{PROJECT}/media/IMG123/thumbnail" in b   # <img> thumb url
    assert "EWC-10" in b                                # OCR rendered
    assert "rif. media:" in b                           # id only as secondary ref


@pytest.mark.asyncio
async def test_v2_diary_separate_page(app):
    async with _client(app) as c:
        r = await c.get(f"/operational-report/{PROJECT}/latest")
    b = r.text
    assert "Diario di bordo Genesi" in b
    assert 'class="diary"' in b
    assert "page-break-before" in b                     # separate page CSS


@pytest.mark.asyncio
async def test_thumbnail_endpoint_serves_image(app):
    async with _client(app) as c:
        r = await c.get(f"/operational-report/{PROJECT}/media/IMG123/thumbnail")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/jpeg"
    assert r.content[:2] == b"\xff\xd8"                  # JPEG magic


@pytest.mark.asyncio
async def test_thumbnail_rejects_unknown_media(app):
    async with _client(app) as c:
        r = await c.get(f"/operational-report/{PROJECT}/media/NOPE999/thumbnail")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_thumbnail_rejects_traversal(app):
    async with _client(app) as c:
        r = await c.get(f"/operational-report/{PROJECT}/media/..%2f..%2fetc%2fpasswd/thumbnail")
    assert r.status_code in (400, 404)                  # never serves arbitrary path


@pytest.mark.asyncio
async def test_json_daily_report_unchanged(app):
    async with _client(app) as c:
        r = await c.get(f"/operational-state/{PROJECT}/daily-report")
    assert r.status_code == 200
    assert "markdown" in r.json()
