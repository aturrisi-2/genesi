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
            r"\b(?:voglio morire|non voglio pi[uù] vivere|mi voglio uccidere)\b",
            r"\b(?:voglio farla finita|meglio se non ci fossi)\b",
            r"\b(?:mi faccio del male|mi taglio|autolesion)\b",
            r"\b(?:suicid|togliermi la vita|non ha senso vivere)\b",
            r"\b(?:sarebbe meglio se morissi|nessuno noterebbe)\b",
            r"\b(?:non ce la faccio pi[uù] a vivere|non voglio svegliarmi)\b",
        ]
    },
    # --- SEVERE: crisi acuta, disperazione ---
    "severe": {
        "weight": 0.6,
        "patterns": [
            r"\b(?:sono disperato|sono disperata|non ce la faccio pi[uù])\b",
            r"\b(?:non vedo via d'uscita|non c'[eè] speranza)\b",
            r"\b(?:crollo|sto crollando|sono al limite)\b",
            r"\b(?:attacco di panico|non riesco a respirare)\b",
            r"\b(?:mi sento vuoto|mi sento vuota|non sento pi[uù] niente)\b",
            r"\b(?:ho perso tutto|non ho pi[uù] niente)\b",
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
            r"(?:mi sento gi[uù]|gi[uù] di morale|giornata nera)",
            r"(?:stanco di tutto|stanca di tutto)",
            r"(?:non ho voglia di niente|non mi interessa pi[uù] niente)",
            r"(?:mi sento perso|mi sento persa|confuso|confusa)",
            r"non so cosa fare della mia vita",
            r"(?:mi sento in colpa|senso di colpa)",
            r"(?:ho paura|sono spaventato|sono spaventata)",
            r"(?:mi vergogno|vergogna)",
            r"(?:non mi sento abbastanza|non sono abbastanza)",
            r"(?:fatico a|faccio fatica a).{0,15}(?:alzarmi|uscire|lavorare|studiare)",
            # --- Pattern colloquiali ampi ---
            r"mi sento.{0,15}(?:gi[uù]|male|uno schifo|di merda|a terra)",
            r"(?:stanco|stanca)\s+(?:mentalmente|psicologicamente|emotivamente|dentro)",
            r"non sto bene",
            r"non sto bene con la testa",
            r"sto male",
            r"mi sento.{0,10}(?:triste|vuoto|vuota|solo|sola|perso|persa)",
            r"(?:periodo|momento|fase).{0,15}(?:difficile|brutto|nero|pesante|duro)",
            r"non ce la faccio",
            r"sono.{0,8}(?:stanco|stanca|esausto|esaurita|distrutto|distrutta)",
            r"(?:mi pesa|mi pesa tutto|tutto pesa)",
            r"non ho (?:pi[uù] )?(?:forze|energia|voglia)",
            r"(?:ansia|ansioso|ansiosa)",
            r"(?:triste|tristezza)",
            r"piango",
            r"(?:non riesco a|faccio fatica a)\s*(?:concentrarmi|andare avanti|reagire)",
        ]
    },
}

# ===============================
# EMOTIONAL BOOST KEYWORDS
# ===============================
# Parole singole che indicano contesto emotivo.
# Ogni match aggiunge +0.10 al punteggio (cumulabile max +0.20).
# Servono a catturare segnali che i pattern strutturati non coprono.
EMOTIONAL_BOOST_KEYWORDS = [
    "stanco", "stanca", "esausto", "esausta",
    "ansia", "ansioso", "ansiosa",
    "triste", "tristezza", "depresso", "depressa",
    "paura", "spaventato", "spaventata",
    "stress", "stressato", "stressata",
    "solo", "sola", "solitudine",
    "giù", "giu", "male", "piango", "piangere",
    "crollo", "crollare", "vuoto", "vuota",
    "perso", "persa", "confuso", "confusa",
    "soffro", "soffrire", "sofferenza",
    "incubo", "incubi", "insonnia",
    "disperato", "disperata",
]
EMOTIONAL_BOOST_WEIGHT = 0.10
EMOTIONAL_BOOST_CAP = 0.20

# Soglia di attivazione del ramo psicologico
ACTIVATION_THRESHOLD = 0.20
# Soglia per segnali critici (attivazione immediata)
CRITICAL_THRESHOLD = 0.8
# Numero di messaggi neutri consecutivi per disattivare
DEACTIVATION_NEUTRAL_COUNT = 3

