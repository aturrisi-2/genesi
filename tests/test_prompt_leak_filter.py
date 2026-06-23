"""
Test anti prompt-leakage nelle risposte di gruppo (WhatsApp/Telegram).

Verifica che il filtro rimuova/blocchi sezioni di prompt interno copiate dal
modello, senza penalizzare risposte normali o affettuose.

Copre i 10 casi richiesti:
 1. risposta normale eccellente → passa invariata
 2. "CONTESTO FAMIGLIA" → bloccata/ripulita
 3. "REGOLE DI INFERENZA" → bloccata/ripulita
 4. "DISCUSSIONE IN CORSO" → bloccata/ripulita
 5. prefisso "Genesi:" → rimosso
 6. parentesi quadre con istruzioni interne → ripulite
 7. risposta familiare/affettuosa → non penalizzata
 8. nomi reali del gruppo → restano coerenti, nessun assente inventato
 9. output WA/TG non deve contenere prompt interno
10. regressione narrativa esistente resta verde
"""
import re

from core.response_filter import (
    filter_response,
    strip_internal_prompt_leak,
    strip_leading_speaker_prefix,
    _LEAK_KW_RE,
    _last_responses,
    _repeat_counts,
)


def _no_leak(text: str) -> bool:
    """True se il testo non contiene marcatori di prompt interno."""
    return not _LEAK_KW_RE.search(text or "")


def _reset(uid: str):
    _last_responses.pop(uid, None)
    _repeat_counts.pop(uid, None)


# ── Caso 1: risposta normale eccellente → invariata ──────────────────────────
def test_excellent_normal_response_unchanged():
    text = "Che bella notizia Marco, sono contenta per te! Salutami tutti a casa."
    cleaned, heavy = strip_internal_prompt_leak(text)
    assert cleaned == text
    assert heavy is False


# ── Caso 2: CONTESTO FAMIGLIA → bloccata/ripulita ────────────────────────────
def test_contesto_famiglia_block_removed():
    text = ("Ciao a tutti!\n"
            "[CONTESTO FAMIGLIA: Trattalo con calore, NON nominare parenti assenti. "
            "Usa i gradi di parentela corretti.]")
    cleaned, heavy = strip_internal_prompt_leak(text)
    assert _no_leak(cleaned)
    assert "CONTESTO" not in cleaned
    # end-to-end: niente leak nell'output (vuoto = fallback accettabile)
    _reset("c2")
    out = filter_response(text, "c2")
    assert _no_leak(out)


# ── Caso 3: REGOLE DI INFERENZA → bloccata/ripulita ──────────────────────────
def test_regole_inferenza_removed():
    text = "Va bene zia. [REGOLE DI INFERENZA: deduci la parentela dal contesto.]"
    cleaned, heavy = strip_internal_prompt_leak(text)
    assert _no_leak(cleaned)
    _reset("c3")
    out = filter_response(text, "c3")
    assert _no_leak(out)


# ── Caso 4: DISCUSSIONE IN CORSO → bloccata/ripulita ─────────────────────────
def test_discussione_in_corso_removed():
    text = ("[DISCUSSIONE IN CORSO — messaggi recenti del gruppo:]\n"
            "  [2min fa] Rita: come state?\n"
            "[FINE DISCUSSIONE IN CORSO]\n"
            "Tutto bene qui!")
    cleaned, heavy = strip_internal_prompt_leak(text)
    assert _no_leak(cleaned)
    assert "DISCUSSIONE" not in cleaned
    assert "FINE DISCUSSIONE" not in cleaned


# ── Caso 5: prefisso "Genesi:" → rimosso ─────────────────────────────────────
def test_genesi_prefix_removed():
    assert strip_leading_speaker_prefix("Genesi: Va bene, arrivo!") == "Va bene, arrivo!"
    _reset("c5")
    out = filter_response("Genesi: Ciao Marco, come stai?", "c5")
    assert not out.lower().startswith("genesi:")
    assert "Marco" in out


# ── Caso 6: parentesi quadre con istruzioni interne → ripulite ───────────────
def test_internal_instruction_brackets_removed():
    text = "Ti penso! [REGOLA FONDAMENTALE: Rispondi SOLO a ciò che viene detto adesso.]"
    cleaned, heavy = strip_internal_prompt_leak(text)
    assert "REGOLA FONDAMENTALE" not in cleaned
    assert "Rispondi SOLO" not in cleaned
    assert "Ti penso" in cleaned


# ── Caso 7: emote/affetto innocuo → NON penalizzato ──────────────────────────
def test_affectionate_reply_not_penalized():
    text = "Ti voglio bene zia [sorride] passa una bella giornata!"
    cleaned, heavy = strip_internal_prompt_leak(text)
    assert cleaned == text          # emote [sorride] preservata
    assert heavy is False


# ── Caso 8: nomi reali del gruppo → coerenti, nessun assente inventato ───────
def test_real_group_names_preserved():
    text = "Ciao Marco e Rita! Che bello sentirvi, un abbraccio a entrambi."
    cleaned, heavy = strip_internal_prompt_leak(text)
    assert cleaned == text
    assert "Marco" in cleaned and "Rita" in cleaned
    assert heavy is False


# ── Caso 9: output WA/TG non deve contenere prompt interno ───────────────────
def test_full_group_context_leak_blocked_end_to_end():
    leaked = (
        "[GRUPPO FAMILIARE: scrive Marco. REGOLE ASSOLUTE: tono naturale.]\n"
        "[CONTESTO FAMIGLIA: Trattalo con calore. NON nominare parenti assenti.]\n"
        "[RISPOSTE RECENTI DI GENESI IN QUESTO GRUPPO:]\n"
        "  → Genesi: ciao!\n"
        "[REGOLA FONDAMENTALE: Rispondi SOLO a ciò che viene detto adesso.]\n"
        "Ciao Marco!"
    )
    _reset("c9")
    out = filter_response(leaked, "c9")
    # Output sicuro: nessuna sezione interna (vuoto = fallback/rigenerazione)
    assert _no_leak(out)
    assert "→ Genesi:" not in out
    assert "REGOLE ASSOLUTE" not in out


# ── Caso 10: regressione narrativa — risposte normali restano valide ─────────
def test_narrative_regression_clean_responses():
    _reset("c10a")
    assert filter_response("Che giornata pesante.", "c10a") == "Che giornata pesante."
    _reset("c10b")
    # frase blacklisted resta gestita come prima (rimossa → vuota o ripulita)
    out = filter_response("Capisco, deve essere difficile.", "c10b")
    assert "capisco," not in out.lower()
