import asyncio

import pytest

from core.operational_memory.chat_presence import build_chat_reply, build_operational_reply
from core.operational_memory.models import ChatReply, Issue, OperationalEvent, OperationalState
from core.operational_memory.query_engine import answer_query, classify_query_intent


def test_new_conversational_intents_precede_generic_issue_list():
    assert classify_query_intent("quale utente ha segnalato più problemi") == "reporter_stats"
    assert classify_query_intent("fammi vedere la foto di questi problemi aperti") == "issue_media"
    assert classify_query_intent("oggi com'è il tempo, consigli di lavorare al sole?") == "weather"
    assert classify_query_intent("segna che il circuito freddo è fermo") != "weather"


def test_reporter_answer_is_natural_and_explainable():
    state = OperationalState(
        project_id="p",
        issues=[
            Issue(text="A", source="whatsapp", source_sender="Marco"),
            Issue(text="B", source="whatsapp", source_sender="Marco"),
            Issue(text="C", source="whatsapp", source_sender="Flo"),
        ],
    )
    result = answer_query(state, "quale utente ha segnalato più problemi")
    reply = build_chat_reply(state, result.query)

    assert result.intent == "reporter_stats"
    assert "Al momento è Marco" in reply.reply_markdown
    assert "2 delle 3" in reply.reply_markdown
    assert "non delle responsabilità" in reply.reply_markdown


@pytest.mark.asyncio
async def test_issue_media_returns_only_verified_open_issue_images(monkeypatch):
    state = OperationalState(
        project_id="p",
        issues=[Issue(text="Sensore guasto", source="whatsapp", source_event_id="img1")],
    )
    event = OperationalEvent(
        event_id="img1", project_id="p", source="whatsapp", type="image",
        attachment_type="image", attachment_path="/opt/genesi-baileys/media-cache/img1",
    )
    monkeypatch.setattr("core.operational_memory.chat_presence.load_state", lambda _p: asyncio.sleep(0, result=state))
    monkeypatch.setattr("core.operational_memory.event_store.list_events", lambda _p: asyncio.sleep(0, result=[event]))

    reply = await build_operational_reply(
        "p", "fammi vedere le foto dei problemi aperti",
        report_base_url="https://example.test", save=False,
    )

    assert reply.intent == "issue_media"
    assert "Sensore guasto" in reply.reply_markdown
    assert "https://example.test/operational-report/p/media/img1/thumbnail" in reply.reply_markdown
    assert reply.evidence_event_ids == ["img1"]


@pytest.mark.asyncio
async def test_weather_is_honest_and_never_written_as_operational_data(monkeypatch):
    state = OperationalState(project_id="p")
    monkeypatch.setattr("core.operational_memory.chat_presence.load_state", lambda _p: asyncio.sleep(0, result=state))
    reply = await build_operational_reply(
        "p", "oggi com'è il tempo, consigli di lavorare al sole?", save=False,
    )
    assert reply.intent == "weather"
    assert "non ho dati meteo in tempo reale affidabili" in reply.reply_markdown
    assert "procedure di sicurezza" in reply.reply_markdown


@pytest.mark.asyncio
async def test_same_sender_followup_routes_to_tab_without_ingesting_canary(monkeypatch):
    import core.operational_memory.whatsapp_operational as mod

    canary = "120363000000000001@g.us"
    tab_project = "tab-project"
    monkeypatch.setattr(mod, "is_whatsapp_operational_enabled", lambda: True)
    monkeypatch.setattr(mod, "resolve_whatsapp_project_id", lambda jid: "canary-project")
    monkeypatch.setattr(mod, "is_whatsapp_operational_reply_enabled", lambda jid=None: True)
    monkeypatch.setattr(mod, "_TAB_BRIDGE_ORIGIN_JID", canary)
    monkeypatch.setattr(mod, "_TAB_BRIDGE_PROJECT_ID", tab_project)
    monkeypatch.setattr(mod, "_TAB_BRIDGE_DEFAULT_NO_TARGET", True)

    captured = []
    ingested = []
    sent = []

    async def fake_reply(project_id, query, **kwargs):
        captured.append((project_id, query))
        return ChatReply(project_id=project_id, intent="reporter_stats", reply_markdown="Marco è il primo.")

    async def update(message):
        ingested.append(message)

    async def send(to, text):
        sent.append((to, text))

    monkeypatch.setattr(mod, "build_operational_reply", fake_reply)
    result = {}
    handled = await mod.maybe_handle_whatsapp_operational(
        canary, "sender", "Alfio", "quale utente ha segnalato più problemi",
        send, message_id="followup-1", updater=update, result=result,
        directed_followup=True,
    )

    assert handled is True
    assert captured == [(tab_project, "quale utente ha segnalato più problemi")]
    assert ingested == []
    assert sent == [(canary, "Vista TAB reale:\nMarco è il primo.")]
    assert result["action"] == "tab_bridge"


def test_baileys_forwards_only_gated_directed_followup_flag():
    src = open("baileys-service/index.js", encoding="utf-8").read()
    assert "directed_followup: directedFollowup" in src
    assert 'interventionReason === "engaged_direct_followup"' in src
    assert "|| /\\?\\s*$/.test(s)" in src
