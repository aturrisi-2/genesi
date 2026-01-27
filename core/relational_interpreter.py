# core/relational_interpreter.py

from typing import Dict

class RelationalInterpreter:
    """
    Valuta se un evento ha POTENZIALE relazionale.
    NON salva.
    NON modifica il profilo.
    NON prende decisioni definitive.
    """

    def interpret(self, event: Dict) -> Dict:
        """
        Ritorna una valutazione relazionale dell'evento.
        """

        score = 0.0
        reasons = []

        text = event.get("content", {}).get("text", "").lower()
        affect = event.get("affect", {})
        salience = event.get("salience", 0.0)

        # 1️⃣ Carico emotivo
        if any(v > 0.6 for v in affect.values()):
            score += 0.4
            reasons.append("emozione_intensa")

        # 2️⃣ Forma personale
        if any(p in text for p in ["io ", "mi ", "per me", "mi sento"]):
            score += 0.3
            reasons.append("coinvolgimento_personale")

        # 3️⃣ Peso dell'evento
        if salience > 0.6:
            score += 0.2
            reasons.append("evento_saliente")

        # Clamp
        score = min(score, 1.0)

        return {
            "relational_score": round(score, 2),
            "reasons": reasons,
            "candidate": score >= 0.5
        }
