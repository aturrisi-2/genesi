# Python module for shared Genesi prompt logic.

"""Shared utilities to build system‑prompt fragments used by both Telegram and WhatsApp bots.

The original bots contained duplicated logic for constructing ``extra_rules`` and a ``late wake‑up``
prompt.  Centralising this logic ensures that any future change automatically applies to all
platforms, satisfying the requirement for *global* instructions.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Constant for the "late wake‑up" prompt used when a user greets the group late.
# ---------------------------------------------------------------------------
LATE_WAKEUP_PROMPT: str = (
    "[SISTEMA: Tu hai già dato il buongiorno al gruppo stamattina. "
    "Questo utente si è svegliato (o ha scritto) tardi e ti sta salutando adesso. "
    "Rispondi con affetto e, se opportuno, con una battuta scherzosa sul fatto che è "
    "un po' in ritardo, dandogli un caloroso benvenuto nella giornata! "
    "Ignora la regola del 'rispondi in modo estremamente conciso' per questa "
    "interazione.]"
)


def _build_photo_rules(message: str) -> str:
    """Return photo‑related rule string based on detected placeholders.

    The original code inspected ``message`` for ``[Contenuto immagine:`` and for the
    ``[UNKNOWN_FACES_DETECTED]`` / ``[UNKNOWN_PETS_DETECTED]`` markers.  We keep the same
    behaviour here.
    """
    photo_rules = ""
    if "[Contenuto immagine:" in message:
        photo_rules += "Evita spiegoni descrittivi dell'immagine: fai un commento discorsivo e conciso. "
    if "[UNKNOWN_FACES_DETECTED]" in message or "[UNKNOWN_PETS_DETECTED]" in message:
        if "[UNKNOWN_PETS_DETECTED]" in message:
            photo_rules += (
                "Ci sono animali domestici sconosciuti al sistema visivo. Fai un commento affettuoso. "
                "Anche se intuisci chi sia dal profilo, DEVI CHIEDERE all\\'utente di scriverti "
                "esplicitamente come si chiama per poter memorizzare il suo aspetto visivo. "
                "REGOLA FERREA: Fai la domanda e chiedi di scriverti il nome! "
            )
        else:
            photo_rules += (
                "Ci sono persone sconosciute in foto. Fai un commento colloquiale, curioso e intelligente. "
                "Includi con molta naturalezza una domanda per chiedere chi sono (se non lo sai dal contesto), "
                "ma non essere ripetitivo se l\\'hai già chiesto di recente. "
            )
    return photo_rules


def build_extra_rules(first_name: str, chat_id: int, message: str, is_family_group: bool) -> str:
    """Construct the ``extra_rules`` block used for group messages.

    Mirrors the original logic from ``telegram_bot._group_msg`` so behaviour remains
    identical across platforms.
    """
    # Base rule for asking follow‑up questions – suppressed when unknown faces/pets are present.
    domande_rule = "zero domande di ritorno, "
    # Build photo‑related rules.
    photo_rules = _build_photo_rules(message)
    if "[UNKNOWN_FACES_DETECTED]" in message or "[UNKNOWN_PETS_DETECTED]" in message:
        domande_rule = ""

    extra_rules = (
        f"zero intro elaborati, {domande_rule}zero 'che bello!'. "
        "IMPORTANTE: Sei Genesi (un'AI). Non sei la mamma o altri parenti. "
        "Non impersonare altri. Se gli utenti festeggiano qualcuno o fanno auguri ad altri "
        "nel gruppo, non ringraziare come se fossi tu la festeggiata, ma unisciti cordialmente "
        "ai festeggiamenti rivolti a quel familiare. "
        "NON menzionare eventi passati (malattie, problemi, notizie di giorni fa) "
        "a meno che {first_name} non li citi in questo messaggio. "
        f"{photo_rules}"
    )
    # Example customisation for a known group – kept for parity with the original code.
    if chat_id == -1001267666655:
        extra_rules += (
            "CONTESTO SPECIFICO GRUPPO: Questo gruppo era nato per programmatori Swift. "
            "Il creatore, Marcello, è mancato. "
            "Oggi gli utenti rimasti interagiscono ogni tanto per parlare delle loro app, "
            "che sono in maggioranza per dispositivi Apple. "
            "Tieni a mente questo contesto se fanno domande di programmazione, Apple o app. "
            "RISOLUZIONE DOMANDE: Quando viene fatta una domanda di cui conosci la risposta o "
            "che puoi cercare, usa le tue skill di ricerca web sui siti specializzati per "
            "fornire risposte coerenti e verificate, accompagnate possibilmente da link utili "
            "(inserendo un bottone al link esterno se supportato). "
        )
    return extra_rules
