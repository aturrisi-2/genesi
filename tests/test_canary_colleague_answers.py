"""Canary colleague answers — persone del gruppo, attività in chat, fail-closed umano.

Dalle prove live: "chi sono i componenti del gruppo" e "marco a che ora è
arrivato lunedì scorso" cadevano nel fail-closed fotocopia. Ora:

  - group_members: risposta vera dai mittenti degli eventi (con conteggi),
    dichiarando la fonte (registro chat, non la lista formale WhatsApp);
  - person_activity: orari dei MESSAGGI della persona (anche "lunedì scorso",
    in ora italiana), dicendo esplicitamente che le presenze fisiche non sono
    tracciate — onestà con sostanza, mai invenzione;
  - fail-closed restante: si rivolge per nome, varia con la query (mai due
    fotocopie), resta assoluto sul non inventare.

Offline: eventi sintetici, nessun LLM, nessun invio reale.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from core.operational_memory.chat_presence import (
    _referenced_day,
    _rome_dt,
    build_operational_reply,
)
from core.operational_memory.models import OperationalEvent, OperationalState
from core.operational_memory.query_engine import classify_query_intent
from core.operational_memory.whatsapp_operational import _tab_unknown_reply


ROME = ZoneInfo("Europe/Rome")


# --------------------------------------------------------------------------- #
# Classificazione
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("q,expected", [
    ("chi sono i componenti del gruppo dimmi i nomi", "group_members"),
    ("chi scrive nel gruppo?", "group_members"),
    ("membri del gruppo", "group_members"),
    ("marco a che ora è arrivato lunedì scorso", "person_activity"),
    ("quando ha scritto Anna ieri?", "person_activity"),
    ("l'ultima volta che ha scritto Marco", "person_activity"),
])
def test_new_intents_classified(q, expected):
    assert classify_query_intent(q) == expected


@pytest.mark.parametrize("q,expected", [
    ("problemi aperti?", "open_issues"),
    ("chi deve fare cosa?", "open_tasks"),
    ("quale utente ha segnalato più problemi", "reporter_stats"),
])
def test_existing_intents_not_hijacked(q, expected):
    assert classify_query_intent(q) == expected


# --------------------------------------------------------------------------- #
# Fixtures eventi
# --------------------------------------------------------------------------- #

def _events() -> list[OperationalEvent]:
    monday = datetime.now(ROME).date() - timedelta(
        days=(datetime.now(ROME).date().weekday() % 7) or 7)
    # lunedì scorso (sempre nel passato), orari UTC che in Italia (estate)
    # diventano 09:00 e 15:30
    def utc(day, h, m):
        return datetime(day.year, day.month, day.day, h, m,
                        tzinfo=ZoneInfo("UTC")).isoformat()
    return [
        OperationalEvent(event_id="e1", project_id="p", sender="Marco",
                         type="text", text="arrivato, inizio dal quadro",
                         timestamp=utc(monday, 7, 0)),
        OperationalEvent(event_id="e2", project_id="p", sender="Marco",
                         type="text", text="chiuso il piano 2",
                         timestamp=utc(monday, 13, 30)),
        OperationalEvent(event_id="e3", project_id="p", sender="Anna",
                         type="text", text="ok",
                         timestamp=utc(monday, 8, 15)),
    ]


def _patch(monkeypatch, events):
    state = OperationalState(project_id="p")
    monkeypatch.setattr(
        "core.operational_memory.chat_presence.load_state",
        lambda _p: asyncio.sleep(0, result=state))
    monkeypatch.setattr(
        "core.operational_memory.event_store.list_events",
        lambda _p: asyncio.sleep(0, result=events))


# --------------------------------------------------------------------------- #
# group_members
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_group_members_lists_real_senders_with_counts(monkeypatch):
    _patch(monkeypatch, _events())
    reply = await build_operational_reply("p", "chi sono i componenti del gruppo?",
                                          save=False)
    assert reply.intent == "group_members"
    assert "Marco (2 messaggi)" in reply.reply_markdown
    assert "Anna (1 messaggio)" in reply.reply_markdown
    assert "WhatsApp" in reply.reply_markdown   # fonte dichiarata onestamente


@pytest.mark.asyncio
async def test_group_members_empty_is_honest(monkeypatch):
    _patch(monkeypatch, [])
    reply = await build_operational_reply("p", "chi scrive nel gruppo?", save=False)
    assert "Non ho ancora messaggi registrati" in reply.reply_markdown


# --------------------------------------------------------------------------- #
# person_activity
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_person_activity_day_span_in_rome_time(monkeypatch):
    _patch(monkeypatch, _events())
    reply = await build_operational_reply(
        "p", "marco a che ora è arrivato lunedì scorso", save=False)
    assert reply.intent == "person_activity"
    body = reply.reply_markdown
    assert "Marco" in body and "2 messaggi" in body
    # 07:00Z/13:30Z → 09:00/15:30 italiane (estate)
    assert "09:00" in body and "15:30" in body
    # onestà sul limite: chat, non presenze
    assert "non lo traccio" in body or "non li registro" in body


@pytest.mark.asyncio
async def test_person_activity_silent_day_is_honest(monkeypatch):
    _patch(monkeypatch, _events())
    reply = await build_operational_reply(
        "p", "quando ha scritto Anna ieri?", save=False)
    assert "Anna" in reply.reply_markdown
    assert "non ha scritto nulla" in reply.reply_markdown


@pytest.mark.asyncio
async def test_person_activity_unknown_person_asks_naturally(monkeypatch):
    _patch(monkeypatch, _events())
    reply = await build_operational_reply(
        "p", "a che ora è arrivato Gennaro?", save=False)
    assert "Dimmi il nome" in reply.reply_markdown
    assert "Marco" in reply.reply_markdown   # suggerisce chi conosce davvero


@pytest.mark.asyncio
async def test_person_activity_no_day_gives_last_message(monkeypatch):
    _patch(monkeypatch, _events())
    reply = await build_operational_reply(
        "p", "l'ultima volta che ha scritto Marco?", save=False)
    assert "L'ultima volta che Marco ha scritto" in reply.reply_markdown


# --------------------------------------------------------------------------- #
# Helpers temporali
# --------------------------------------------------------------------------- #

def test_referenced_day_semantics():
    today = datetime.now(ROME).date()
    assert _referenced_day("quando ha scritto ieri?") == today - timedelta(days=1)
    assert _referenced_day("chi ha scritto oggi?") == today
    monday = _referenced_day("a che ora è arrivato lunedì scorso")
    assert monday.weekday() == 0 and monday < today or monday == today - timedelta(days=7)
    assert _referenced_day("quando ha scritto?") is None


def test_rome_dt_converts_utc():
    dt = _rome_dt("2026-07-13T07:00:00+00:00")
    assert f"{dt:%H:%M}" == "09:00"   # estate: UTC+2
    assert _rome_dt("garbage") is None


# --------------------------------------------------------------------------- #
# Fail-closed umano
# --------------------------------------------------------------------------- #

def test_tab_unknown_reply_addresses_by_name_and_varies():
    a = _tab_unknown_reply("Alfio", "fai una magia")
    b = _tab_unknown_reply("Alfio", "dimmi un segreto")
    c = _tab_unknown_reply("Alfio", "sistemami la faccenda")
    assert a.startswith("Alfio, ")
    assert len({a, b, c}) >= 2            # varia tra query diverse
    assert _tab_unknown_reply("Alfio", "fai una magia") == a  # deterministico
    # mai inventare: ogni variante reindirizza a ciò che sa fare davvero
    for v in (a, b, c):
        assert "problemi" in v or "stato" in v or "quadro" in v


def test_tab_unknown_reply_without_name_still_natural():
    v = _tab_unknown_reply("", "query strana")
    assert v and not v.startswith(", ")


# --------------------------------------------------------------------------- #
# Weather carry gate (loop live 17/07: ogni follow-up diventava meteo)
# --------------------------------------------------------------------------- #

def test_weather_context_carry_is_topic_gated():
    with open("baileys-service/index.js", encoding="utf-8") as fh:
        src = fh.read()
    assert "function isWeatherTopicFollowup" in src
    # il carry passa dal gate: prima riga della funzione di concatenazione
    assert "if (!isWeatherTopicFollowup(followup)) return followup;" in src


@pytest.mark.skipif(__import__("shutil").which("node") is None,
                    reason="node non disponibile")
def test_weather_carry_behaviour_in_node():
    import subprocess
    script = r'''
const src = require("fs").readFileSync("baileys-service/index.js","utf8");
const fnSrc = src.match(/function isWeatherTopicFollowup[\s\S]*?\n}/)[0] + "\n" +
              src.match(/function weatherContextFollowupQuery[\s\S]*?\n}/)[0];
eval(fnSrc);
const prev = "Per domani a Bologna, le previsioni indicano cielo sereno.";
const same = (i) => weatherContextFollowupQuery(i, prev) === i;
const carried = (i) => weatherContextFollowupQuery(i, prev).startsWith("meteo domani a Bologna. ");
if (!same("impegni di oggi?")) process.exit(1);
if (!same("cosa è successo domenica?")) process.exit(2);
if (!carried("che ne pensi, si potrà lavorare al sole?")) process.exit(3);
if (!carried("e dopodomani?")) process.exit(4);
process.exit(0);
'''
    proc = subprocess.run(["node", "-e", script], capture_output=True)
    assert proc.returncode == 0, proc.stderr.decode()


# --------------------------------------------------------------------------- #
# media_recap — risponde con ciò che ha visto/sentito (foto, audio, video)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("q,expected", [
    ("cosa ti ho appena mandato?", "media_recap"),
    ("hai visto la foto?", "media_recap"),
    ("cosa dice l'audio?", "media_recap"),
    ("descrivi il video", "media_recap"),
    ("cosa vedi di aperto?", "unknown"),   # non hijackato da media_recap
])
def test_media_recap_classification(q, expected):
    assert classify_query_intent(q) == expected


def _media_events():
    return [
        OperationalEvent(
            event_id="ph1", project_id="p", sender="Alfio", type="image",
            attachment_type="image",
            extracted_text="Un gatto rilassato su un sacchetto di carta. [TOTAL_PETS:1]",
            timestamp="2026-07-17T15:20:00+00:00"),
        OperationalEvent(
            event_id="au1", project_id="p", sender="Marco", type="audio",
            attachment_type="audio",
            extracted_text="Arrivo tardi, sono in coda a Orte.",
            timestamp="2026-07-17T14:00:00+00:00"),
    ]


@pytest.mark.asyncio
async def test_media_recap_answers_with_vision_description(monkeypatch):
    _patch(monkeypatch, _media_events())
    reply = await build_operational_reply(
        "p", "cosa ti ho appena mandato?", invoked_by="Alfio", save=False)
    assert reply.intent == "media_recap"
    body = reply.reply_markdown
    assert body.startswith("Mi hai mandato una foto")
    assert "gatto rilassato" in body
    assert "[TOTAL_PETS" not in body           # marker interni mai in chat
    assert "17:20" in body                     # ora italiana (UTC+2)


@pytest.mark.asyncio
async def test_media_recap_audio_filter_and_third_person(monkeypatch):
    _patch(monkeypatch, _media_events())
    reply = await build_operational_reply(
        "p", "cosa dice l'audio?", invoked_by="Alfio", save=False)
    body = reply.reply_markdown
    assert "Marco ha mandato un vocale" in body
    assert "l'ho ascoltato e dice" in body
    assert "coda a Orte" in body


@pytest.mark.asyncio
async def test_media_recap_no_media_is_honest(monkeypatch):
    _patch(monkeypatch, [])
    reply = await build_operational_reply(
        "p", "hai visto la foto?", invoked_by="Alfio", save=False)
    assert "non ho ancora ricevuto" in reply.reply_markdown


def test_media_recap_is_auxiliary_origin_project():
    with open("core/operational_memory/whatsapp_operational.py", encoding="utf-8") as fh:
        src = fh.read()
    assert '"media_recap"' in src.split("auxiliary_intents = ")[1].split("\n")[0]
