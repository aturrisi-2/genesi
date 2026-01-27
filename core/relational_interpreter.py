# core/relational_interpreter.py

from typing import Dict

class RelationalInterpreter:
    """
    Osserva segnali relazionali latenti.
    NON decide, NON salva, NON risponde.
    """

    def interpret(self, event: dict) -> dict:
        text = event.get("content", {}).get("text", "")
        salience = event.get("salience", 0.0)
        affect = event.get("affect", 0.0)  # 🔧 È UN FLOAT

        score = 0.0
        reasons = []

        # Intensità emotiva
        if affect > 0.6:
            score += 0.4
            reasons.append("emotional_intensity")

        # Salienza alta
        if salience > 0.6:
            score += 0.3
            reasons.append("high_salience")

        # Frasi introspettive / relazionali
        if any(
            phrase in text.lower()
            for phrase in [
                "mi sento",
                "non mi fido",
                "per me",
                "ho paura",
                "sono stanco",
                "mi pesa",
                "mi fa sentire"
            ]
        ):
            score += 0.3
            reasons.append("introspective_language")

        return {
            "relational_score": round(score, 2),
            "reasons": reasons,
            "candidate": score >= 0.6
        }
