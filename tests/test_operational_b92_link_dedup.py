"""B9.2 — report link dedup in render_whatsapp_reply.

cmd_report embeds the report URL in the body; the WA renderer must not
append the same link a second time. Link still appended when the body has
no URL (briefing/digest); never appended for non-report intents.
"""
from __future__ import annotations

from core.operational_memory.models import ChatReply
from core.operational_memory.whatsapp_operational import render_whatsapp_reply

URL = "https://x/api/operational/projects/p/reports/r1/view"


def _reply(intent, body, url=URL):
    return ChatReply(
        project_id="p", intent=intent, reply_markdown=body,
        synthesis="", table_markdown="", actions=[], evidence_event_ids=[],
        report_id="r1", report_url=url,
    )


def test_cmd_report_body_with_url_no_duplicate():
    body = render_whatsapp_reply(_reply("cmd_report", f"Report operativo: {URL}"))
    assert body.count(URL) == 1
    assert body == f"Report operativo: {URL}"


def test_report_tab_style_body_with_url_no_duplicate():
    # Bridge prepends "Vista TAB reale:" around the same rendered body upstream;
    # renderer itself must still emit the URL exactly once.
    body = render_whatsapp_reply(_reply("cmd_report", f"Report operativo: {URL}"))
    assert body.count(URL) == 1


def test_briefing_body_without_url_still_appends():
    body = render_whatsapp_reply(_reply("briefing", "📌 Quadro operativo\n..."))
    assert body.count(URL) == 1
    assert body.endswith(f"Report: {URL}")


def test_digest_body_without_url_still_appends():
    body = render_whatsapp_reply(_reply("digest", "sintesi breve"))
    assert f"Report: {URL}" in body


def test_non_report_intent_never_appends():
    for intent in ["attention", "open_tasks", "open_issues", "team_brief", "cmd_stato"]:
        body = render_whatsapp_reply(_reply(intent, "corpo risposta"))
        assert URL not in body, intent


def test_no_report_url_no_append():
    body = render_whatsapp_reply(_reply("cmd_report", "Report operativo disponibile", url=""))
    assert body == "Report operativo disponibile"
