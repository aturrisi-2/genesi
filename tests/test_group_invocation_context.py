"""Group invocation context — intent routing + flat-refusal guard (core, shared).

Covers the two residual root causes of the "cold / refusing" group replies:

  1. Intent routing: the group paths (Telegram `_group_msg`, WhatsApp `_do_chat`)
     hand the classifier a DECORATED prompt ([ISTRUZIONE PRIORITARIA]/[IDENTITÀ
     ASSOLUTA] preamble + [MESSAGGIO ATTUALE] wrapper + group history). The
     classifier must operate on the user's real text only, otherwise tool-shaped
     questions (weather, reminders, …) collapse to chat_free and the relational
     route answers without data → refusal. `extract_group_user_text` isolates
     the user turn while preserving inline media markers.

  2. Flat-refusal guard: when the relational model still emits the bare
     "non posso rispondere a questo messaggio" fallback, the shared post-
     generation enforcement (`enforce_group_pragmatic_response`, called by BOTH
     the Telegram and the WhatsApp send paths) must turn it into an honest
     clarification request on direct invocation, and into silence on
     spontaneous interventions. Never a flat refusal, never invented data.

All tests are OFFLINE: pure functions only, no LLM, no storage, no transport.
Fixture texts are generic and reproduce the STRUCTURE of the real incidents,
not their literal content.
"""

from __future__ import annotations

import re

import pytest

from core.group_pragmatics import (
    POSTURE_ASSISTANT_OBSERVER,
    POSTURE_DIRECT_ASSISTANT,
    POSTURE_DRAFT_HELPER,
    POSTURE_NEUTRAL_SUPPORT,
    POSTURE_SILENT,
    classify_group_message_role,
    enforce_group_pragmatic_response,
    is_flat_group_refusal,
)
from core.intent_classifier import extract_group_user_text, intent_classifier


# --------------------------------------------------------------------------- #
# Decorated-prompt builders — reproduce the two adapter wrapper STRUCTURES.
# --------------------------------------------------------------------------- #

def _telegram_wrapper(user_text: str, sender: str = "Utente1",
                      preamble: str = "") -> str:
    """Structure of telegram_bot._group_msg output (identity + current block)."""
    return (
        f"{preamble}"
        "[IDENTITÀ ASSOLUTA: TU sei Genesi, l'AI del gruppo. Rispondi SEMPRE "
        f"in prima persona come Genesi. Il messaggio a cui DEVI rispondere è quello di {sender} qui sotto.]\n"
        "[MESSAGGIO ATTUALE — a cui devi rispondere]\n"
        f"{sender}: {user_text}\n"
        "[FINE MESSAGGIO ATTUALE]\n"
        "\n[GRUPPO FAMILIARE: REGOLE ASSOLUTE: risposta misurata.]\n"
        "[POLICY PRAGMATICA GRUPPO: interpreta il ruolo del messaggio.]\n"
        "[DISCUSSIONE IN CORSO — messaggi recenti del gruppo:]\n"
        "  [1h fa] Utente2: piatto di pesce fatto in casa!\n"
        "  [5min fa] Utente3: in partenza per la località di mare\n"
        "[FINE DISCUSSIONE IN CORSO]\n"
    )


def _whatsapp_wrapper(user_text: str, sender: str = "Utente1") -> str:
    """Structure of whatsapp_bot._do_chat output (raw text first, blocks after)."""
    return (
        f"{user_text}\n\n"
        f"[GRUPPO FAMILIARE: scrive {sender}. REGOLE ASSOLUTE: risposta misurata.]\n"
        "[POLICY PRAGMATICA GRUPPO: interpreta il ruolo del messaggio.]\n"
        "[DISCUSSIONE IN CORSO — messaggi recenti del gruppo:]\n"
        "  [5min fa] Utente3: in partenza per la località di mare\n"
        "[FINE DISCUSSIONE IN CORSO]\n"
    )


