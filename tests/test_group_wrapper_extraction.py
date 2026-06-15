"""Regressione: estrazione testo utente dal wrapper di gruppo.

Radice di due difetti (validati live 2026-06-15, post-deploy 21c4bdf):
- chat_memory salvava il wrapper intero come user_message (filo gruppi corrotto).
- is_document_reference girava sul wrapper → parole "foto"/"immagine" nello storico
  rendevano _references=True a ogni turno → DOCUMENT_CONTEXT_SKIP non scattava mai.

Fix: extract_current_user_text isola il solo testo dell'utente prima di entrambi.
"""

from core.context_assembler import extract_current_user_text, is_document_reference


_IDENT = "[IDENTITÀ ASSOLUTA: TU sei Genesi, l'AI del gruppo. Il messaggio a cui DEVI rispondere è quello di Alfio qui sotto.]"
_HIST = "[GRUPPO FAMILIARE: storico — Nella foto vedo Ennio. ti ho riconosciuto in foto, bella immagine]"


def _std(text, name="Alfio"):
    return (f"{_IDENT}\n[MESSAGGIO ATTUALE — a cui devi rispondere]\n"
            f"{name}: {text}\n[FINE MESSAGGIO ATTUALE]\n\n[GRUPPO: tono]\n{_HIST}")


def test_standard_wrapper_extracts_clean_text():
    assert extract_current_user_text(_std("Genesi che ore sono?")) == "Genesi che ore sono?"


def test_emoji_variant():
    msg = f"{_IDENT}\n[MESSAGGIO ATTUALE — Alfio]: 👍👍\n\n[GRUPPO: Reazione emoji]"
    assert extract_current_user_text(msg) == "👍👍"


def test_directive_only_has_no_user_text():
    msg = (f"{_IDENT}\n[NESSUN NUOVO MESSAGGIO TESTUALE DA Alfio — esegui azione]\n"
           f"[SISTEMA: Hai memorizzato Rita in foto]")
    assert extract_current_user_text(msg) == ""


def test_plain_message_unchanged():
    assert extract_current_user_text("Genesi che ore sono?") == "Genesi che ore sono?"


def test_fallback_strips_only_group_ctx():
    assert extract_current_user_text("ciao a tutti\n[GRUPPO: x]") == "ciao a tutti"


def test_empty():
    assert extract_current_user_text("") == ""
    assert extract_current_user_text(None) == ""


# --- Il punto chiave: il gate documenti non deve più triggare sullo storico ---

def test_doc_gate_no_false_positive_from_history():
    # Storico pieno di "foto"/"immagine" ma l'utente chiede l'ora.
    wrapped = _std("Genesi che ore sono?")
    assert is_document_reference(wrapped) is True          # vecchio comportamento (bug)
    assert is_document_reference(extract_current_user_text(wrapped)) is False  # fix


def test_doc_gate_keeps_genuine_reference():
    # Se l'utente referenzia davvero la foto, deve restare True.
    wrapped = _std("cosa vedi nella foto?")
    assert is_document_reference(extract_current_user_text(wrapped)) is True
