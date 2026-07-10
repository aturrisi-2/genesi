"""Composer condiviso del prompt di gruppo (contratto unico, tutte le piattaforme).

Prima di questo modulo il wrapper del "messaggio attuale" era duplicato in tre
punti — telegram_bot._group_msg, api/chat (path gruppi Baileys/WhatsApp) e
whatsapp_bot._do_chat — con strutture divergenti. Le divergenze hanno già
prodotto bug reali fixati su un solo adapter (veto anti-contesto, hijack della
domanda inevasa, formato senza blocco identità). Regola di confine: gli adapter
calcolano SOLO i dati platform-specific (mention, reply, media, policy) e
delegano qui la composizione; il testo delle regole vive in un posto solo.

Struttura prodotta (variante standard):

    [IDENTITÀ ASSOLUTA: …]
    [MESSAGGIO ATTUALE — a cui devi rispondere]
    <Nome>: <testo>
    [FINE MESSAGGIO ATTUALE]
    (<blocchi [SISTEMA: …] estratti dal corpo>)
    [GRUPPO FAMILIARE/ESTERNO: …regole…]
    [POLICY PRAGMATICA GRUPPO / POSTURA: …]
    <group_ctx>

`core.intent_classifier.extract_group_user_text` e
`core.context_assembler.extract_current_user_text` dipendono da questi marker:
qualunque modifica alla struttura va riflessa lì (e nei test che la pinnano).
"""

from __future__ import annotations

_SISTEMA_MARKER = "\n[SISTEMA:"


def split_sistema_block(message: str) -> tuple[str, str]:
    """Separa i blocchi [SISTEMA: …] dal corpo del messaggio.

    Devono apparire DOPO [FINE MESSAGGIO ATTUALE], non dentro la riga
    "<Nome>: <testo>" — altrimenti il LLM li legge come parole dell'utente
    invece che come direttive di sistema.
    """
    msg = message or ""
    if _SISTEMA_MARKER in msg:
        idx = msg.index(_SISTEMA_MARKER)
        return msg[:idx], msg[idx:].strip()
    if msg.lstrip().startswith("[SISTEMA:"):
        return "", msg.strip()
    return msg, ""


def is_emoji_only(text: str) -> bool:
    """True se il testo è solo emoji/reazioni (stessa semantica storica TG)."""
    return all(ord(c) > 127 or c in (" ", "\n") for c in (text or "").strip())


def identity_block(sender_name: str) -> str:
    return (
        f"[IDENTITÀ ASSOLUTA: TU sei Genesi, l'AI del gruppo. "
        f"Quando leggi i messaggi dello storico NON sei nessuno di quei parlanti: "
        f"non impersonare nessun membro. Rispondi SEMPRE in prima persona come Genesi. "
        f"Il messaggio a cui DEVI rispondere è quello di {sender_name} qui sotto, "
        f"non quelli nello storico.]\n"
    )


def family_extra_rules(sender_name: str, *, photo_rules: str = "",
                       domande_rule: str = "zero domande di ritorno, ") -> str:
    """Corpo regole del gruppo familiare (contratto di continuità 84170c6)."""
    return (
        f"zero intro elaborati, {domande_rule}zero 'che bello!'. "
        f"IMPORTANTE: Sei Genesi (un'AI). Non sei la mamma o altri parenti. Non impersonare altri. "
        f"Se gli utenti festeggiano qualcuno o fanno auguri ad altri nel gruppo, non ringraziare come se fossi tu la festeggiata, ma unisciti cordialmente. "
        f"COERENZA: hai seguito la discussione recente ed entri nel discorso già informata, collegandoti al tema in corso. "
        f"Non riesumare di tua iniziativa vecchie questioni chiuse da giorni (malattie superate, problemi risolti) se {sender_name} non le cita ora; se una situazione è ancora in corso e vuoi aggiornamenti, chiedilo con delicatezza. "
        f"{photo_rules}"
    )