_PRIORITY_PREAMBLE = (
    '[ISTRUZIONE PRIORITARIA: nel gruppo Utente9 aveva chiesto "cancella '
    'quella prenotazione?" e nessuno ha risposto. Rispondi PRIMA a Utente9.]\n\n'
)

_WEATHER_QUESTION = "genesi come sarà il tempo nella destinazione del viaggio"


# --------------------------------------------------------------------------- #
# 1. extract_group_user_text — user turn isolated from both adapter wrappers.
# --------------------------------------------------------------------------- #

def test_extract_returns_plain_text_unchanged():
    assert extract_group_user_text("che ore sono?") == "che ore sono?"
    assert extract_group_user_text("") == ""


def test_extract_isolates_user_text_from_telegram_wrapper():
    blob = _telegram_wrapper(_WEATHER_QUESTION)
    assert extract_group_user_text(blob) == _WEATHER_QUESTION


def test_extract_drops_priority_preamble_before_current_message():
    blob = _telegram_wrapper(_WEATHER_QUESTION, preamble=_PRIORITY_PREAMBLE)
    out = extract_group_user_text(blob)
    assert out == _WEATHER_QUESTION
    assert "ISTRUZIONE PRIORITARIA" not in out
    assert "cancella" not in out  # keywords quoted in the hijack must not leak


def test_extract_preserves_inline_media_marker():
    # The photo-analysis marker is part of the user turn: photo routes need it.
    text = "guarda qui\n[Contenuto immagine: un piatto colorato su un tavolo]"
    blob = _telegram_wrapper(text)
    out = extract_group_user_text(blob)
    assert "[Contenuto immagine:" in out
    assert out.startswith("guarda qui")


def test_extract_handles_emoji_variant():
    blob = (
        "[IDENTITÀ ASSOLUTA: TU sei Genesi.]\n"
        "[MESSAGGIO ATTUALE — Utente1]: 😘😘\n\n"
        "[GRUPPO FAMILIARE: Reazione emoji — 1 riga max.]\n"
    )
    assert extract_group_user_text(blob).startswith("😘😘")


def test_extract_strips_bare_preamble_without_current_block():
    blob = _PRIORITY_PREAMBLE + "come stai?"
    assert extract_group_user_text(blob) == "come stai?"


# --------------------------------------------------------------------------- #
# 2. Deterministic guard layers run on the user text, not the wrapper.
#    (normalize_reminder_intent is the pure deterministic layer on the same
#     extraction path used by classify_async.)
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("wrapper", [_telegram_wrapper, _whatsapp_wrapper])
def test_reminder_keywords_inside_wrapper_do_not_hijack_intent(wrapper):
    # "cancella" appears ONLY in the priority-preamble quote / group history,
    # not in the user's message → must NOT force reminder_delete.
    blob = wrapper("buongiorno a tutti!")
    if wrapper is _telegram_wrapper:
        blob = _PRIORITY_PREAMBLE + blob
    out = intent_classifier.normalize_reminder_intent(blob, "chat_free")
    assert out != "reminder_delete"


@pytest.mark.parametrize("wrapper", [_telegram_wrapper, _whatsapp_wrapper])
def test_reminder_keywords_in_user_text_still_detected(wrapper):
    blob = wrapper("cancella il promemoria della spesa")
    out = intent_classifier.normalize_reminder_intent(blob, "chat_free")
    assert out == "reminder_delete"


# --------------------------------------------------------------------------- #
# 3. Flat-refusal guard (shared core enforcement, Telegram + WhatsApp path).
# --------------------------------------------------------------------------- #

_FLAT_REFUSALS = [
    "Mi dispiace, ma non posso rispondere a questo messaggio.",
    "Mi dispiace, non posso rispondere a questo messaggio.",
    "non posso rispondere a questo messaggio",
]


@pytest.mark.parametrize("refusal", _FLAT_REFUSALS)
def test_is_flat_group_refusal_matches_bare_refusals(refusal):
    assert is_flat_group_refusal(refusal)


