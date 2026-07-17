"""Canary photo replies — le foto dei problemi arrivano in chat come immagini.

"Fammi vedere le foto dei problemi aperti" rispondeva con un elenco di link:
utile ma da bot. Ora la ChatReply trasporta gli allegati ([{media_id, caption,
url}]), l'API li espone nella GroupChatResponse e Baileys li invia come foto
reali con didascalia, con l'URL come fallback se il file non c'è più. Il testo
annuncia le foto come farebbe un collega.

Offline: stato/eventi monkeypatchati, nessun LLM, nessun invio reale.
"""

from __future__ import annotations

import asyncio
import json

import pytest

from core.operational_memory.chat_presence import build_operational_reply
from core.operational_memory.models import Issue, OperationalEvent, OperationalState


def _issue_state_with_images(n: int) -> tuple[OperationalState, list[OperationalEvent]]:
    issues, events = [], []
    for i in range(n):
        eid = f"img{i}"
        issues.append(Issue(text=f"Problema {i} sul quadro", source="whatsapp",
                            source_event_id=eid))
        events.append(OperationalEvent(
            event_id=eid, project_id="p", source="whatsapp", type="image",
            attachment_type="image",
            attachment_path=f"/opt/genesi-baileys/media-cache/{eid}",
        ))
    return OperationalState(project_id="p", issues=issues), events


def _patch_state(monkeypatch, state, events):
    monkeypatch.setattr(
        "core.operational_memory.chat_presence.load_state",
        lambda _p: asyncio.sleep(0, result=state))
    monkeypatch.setattr(
        "core.operational_memory.event_store.list_events",
        lambda _p: asyncio.sleep(0, result=events))


@pytest.mark.asyncio
async def test_media_entries_cap_at_five_and_carry_captions(monkeypatch):
    state, events = _issue_state_with_images(7)
    _patch_state(monkeypatch, state, events)
    reply = await build_operational_reply(
        "p", "fammi vedere le foto dei problemi aperti",
        report_base_url="https://example.test", save=False)
    assert len(reply.media) == 5
    assert all(m["media_id"] and m["caption"] and m["url"] for m in reply.media)
    assert reply.media[0]["caption"] == "Problema 0 sul quadro"
    assert "5 dei problemi aperti" in reply.reply_markdown


@pytest.mark.asyncio
async def test_no_images_answer_is_honest_and_has_no_media(monkeypatch):
    state = OperationalState(project_id="p", issues=[
        Issue(text="Problema senza foto", source="whatsapp", source_event_id="t1"),
    ])
    _patch_state(monkeypatch, state, [])
    reply = await build_operational_reply(
        "p", "fammi vedere le foto dei problemi aperti",
        report_base_url="https://example.test", save=False)
    assert reply.media == []
    assert "non ho foto collegate in modo affidabile" in reply.reply_markdown
    assert "https://" not in reply.reply_markdown


# --------------------------------------------------------------------------- #
# Wiring pins: bridge → API → Baileys
# --------------------------------------------------------------------------- #


def _src(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def test_bridge_forwards_media_with_the_reply():
    src = _src("core/operational_memory/whatsapp_operational.py")
    assert src.count('media=list(getattr(tab_reply, "media", []) or [])') >= 2


def test_api_response_carries_media():
    src = _src("api/chat.py")
    assert "media: list[dict] = []" in src
    assert '_op_reply["media"] = list(k["media"])' in src
    assert 'media=list(_op_reply.get("media") or [])' in src


def test_baileys_sends_real_images_with_sanitized_ids_and_fallback():
    src = _src("baileys-service/index.js")
    assert "backendResult.media" in src
    assert 'replace(/[^A-Za-z0-9._-]/g, "")' in src   # niente path traversal
    assert "image: fs.readFileSync(mediaPath), caption" in src
    assert ".slice(0, 5)" in src                       # cap invii
    assert "Invio foto fallito" in src                 # fallback su errore
