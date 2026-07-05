"""Telegram group multimodal context continuity.

Reproduces (offline, no live Telegram, no real providers) the two real failures
observed in a Telegram family group:

  Scenario A — a photo with caption ("Pokè di pollo…, fatto da Elena") is shared,
  the group comments, then a user invokes Genesi ("Genesi come ti sembra il poke").
  The caption MUST be present in the recent conversation window at invocation time
  so the reply can be contextual (not a generic knowledge-base answer).

  Scenario B — after "direzione mare" / "In partenza per Franchetto" and an earlier
  rhetorical question from another member, a user invokes Genesi with a weather
  question. The unanswered-question PRIORITY override must NOT hijack the direct
  invocation (that hijack injected a contradictory instruction → the model refused
  with "non posso rispondere").

The assertions target platform-independent core behaviour (the shared group memory
buffer + the reusable invocation-vs-spontaneous helper), not Telegram transport.
Generic: no chat id, family name, "poke", "Franchetto" or weather term is relied
on by the production code — they appear here only as representative fixture data.
"""

from __future__ import annotations

import pytest

from core.group_reactivity import addresses_genesi_directly, find_unanswered_question


# --------------------------------------------------------------------------- #
# In-memory storage fake (no real memory/ writes).
# --------------------------------------------------------------------------- #


class _FakeStorage:
    def __init__(self):
        self._d = {}

    async def load(self, key, default=None):
        return self._d.get(key, default)

    async def save(self, key, value):
        self._d[key] = value


@pytest.fixture
def fake_storage(monkeypatch):
    fake = _FakeStorage()
    monkeypatch.setattr("core.storage.storage", fake, raising=False)
    return fake


CHAT_ID = -100777000  # representative group id, not a real chat


# --------------------------------------------------------------------------- #
# Scenario A — caption enters the recent window and survives until invocation.
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_photo_caption_is_in_recent_window_at_invocation(fake_storage):
    from core.telegram_group_memory import append_raw_message, get_raw_messages

    # A photo with caption is ingested exactly like a text message: the transport
    # appends (text or caption), so the caption becomes recoverable buffer content.
    caption = "Pokè di pollo in agrodolce, fatto da Elena!!!"
    await append_raw_message(CHAT_ID, 1, "Mariella", caption)          # photo caption
    await append_raw_message(CHAT_ID, 2, "Katia", "Meee sembra buonissimo")
    await append_raw_message(CHAT_ID, 3, "Alfio", "Brava Elena, sembra buono")
    await append_raw_message(CHAT_ID, 4, "Iolanda", "buono sicuramente brava")
    # ... invocation arrives later:
    await append_raw_message(CHAT_ID, 5, "Alfio", "Genesi come ti sembra il poke")

    window = await get_raw_messages(CHAT_ID, limit=20)
    texts = [m.get("text", "") for m in window]

    # The caption is still in the recent window — the invocation reply can refer to it.
    assert any("agrodolce" in t for t in texts)
    assert any("Elena" in t for t in texts)
    # And it is not just the last message: the whole recent thread is available.
    assert len(window) >= 5


# --------------------------------------------------------------------------- #
# Scenario B — a direct invocation must not be hijacked by an older unanswered
# (often rhetorical) question from another member.
# --------------------------------------------------------------------------- #


def test_direct_invocation_skips_unanswered_question_hijack():
    # Recent buffer: an earlier rhetorical question from Mariella, conversation
    # moved on, then Alfio directly invokes Genesi with a weather question.
    raw = [
        {"first_name": "Mariella", "text": "Mia figlia si è messo il copricostume sopra la maglietta???"},
        {"first_name": "Katia", "text": "Si"},
        {"first_name": "Mariella", "text": "Con questo caldo"},
        {"first_name": "Mariella", "text": "In partenza per Franchetto"},
    ]
    current = "Buon mare e buon Franchetto, genesi come sarà il tempo nella destinazione dei vacanzieri"

    # The detector WOULD surface Mariella's dangling question (the hijack risk is real)…
    assert find_unanswered_question(raw, current_sender="Alfio") is not None
    # …but the current message directly addresses Genesi, so the override is skipped.
    assert addresses_genesi_directly(current, bot_mentioned=False, reply_to_genesi=False) is True


def test_spontaneous_intervention_still_answers_dangling_question():
    # No direct invocation → the unanswered-question feature is preserved: Genesi may
    # still step in to answer the dangling question during an autonomous intervention.
    raw = [
        {"first_name": "Mariella", "text": "Qualcuno sa a che ora apre la farmacia?"},
        {"first_name": "Katia", "text": "boh"},
        {"first_name": "Wind", "text": "Buongiorno"},
    ]
    current = "che caldo oggi"  # a normal group message, not addressed to Genesi
    assert addresses_genesi_directly(current) is False
    uq = find_unanswered_question(raw, current_sender="Wind")
    assert uq is not None and "farmacia" in uq["text"]


def test_telegram_bot_wires_the_invocation_gate():
    src = open("core/telegram_bot.py", "r", encoding="utf-8").read()
    # The unanswered-question override is gated by the direct-invocation check.
    assert "addresses_genesi_directly" in src
    assert "_direct_invocation" in src


def test_proactor_passes_platform_on_internal_context_build():
    src = open("core/proactor.py", "r", encoding="utf-8").read()
    # Regression: the internal context build must not drop the platform (which would
    # bypass telegram_group/whatsapp_group predictive-hint suppression).
    assert "self.context_assembler.build(user_id, message)\n" not in src