def test_is_flat_group_refusal_ignores_argued_or_normal_replies():
    assert not is_flat_group_refusal(
        "Non posso rispondere a questo messaggio perché mi mancano i dati del "
        "viaggio: dimmi la destinazione e ti dico che tempo farà."
    )
    assert not is_flat_group_refusal("Che bel piatto, complimenti alla cuoca!")
    assert not is_flat_group_refusal("")


def _role_with_posture(posture: str):
    from core.group_pragmatics import GroupMessageRole
    return GroupMessageRole(recommended_response_posture=posture)


@pytest.mark.parametrize("posture", [POSTURE_DIRECT_ASSISTANT, POSTURE_DRAFT_HELPER])
@pytest.mark.parametrize("refusal", _FLAT_REFUSALS)
def test_direct_invocation_refusal_becomes_clarification(posture, refusal):
    # Resolvable-or-missing referent, no data: NEVER a flat refusal to the
    # person who invoked Genesi — ask for details instead, invent nothing.
    text, changed, reason = enforce_group_pragmatic_response(
        refusal, _role_with_posture(posture))
    assert changed is True
    assert reason == "flat_refusal_to_clarification"
    assert "non posso rispondere" not in text.lower()
    assert text.endswith("?")            # it is a clarification request
    assert not re.search(r"\d", text)    # no invented data (numbers/forecasts)


@pytest.mark.parametrize("posture", [
    POSTURE_SILENT, POSTURE_ASSISTANT_OBSERVER, POSTURE_NEUTRAL_SUPPORT,
])
def test_spontaneous_refusal_is_suppressed_to_silence(posture):
    text, changed, reason = enforce_group_pragmatic_response(
        _FLAT_REFUSALS[0], _role_with_posture(posture))
    assert changed is True
    assert reason == "flat_refusal_suppressed"
    assert text == ""   # both adapters drop empty replies (no visible send)


def test_healthy_direct_reply_passes_untouched():
    reply = "A destinazione troverete bel tempo di solito in estate!"
    text, changed, _ = enforce_group_pragmatic_response(
        reply, _role_with_posture(POSTURE_DIRECT_ASSISTANT))
    assert changed is False
    assert text == reply


# --------------------------------------------------------------------------- #
# 4. End-to-end shape on both adapters' role source: a direct invocation
#    (mention on Telegram, name-in-text on WhatsApp) classified by the SHARED
#    classifier yields direct_assistant → refusal becomes clarification.
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("kwargs", [
    {"bot_mentioned": True},                 # Telegram @mention
    {},                                       # WhatsApp: name in text only
], ids=["telegram_mention", "whatsapp_name_in_text"])
def test_refusal_on_direct_invocation_both_adapters(kwargs):
    role = classify_group_message_role(
        "genesi che tempo farà nella destinazione del viaggio?", **kwargs)
    assert role.recommended_response_posture == POSTURE_DIRECT_ASSISTANT
    text, changed, reason = enforce_group_pragmatic_response(
        _FLAT_REFUSALS[0], role)
    assert changed and reason == "flat_refusal_to_clarification"
    assert "?" in text and "non posso" not in text.lower()


# --------------------------------------------------------------------------- #
# 5. Source-level pins: both send paths route through the shared enforcement,
#    and both quote/reply contexts are attached before generation.
# --------------------------------------------------------------------------- #

def _src(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def test_both_adapters_route_replies_through_shared_enforcement():
    for path in ("core/telegram_bot.py", "core/whatsapp_bot.py"):
        src = _src(path)
        assert "enforce_group_pragmatic_response" in src, path


def test_both_adapters_attach_quoted_reply_context():
    assert "Stai rispondendo a questo tuo messaggio precedente" in _src("core/telegram_bot.py")
    assert "Stai rispondendo a un tuo messaggio precedente" in _src("core/whatsapp_bot.py")


def test_classifier_entry_uses_group_user_text_extraction():
    src = _src("core/intent_classifier.py")
    assert "extract_group_user_text(_classify_msg)" in src
    assert "extract_group_user_text(_user_part)" in src