def family_rules_block(sender_name: str, *, loquace: bool = False,
                       extra_rules: str | None = None,
                       photo_rules: str = "",
                       domande_rule: str = "zero domande di ritorno, ") -> str:
    """Blocco regole canonico del gruppo familiare.

    `loquace` mantiene la sfumatura storica WhatsApp ("di compagnia").
    `extra_rules`, se passato, SOSTITUISCE il corpo regole (es. override foto).
    """
    measured = ("risposta misurata ma loquace e di compagnia (3-4 righe max)"
                if loquace else "risposta misurata (3-4 righe max)")
    if extra_rules is None:
        extra_rules = family_extra_rules(sender_name, photo_rules=photo_rules,
                                         domande_rule=domande_rule)
    return (
        f"\n[GRUPPO FAMILIARE: REGOLE ASSOLUTE: {measured}, "
        f"tono naturale da familiare (non da assistente), {extra_rules}"
        f"Rispondi al messaggio attuale di {sender_name} sopra restando nel filo "
        f"della conversazione in corso: tieni conto degli ultimi messaggi e del "
        f"tema di cui si sta parlando, entrando nel discorso già informata.]\n"
    )


def photo_style_override(sender_name: str) -> str:
    """Override regole per i turni-foto: stile caldo/breve uniforme su tutte le piattaforme."""
    return (
        "Stai commentando una FOTO. Reagisci come un amico affettuoso: 1-2 frasi calde e "
        "naturali (max ~25 parole), italiano colloquiale. Se la persona ritratta è chi ti "
        f"scrive ({sender_name}), rivolgiti a lui in SECONDA persona ('ti vedo', 'sei'), mai in terza. "
        "VIETATO esordire con 'Nell'immagine'/'L'immagine mostra'/'Nella foto vedo' o fare "
        "descrizioni cliniche/elenchi. Niente domande di ritorno forzate. "
    )


def compose_group_prompt(*, sender_name: str, message: str, rules_block: str,
                         pragmatic_block: str = "", group_ctx: str = "",
                         emoji_rules_block: str | None = None,
                         directive_rules_block: str | None = None) -> str:
    """Compone il prompt di gruppo. Unico produttore del wrapper per tutti gli adapter.

    Il chiamante fornisce le regole già formattate (rules_block, tipicamente da
    family_rules_block) e l'eventuale blocco pragmatico; qui vivono struttura,
    blocco identità, delimitazione del messaggio attuale e varianti
    emoji/directive-only.
    """
    clean, sistema = split_sistema_block(message or "")

    # Messaggio = SOLO direttiva di sistema (es. volti memorizzati): niente slot
    # "<Nome>: " vuoto, altrimenti il LLM dice "non vedo un messaggio".
    if not clean.strip() and sistema:
        rules = directive_rules_block if directive_rules_block is not None else rules_block
        return (
            f"{identity_block(sender_name)}"
            f"[NESSUN NUOVO MESSAGGIO TESTUALE DA {sender_name} — esegui l'azione "
            f"di sistema qui sotto e rispondi in modo naturale, in prima persona come Genesi]\n"
            f"{sistema}\n"
            f"{pragmatic_block}"
            f"{rules}"
            f"{group_ctx}"
        )

    if is_emoji_only(clean):
        emoji_block = (emoji_rules_block if emoji_rules_block is not None
                       else "[GRUPPO FAMILIARE: Reazione emoji — 1 riga max, naturale.]\n")
        return (
            f"{identity_block(sender_name)}"
            f"[MESSAGGIO ATTUALE — {sender_name}]: {clean}\n\n"
            f"{emoji_block}"
            f"{pragmatic_block}"
            f"{group_ctx}"
        )

    sistema_sep = f"\n{sistema}\n" if sistema else ""
    return (
        f"{identity_block(sender_name)}"
        f"[MESSAGGIO ATTUALE — a cui devi rispondere]\n"
        f"{sender_name}: {clean}\n"
        f"[FINE MESSAGGIO ATTUALE]\n"
        f"{sistema_sep}"
        f"{rules_block}"
        f"{pragmatic_block}"
        f"{group_ctx}"
    )
