from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from core.operational_memory.report_viewer import markdown_to_html, render_report_page
from core.operational_memory.models import StoredReport


PROJECT = "viewer-proj"

_SAMPLE_MD = """# Briefing operativo — viewer-proj

## Quadro sintetico

| Categoria | N |
| --- | ---: |
| Task aperti | 2 |
| Problemi risolti | 1 |

## Sintesi

**Azione consigliata:** monitorare.

## Dettaglio

### Task aperti (2) — ATTIVO
- ordinare materiale (open) [evidenza: ev1]
- inviare preventivo (open)
"""


# --------------------------------------------------------------------------- #
# Pure renderer
# --------------------------------------------------------------------------- #


def test_markdown_to_html_constructs():
    html = markdown_to_html(_SAMPLE_MD)
    assert "<h1>" in html and "<h2>" in html and "<h3>" in html
    assert "<table>" in html and "<th>" in html and "<td>" in html
    assert "<ul>" in html and "<li>" in html
    assert "<strong>Azione consigliata:</strong>" in html
    assert "evidenza: ev1" in html  # evidence preserved


def test_markdown_escapes_html():
    html = markdown_to_html("- <script>alert(1)</script>")
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_render_report_page_has_buttons_and_css():
    report = StoredReport(report_id="report_x", project_id=PROJECT, generated_at="2026-06-20T10:00:00+00:00", markdown=_SAMPLE_MD)
    page = render_report_page(report, "/dl/report_x")
    assert page.startswith("<!doctype html>")
    assert 'window.print()' in page
    assert 'href="/dl/report_x" download' in page
    assert "@media print" in page and "no-print" in page
    assert "viewport" in page  # mobile-friendly
    assert PROJECT in page and "report_x" in page


# --------------------------------------------------------------------------- #
# Endpoints
# --------------------------------------------------------------------------- #


@pytest.fixture
def app(monkeypatch, tmp_path):
    from core.operational_memory import report_store
    import api.operational as operational_api

    monkeypatch.setattr(report_store, "_BASE_DIR", tmp_path / "reports")
    rep = report_store.save_report(PROJECT, _SAMPLE_MD)

    application = FastAPI()
    application.include_router(operational_api.router)
    application.state.report_id = rep.report_id
    return application


def _client(app) -> AsyncClient:
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_view_endpoint_html(app):
    rid = app.state.report_id
    async with _client(app) as c:
        r = await c.get(f"/api/operational/projects/{PROJECT}/reports/{rid}/view")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    assert "Briefing operativo" in body
    assert "<table>" in body
    assert "window.print()" in body
    assert f"/reports/{rid}/download" in body  # download link present


@pytest.mark.asyncio
async def test_view_missing_404(app):
    async with _client(app) as c:
        r = await c.get(f"/api/operational/projects/{PROJECT}/reports/nope/view")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_download_still_works(app):
    rid = app.state.report_id
    async with _client(app) as c:
        r = await c.get(f"/api/operational/projects/{PROJECT}/reports/{rid}/download")
    assert r.status_code == 200
    assert "text/markdown" in r.headers["content-type"]
    assert "attachment" in r.headers.get("content-disposition", "")


@pytest.mark.asyncio
async def test_harness_page(app):
    async with _client(app) as c:
        r = await c.get("/operational/harness")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "Test Harness" in r.text and "/chat" in r.text


def test_no_hardcoded_domain_tokens_in_viewer():
    import re

    import core.operational_memory.report_viewer as mod

    body = open(mod.__file__, "r", encoding="utf-8").read().upper()
    for token in ["TAB CEFLA", "T6", "T7", "UTA", "EWC05", "SS01", "B02", "CANTIERE", "WHATSAPP"]:
        assert not re.search(rf"\b{re.escape(token)}\b", body), f"hardcoded token: {token}"