# ===============================
# SOGLIA DINAMICA (MOMENTUM)
# ===============================
# Messaggi negativi consecutivi aggiungono un bonus cumulativo.
# Questo evita che un singolo messaggio moderato venga ignorato
# quando fa parte di una sequenza di sofferenza.
MOMENTUM_BONUS = 0.08   # per messaggio negativo consecutivo
MOMENTUM_CAP = 0.24     # max 3 messaggi di accumulo

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
    
    # ===============================
    # FASE 1: Pattern strutturati
    # ===============================
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
    
    # ===============================
    # FASE 2: Emotional boost keywords
    # ===============================
    emotional_signal = False
    boost_score = 0.0
    boost_words = []
    for kw in EMOTIONAL_BOOST_KEYWORDS:
        if re.search(r"\b" + re.escape(kw) + r"\b", msg_lower):
            emotional_signal = True
            boost_score += EMOTIONAL_BOOST_WEIGHT
            boost_words.append(kw)
            if boost_score >= EMOTIONAL_BOOST_CAP:
                break
    
    boost_score = min(boost_score, EMOTIONAL_BOOST_CAP)
    current_score += boost_score
    
    # Se boost ha rilevato segnali ma nessun pattern strutturato, severity = mild
    if emotional_signal and max_severity == "none":
        max_severity = "mild"
    
    # ===============================
    # FASE 3: Soglia dinamica (momentum)
    # ===============================
    has_distress = current_score >= ACTIVATION_THRESHOLD or emotional_signal or len(current_signals) > 0
    consecutive = state.get("consecutive_distress", 0)
    
    if has_distress:
        consecutive += 1
        momentum = min(consecutive * MOMENTUM_BONUS, MOMENTUM_CAP)
        current_score += momentum
        if momentum > 0:
            _log("PSYCH_MOMENTUM", user_id=user_id,
                 consecutive=consecutive, bonus=momentum,
                 score_after=current_score)
    else:
        consecutive = 0
    
    state["consecutive_distress"] = consecutive
    
    # Cap score a 1.0
    current_score = min(current_score, 1.0)
    
    # ===============================
    # FASE 4: Decisione attivazione
    # ===============================
    is_crisis = max_severity == "critical"
    was_active = state.get("active", False)
    
    if current_score >= CRITICAL_THRESHOLD or is_crisis:
        active = True
        reason = "critical distress signals"
        state["neutral_count"] = 0
        state["activation_time"] = datetime.utcnow().isoformat()
        
    elif current_score >= ACTIVATION_THRESHOLD:
        active = True
        reason = f"{max_severity} emotional distress (score={current_score:.2f})"
        state["neutral_count"] = 0
        if not was_active:
            state["activation_time"] = datetime.utcnow().isoformat()
        
    elif was_active and current_score < ACTIVATION_THRESHOLD:
        # ===============================
        # DECAY esplicito
        # ===============================
        neutral_count = state.get("neutral_count", 0) + 1
        state["neutral_count"] = neutral_count
        
        _log("PSYCH_DECAY", user_id=user_id,
             neutral_counter=f"{neutral_count}/{DEACTIVATION_NEUTRAL_COUNT}")
        
        if neutral_count >= DEACTIVATION_NEUTRAL_COUNT:
            active = False
            reason = f"context normalized ({neutral_count} neutral messages)"
            state["deactivation_time"] = datetime.utcnow().isoformat()
            state["consecutive_distress"] = 0
            _log("PSYCH_DECAY", user_id=user_id,
                 completed=True, action="reverting to standard branch")
        else:
            active = True
            reason = f"still active (neutral={neutral_count}/{DEACTIVATION_NEUTRAL_COUNT})"
    else:
        active = False
        reason = "below threshold"
    
    state["active"] = active
    state["last_severity"] = max_severity
    state["last_score"] = current_score
    state["last_check"] = datetime.utcnow().isoformat()
    
    _save_state(user_id, state)
    
    decision = "ACTIVE" if active else "INACTIVE"
    
    result = {
        "active": active,
        "severity": max_severity,
        "score": round(current_score, 3),
        "signals": current_signals,
        "crisis": is_crisis,
        "reason": reason,
        "emotional_signal": emotional_signal,
        "consecutive_distress": consecutive,
    }
    
    _log("PSYCH_DETECT", user_id=user_id,
         emotional_signal=emotional_signal,
         score=current_score, severity=max_severity,
         decision=decision, reason=reason)
    
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
    PSY_DETECTOR_DIR.mkdir(parents=True, exist_ok=True)
    path = PSY_DETECTOR_DIR / f"{user_id}.json"
    payload = {
        "user_id": user_id,
        "last_update": datetime.utcnow().isoformat(),
        "state": state,
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=2)
