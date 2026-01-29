# core/relational_interpreter.py

from pathlib import Path
from datetime import datetime
import json

RELATIONAL_DIR = Path("data/relational")
RELATIONAL_DIR.mkdir(parents=True, exist_ok=True)

# Soglie umane (non rigide)
ACCUMULATION_THRESHOLD = 1.0
DECAY = 0.9  # dimenticanza naturale


class RelationalInterpreter:
    """
    Osserva segnali relazionali nel tempo.
    NON parla.
    NON influenza la risposta.
    Accumula lentamente come un essere umano.
    """

    def interpret(self, event: dict) -> dict:
        user_id = event["user_id"]
        text = event.get("content", {}).get("text", "").lower()
        affect = event.get("affect", {})

        signals = {}

        # ===============================
        # ESTRAZIONE SEGNALI GREZZI
        # ===============================

        if any(k in text for k in ["mi sento", "stanco", "sotto pressione"]):
            signals["emotional_load"] = 0.3

        if any(k in text for k in ["non mi fido", "non mi fido facilmente"]):
            signals["trust_difficulty"] = 0.4

        if isinstance(affect, dict):
            if any(v > 0.6 for v in affect.values()):
                signals["strong_affect"] = 0.3
        
        # ===============================
        # RILEVAMENTO FATTI PERSONALI STABILI
        # ===============================
        family_relations = ["moglie", "marito", "sorella", "fratello", "figlio", "figlia", "padre", "madre", "nonno", "nonna"]
        pet_relations = ["cane", "gatto", "gatta", "cucciolo"]
        
        # Pattern relazioni familiari
        for relation in family_relations:
            if f"mia {relation}" in text or f"mio {relation}" in text:
                signals["personal_fact_family"] = 0.5
                break
        
        # Pattern animali personali
        for pet in pet_relations:
            if f"il mio {pet}" in text or f"la mia {pet}" in text:
                signals["personal_fact_pet"] = 0.5
                break
        
        # Pattern professioni persone vicine
        if any(k in text for k in ["lavora su", "lavora con", "fa il", "fa la"]):
            signals["personal_fact_profession"] = 0.4

        if not signals:
            return {
                "relational_score": 0.0,
                "reasons": [],
                "candidate": False
            }

        state = self._load_state(user_id)

        reasons = []
        for key, value in signals.items():
            previous = state.get(key, 0.0)
            updated = previous * DECAY + value
            state[key] = round(updated, 3)

            if updated >= ACCUMULATION_THRESHOLD:
                reasons.append(key)

        self._save_state(user_id, state)
        
        # ===============================
        # SALVATAGGIO AUTOMATICO FATTI PERSONALI
        # ===============================
        personal_fact_detected = False
        fact_category = None
        fact_content = None
        
        if signals.get("personal_fact_family"):
            personal_fact_detected = True
            fact_category = "family"
            # Estrai il fatto completo dal testo originale
            original_text = event.get("content", {}).get("text", "")
            fact_content = original_text.strip()
            
        elif signals.get("personal_fact_pet"):
            personal_fact_detected = True
            fact_category = "pet"
            original_text = event.get("content", {}).get("text", "")
            fact_content = original_text.strip()
            
        elif signals.get("personal_fact_profession"):
            personal_fact_detected = True
            fact_category = "profession"
            original_text = event.get("content", {}).get("text", "")
            fact_content = original_text.strip()
        
        if personal_fact_detected and fact_content:
            try:
                from memory.episodic import store_event
                from memory.affective import compute_affect
                from memory.salience import compute_salience
                
                # Calcola salience e affect per il fatto personale
                fact_salience = compute_salience(
                    event_type="personal_fact",
                    content={"text": fact_content, "category": fact_category},
                    past_events=[]
                )
                
                fact_affect = compute_affect(
                    "personal_fact",
                    {"text": fact_content, "category": fact_category}
                )
                
                # Salva fatto personale in memoria episodica
                memory_event = store_event(
                    user_id=user_id,
                    type="personal_fact",
                    content={
                        "text": fact_content,
                        "category": fact_category,
                        "detected_by": "relational_interpreter"
                    },
                    salience=fact_salience,
                    affect=fact_affect
                )
                
                if memory_event:
                    print(f"[RELATIONAL_INTERPRETER] personal_fact detected → saving episodic memory | category={fact_category}", flush=True)
                
            except Exception as e:
                print(f"[RELATIONAL_INTERPRETER] personal_fact save failed | error={str(e)}", flush=True)

        return {
            "relational_score": round(sum(signals.values()), 2),
            "reasons": list(signals.keys()),
            "candidate": bool(reasons)
        }

    # ===============================
    # STATO RELAZIONALE PERSISTENTE
    # ===============================

    def _load_state(self, user_id: str) -> dict:
        file_path = RELATIONAL_DIR / f"{user_id}.json"
        if not file_path.exists():
            return {}

        with open(file_path, "r") as f:
            return json.load(f)

    def _save_state(self, user_id: str, state: dict):
        file_path = RELATIONAL_DIR / f"{user_id}.json"
        payload = {
            "last_update": datetime.utcnow().isoformat(),
            "signals": state
        }

        with open(file_path, "w") as f:
            json.dump(payload, f, indent=2)
