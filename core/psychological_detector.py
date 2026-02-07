# core/psychological_detector.py
# Rileva automaticamente contesti psicologici delicati.
# NON è un sistema diagnostico. NON sostituisce un professionista.

import re
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Optional

from core.log import log as _log

# ===============================
# SEGNALI DI DISTRESS (PESATI)
# ===============================
# Ogni segnale ha un peso. La somma determina l'attivazione.
# Livelli: mild (0.2), moderate (0.4), severe (0.6), critical (0.9)

DISTRESS_SIGNALS = {
    # --- CRITICAL: pensieri autolesivi, suicidio ---
    "critical": {
        "weight": 0.9,
        "patterns": [
            r"\b(?:voglio morire|non voglio più vivere|mi voglio uccidere)\b",
            r"\b(?:voglio farla finita|meglio se non ci fossi)\b",
            r"\b(?:mi faccio del male|mi taglio|autolesion)\b",
            r"\b(?:suicid|togliermi la vita|non ha senso vivere)\b",
            r"\b(?:sarebbe meglio se morissi|nessuno noterebbe)\b",
            r"\b(?:non ce la faccio più a vivere|non voglio svegliarmi)\b",
        ]
    },
    # --- SEVERE: crisi acuta, disperazione ---
    "severe": {
        "weight": 0.6,
        "patterns": [
            r"\b(?:sono disperato|sono disperata|non ce la faccio più)\b",
            r"\b(?:non vedo via d'uscita|non c'è speranza)\b",
            r"\b(?:crollo|sto crollando|sono al limite)\b",
            r"\b(?:attacco di panico|non riesco a respirare)\b",
            r"\b(?:mi sento vuoto|mi sento vuota|non sento più niente)\b",
            r"\b(?:ho perso tutto|non ho più niente)\b",
            r"\b(?:nessuno mi capisce|sono completamente solo)\b",
            r"\b(?:nessuno mi capisce|sono completamente sola)\b",
            r"\b(?:non valgo niente|non valgo nulla|sono inutile)\b",
            r"\b(?:mi odio|mi faccio schifo)\b",
        ]
    },
    # --- MODERATE: sofferenza emotiva significativa ---
    "moderate": {
        "weight": 0.4,
        "patterns": [
            r"\b(?:depresso|depressa|depressione)\b",
            r"\b(?:ansia forte|ansia costante|ansia che non passa)\b",
            r"\b(?:non dormo|insonnia|non riesco a dormire)\b",
            r"\b(?:lutto|è morto|è morta|ho perso mia|ho perso mio)\b",
            r"\b(?:mi hanno lasciato|mi ha lasciato|separazione|divorzio)\b",
            r"\b(?:abuso|violenza|maltrattamento)\b",
            r"\b(?:trauma|traumatizzato|traumatizzata)\b",
            r"\b(?:disturbo alimentare|anoressia|bulimia)\b",
            r"\b(?:non mangio|non riesco a mangiare|non ho appetito)\b",
            r"\b(?:piango sempre|piango ogni giorno|non smetto di piangere)\b",
            r"\b(?:solitudine|mi sento solo|mi sento sola)\b",
            r"\b(?:burnout|esaurimento nervoso|esaurito|esaurita)\b",
            r"\b(?:psicologo|psicologa|terapeuta|terapia|psichiatra)\b",
        ]
    },
    # --- MILD: disagio emotivo, vulnerabilità ---
    "mild": {
        "weight": 0.2,
        "patterns": [
            r"\b(?:mi sento giù|giù di morale|giornata nera)\b",
            r"\b(?:stanco di tutto|stanca di tutto)\b",
            r"\b(?:non ho voglia di niente|non mi interessa più niente)\b",
            r"\b(?:mi sento perso|mi sento persa|confuso|confusa)\b",
            r"\b(?:non so cosa fare della mia vita)\b",
            r"\b(?:mi sento in colpa|senso di colpa)\b",
            r"\b(?:ho paura|sono spaventato|sono spaventata)\b",
            r"\b(?:mi vergogno|vergogna)\b",
            r"\b(?:non mi sento abbastanza|non sono abbastanza)\b",
            r"\b(?:fatico a|faccio fatica a)\b.*\b(?:alzarmi|uscire|lavorare|studiare)\b",
        ]
    },
}

