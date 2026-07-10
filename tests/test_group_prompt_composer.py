"""Shared group prompt composer — structure, contract and adapter wiring pins.

The group "current message" wrapper used to be duplicated in three places
(telegram_bot._group_msg, api/chat WhatsApp-group endpoint, whatsapp_bot
_do_chat) with diverging structures; divergences produced real bugs fixed on a
single adapter at a time (anti-context veto, unanswered-question hijack,
missing identity block). These tests pin the single source of truth
(core.group_prompt_composer) and that all three call sites route through it.

Offline: pure functions + static source checks. No LLM, no storage, no
transport. Fixtures are generic.
"""

from __future__ import annotations

from core.group_prompt_composer import (
    compose_group_prompt,
    family_extra_rules,
    family_rules_block,
    identity_block,
    is_emoji_only,
    photo_style_override,
    split_sistema_block,
)
from core.intent_classifier import extract_group_user_text


SENDER = "Utente1"
CTX = "[INFO GRUPPO: Ti trovi nel gruppo 'Prova']\n[DISCUSSIONE IN CORSO — messaggi recenti del gruppo:]\n  [5min fa] Utente2: ciao\n[FINE DISCUSSIONE IN CORSO]\n"
PRAG = "[POLICY PRAGMATICA GRUPPO: interpreta il ruolo.]\n[POSTURA: direct_assistant.]\n"


def _standard(msg: str) -> str:
    return compose_group_prompt(
        sender_name=SENDER, message=msg,
        rules_block=family_rules_block(SENDER),
        pragmatic_block=PRAG, group_ctx=CTX,
    )


# --------------------------------------------------------------------------- #
# Structure — standard variant
# --------------------------------------------------------------------------- #

def test_standard_prompt_structure_and_order():
    out = _standard("genesi che tempo farà domani?")
    i_ident = out.find("[IDENTITÀ ASSOLUTA")
    i_msg = out.find("[MESSAGGIO ATTUALE — a cui devi rispondere]")
    i_body = out.find(f"{SENDER}: genesi che tempo farà domani?")
    i_fine = out.find("[FINE MESSAGGIO ATTUALE]")
    i_rules = out.find("[GRUPPO FAMILIARE:")
    i_prag = out.find("[POLICY PRAGMATICA GRUPPO")
    i_ctx = out.find("[DISCUSSIONE IN CORSO")
    assert -1 not in (i_ident, i_msg, i_body, i_fine, i_rules, i_prag, i_ctx)
    assert i_ident < i_msg < i_body < i_fine < i_rules < i_prag < i_ctx


def test_sistema_block_moved_after_fine_messaggio():
    out = _standard("ok grazie\n[SISTEMA: azione di sistema completata]")
    i_fine = out.find("[FINE MESSAGGIO ATTUALE]")
    i_sist = out.find("[SISTEMA: azione di sistema completata]")
    assert i_fine != -1 and i_sist != -1 and i_sist > i_fine
    # Il blocco sistema NON deve stare dentro la riga "<Nome>: <testo>".
    body_line = [l for l in out.splitlines() if l.startswith(f"{SENDER}: ")][0]
    assert "[SISTEMA:" not in body_line


def test_emoji_variant():
    out = _standard("😘😘")
    assert f"[MESSAGGIO ATTUALE — {SENDER}]: 😘😘" in out
    assert "[FINE MESSAGGIO ATTUALE]" not in out
    assert "Reazione emoji" in out


def test_directive_only_variant():
    out = compose_group_prompt(
        sender_name=SENDER, message="[SISTEMA: volti memorizzati]",
        rules_block=family_rules_block(SENDER),
        pragmatic_block=PRAG, group_ctx=CTX,
        directive_rules_block="\n[GRUPPO FAMILIARE: tono naturale, esegui e commenta.]\n",
    )
    assert f"[NESSUN NUOVO MESSAGGIO TESTUALE DA {SENDER}" in out
    assert "[SISTEMA: volti memorizzati]" in out
    assert "[MESSAGGIO ATTUALE" not in out


# --------------------------------------------------------------------------- #
# Rules contract (continuity, no hard veto)
# --------------------------------------------------------------------------- #

def test_family_rules_keep_continuity_and_have_no_hard_veto():
    rules = family_rules_block(SENDER)
    assert "entrando nel discorso già informata" in rules
    assert "COERENZA: hai seguito la discussione recente" in rules
    for veto in ("Rispondi SOLO a ciò che viene detto ADESSO",
                 "Rispondi SOLO al messaggio attuale",
                 "solo al messaggio attuale"):
        assert veto not in rules
    # soft guard retained
    assert "Non riesumare" in rules


def test_family_rules_loquace_and_photo_override():
    assert "loquace e di compagnia" in family_rules_block(SENDER, loquace=True)
    assert "loquace" not in family_rules_block(SENDER)
    override = family_rules_block(SENDER, extra_rules=photo_style_override(SENDER))
    assert "Stai commentando una FOTO" in override
    assert "zero intro elaborati" not in override
    # il corpo standard resta disponibile per la variante directive-only
    assert "zero intro elaborati" in family_extra_rules(SENDER)


# --------------------------------------------------------------------------- #
# Round-trip with the intent-classification extractor
# --------------------------------------------------------------------------- #

def test_composer_output_roundtrips_through_intent_extraction():
    user_text = "genesi che tempo farà nella destinazione del viaggio?"
    assert extract_group_user_text(_standard(user_text)) == user_text


def test_roundtrip_preserves_media_marker():
    user_text = "guarda qui\n[Contenuto immagine: un piatto colorato]"
    out = extract_group_user_text(_standard(user_text))
    assert "[Contenuto immagine:" in out


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def test_split_sistema_block():
    assert split_sistema_block("ciao\n[SISTEMA: x]") == ("ciao", "[SISTEMA: x]")
    assert split_sistema_block("[SISTEMA: x]") == ("", "[SISTEMA: x]")
    assert split_sistema_block("solo testo") == ("solo testo", "")


def test_is_emoji_only():
    assert is_emoji_only("😘😘 ❤️")
    assert not is_emoji_only("ciao 😘")


def test_identity_block_names_sender():
    assert SENDER in identity_block(SENDER)


# --------------------------------------------------------------------------- #
# Wiring pins: one composer, three call sites; api/chat hijack gate present.
# --------------------------------------------------------------------------- #

def _src(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def test_all_three_adapters_use_the_shared_composer():
    for path in ("core/telegram_bot.py", "core/whatsapp_bot.py", "api/chat.py"):
        assert "compose_group_prompt" in _src(path), path


def test_api_chat_gates_priority_injection_on_direct_invocation():
    src = _src("api/chat.py")
    assert "addresses_genesi_directly" in src
    # il vecchio wrapper inline con mini-veto è sparito
    assert "Rispondi SOLO al messaggio attuale, tenendo conto del filo nello storico" not in src


def test_no_inline_identity_block_left_in_adapters():
    # Il blocco identità vive solo nel composer.
    for path in ("core/telegram_bot.py", "core/whatsapp_bot.py", "api/chat.py"):
        assert "[IDENTITÀ ASSOLUTA" not in _src(path), path
    assert "[IDENTITÀ ASSOLUTA" in _src("core/group_prompt_composer.py")
