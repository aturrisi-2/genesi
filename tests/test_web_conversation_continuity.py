"""Web conversation continuity — spiegazione downgrade, primo_oggi, platform.

Covers the three defects found in the 2026-07-10 web session where Genesi
"did not follow the thread":

  1. Conversational meta follow-ups about the previous answer ("come arrivi a
     questa conclusione?") were classified `spiegazione` → apologetic
     explanation route + forced relational + synthesis diluted the contextual
     answer into generic text. Deterministic guard: only explicit
     corrections/malfunction complaints keep the explanation route.

  2. `primo_oggi` was computed from `relational.history.last_ts`, which no
     active code path wrote (frozen at the last legacy-path run) → every turn
     of a session was framed as the day's opening. Now the relational handler
     persists the timestamp after each response, and the reader also accepts
     the `relationship_history.last_interaction` schema.

  3. The web chat endpoints passed `platform=None` → "unknown" in logs and
     platform-gated logic. They now default to "web".

Offline: pure functions + static source pins. No LLM, no storage, no network.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from core.intent_classifier import is_behavior_complaint


# --------------------------------------------------------------------------- #
# 1. Behavior-complaint discriminator
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("msg", [
    "Come arrivi a questa conclusione?",
    "Cosa ti fa dire questo?",
    "Interessante. Puoi approfondire?",
    "Questo mi fa pensare. Continua.",
    "Capisco. Ma c'è anche un altro modo di vederlo?",
    "Perché pensi che sia così?",
    "Spiegami meglio questo punto.",
])
def test_conversational_followups_are_not_complaints(msg):
    assert not is_behavior_complaint(msg)


@pytest.mark.parametrize("msg", [
    "Hai sbagliato, non è quello che ho chiesto",
    "Non hai capito la mia domanda",
    "Ti avevo chiesto un'altra cosa",
    "Perché non rispondi?",
    "Ti sei dimenticata di quello che ti ho detto ieri",
    "Hai confuso i nomi di nuovo?",
    "Non funziona il promemoria che avevi impostato",
])
def test_corrections_and_malfunctions_are_complaints(msg):
    assert is_behavior_complaint(msg)


def test_first_person_mistakes_are_not_complaints():
    # L'utente parla dei PROPRI errori o di terzi: non è una lamentela su Genesi.
    assert not is_behavior_complaint("Ho sbagliato tutto nella vita, che ne pensi?")
    assert not is_behavior_complaint("Il mio capo ha detto che il progetto va rifatto")


def test_empty_or_none_is_not_complaint():
    assert not is_behavior_complaint("")
    assert not is_behavior_complaint(None)


# --------------------------------------------------------------------------- #
# 2. primo_oggi — reader accepts both schemas, writer exists on the live path
# --------------------------------------------------------------------------- #

def test_is_first_message_of_day_semantics():
    from core.calendar_awareness import is_first_message_of_day
    now = datetime.now()
    assert is_first_message_of_day(None) is True
    assert is_first_message_of_day((now - timedelta(minutes=5)).isoformat()) is False
    assert is_first_message_of_day((now - timedelta(days=2)).isoformat()) is True


def _proactor_src() -> str:
    with open("core/proactor.py", encoding="utf-8") as fh:
        return fh.read()


def test_primo_oggi_reader_accepts_active_schema():
    src = _proactor_src()
    assert 'get("relationship_history", {}).get("last_interaction")' in src


def test_relational_handler_persists_last_interaction_timestamp():
    # Il writer è la fonte di primo_oggi al turno successivo: senza,
    # ogni turno è "prima interazione della giornata".
    src = _proactor_src()
    assert '["last_ts"] = _now_iso' in src
    assert '["last_interaction"] = _now_iso' in src
    assert 'storage.save(f"relational_state:{user_id}"' in src


# --------------------------------------------------------------------------- #
# 3. spiegazione downgrade wired before the forced-relational integration
# --------------------------------------------------------------------------- #

def test_spiegazione_downgrade_runs_before_forced_integration():
    src = _proactor_src()
    i_downgrade = src.find("SPIEGAZIONE_DOWNGRADED_TO_CHAT")
    i_force = src.find("PROACTOR_FORCE_RELATIONAL_INTEGRATION")
    assert i_downgrade != -1 and i_force != -1
    assert i_downgrade < i_force
    assert "is_behavior_complaint" in src


# --------------------------------------------------------------------------- #
# 4. Web endpoints send platform="web"
# --------------------------------------------------------------------------- #

def test_web_chat_endpoints_default_platform_web():
    with open("api/chat.py", encoding="utf-8") as fh:
        src = fh.read()
    assert src.count('platform=request.platform or "web"') >= 2
    # nessun call site 1:1 rimasto senza default
    assert "platform=request.platform)" not in src