# Soglia di attivazione del ramo psicologico
ACTIVATION_THRESHOLD = 0.35
# Soglia per segnali critici (attivazione immediata)
CRITICAL_THRESHOLD = 0.8
# Numero di messaggi neutri consecutivi per disattivare
DEACTIVATION_NEUTRAL_COUNT = 3

# Directory per stato detector per-utente
PSY_DETECTOR_DIR = Path("data/psychological/detector")
PSY_DETECTOR_DIR.mkdir(parents=True, exist_ok=True)


def detect(user_id: str, message: str) -> Dict:
    """
    Analizza un messaggio e determina se attivare il ramo psicologico.
    
    Returns:
        {
            "active": bool,           # ramo psicologico attivo
            "severity": str,          # "none", "mild", "moderate", "severe", "critical"
            "score": float,           # punteggio distress 0.0-1.0
            "signals": list,          # segnali rilevati
            "crisis": bool,           # segnali critici presenti
            "reason": str,            # motivo attivazione/disattivazione
        }
    """
    msg_lower = message.lower().strip()
    state = _load_state(user_id)
    
    # Rileva segnali nel messaggio corrente
    current_signals = []
    current_score = 0.0
    max_severity = "none"
    severity_order = {"none": 0, "mild": 1, "moderate": 2, "severe": 3, "critical": 4}
    
    for severity, config in DISTRESS_SIGNALS.items():
        for pattern in config["patterns"]:
            try:
                if re.search(pattern, msg_lower):
                    current_signals.append(severity)
                    current_score += config["weight"]
                    if severity_order.get(severity, 0) > severity_order.get(max_severity, 0):
                        max_severity = severity
            except re.error:
                continue
    
    # Cap score a 1.0
    current_score = min(current_score, 1.0)
    
    # Aggiorna stato persistente
    is_crisis = max_severity == "critical"
    was_active = state.get("active", False)
    
    if current_score >= CRITICAL_THRESHOLD or is_crisis:
        # Attivazione immediata per segnali critici
        active = True
        reason = "Segnali critici rilevati"
        state["neutral_count"] = 0
        state["activation_time"] = datetime.utcnow().isoformat()
        
    elif current_score >= ACTIVATION_THRESHOLD:
        # Attivazione per accumulo segnali
        active = True
        reason = f"Distress rilevato (score={current_score:.2f})"
        state["neutral_count"] = 0
        if not was_active:
            state["activation_time"] = datetime.utcnow().isoformat()
        
    elif was_active and current_score < ACTIVATION_THRESHOLD:
        # Potenziale disattivazione — conta messaggi neutri
        neutral_count = state.get("neutral_count", 0) + 1
        state["neutral_count"] = neutral_count
        
        if neutral_count >= DEACTIVATION_NEUTRAL_COUNT:
            active = False
            reason = f"Contesto rientrato ({neutral_count} messaggi neutri)"
            state["deactivation_time"] = datetime.utcnow().isoformat()
        else:
            active = True
            reason = f"Ramo ancora attivo (neutri={neutral_count}/{DEACTIVATION_NEUTRAL_COUNT})"
    else:
        active = False
        reason = "Nessun segnale di distress"
    
    state["active"] = active
    state["last_severity"] = max_severity
    state["last_score"] = current_score
    state["last_check"] = datetime.utcnow().isoformat()
    
    _save_state(user_id, state)
    
    result = {
        "active": active,
        "severity": max_severity,
        "score": round(current_score, 3),
        "signals": current_signals,
        "crisis": is_crisis,
        "reason": reason,
    }
    
    _log("PSYCH_DETECT", user_id=user_id, active=active,
         score=current_score, severity=max_severity, crisis=is_crisis,
         reason=reason)
    
    return result


def is_active(user_id: str) -> bool:
    """Controlla se il ramo psicologico è attivo per un utente."""
    state = _load_state(user_id)
    return state.get("active", False)


def _load_state(user_id: str) -> dict:
    path = PSY_DETECTOR_DIR / f"{user_id}.json"
    if not path.exists():
        return {"active": False, "neutral_count": 0}
    try:
        with open(path, "r") as f:
            data = json.load(f)
            return data.get("state", {"active": False, "neutral_count": 0})
    except (json.JSONDecodeError, KeyError):
        return {"active": False, "neutral_count": 0}


def _save_state(user_id: str, state: dict):
    path = PSY_DETECTOR_DIR / f"{user_id}.json"
    payload = {
        "user_id": user_id,
        "last_update": datetime.utcnow().isoformat(),
        "state": state,
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
