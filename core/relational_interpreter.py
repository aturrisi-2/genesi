# core/relational_interpreter.py

from typing import Dict


class RelationalInterpreter:
    """
    Decide se un evento contiene informazioni
    rilevanti per la relazione umana.
    """

    def interpret(self, text: str, affect: Dict, salience: float) -> Dict:
        """
        Ritorna un relational signal oppure None.
        """

        # Soglia minima: se non è saliente, non conta
        if salience < 0.6:
            return None

        signal = {
            "text": text,
            "weight": salience,
            "emotional_intensity": max(affect.values()) if affect else 0.0,
            "stability": self._estimate_stability(text),
        }

        # Se non è stabile, non va nel profilo
        if signal["stability"] < 0.5:
            return None

        return signal

    def _estimate_stability(self, text: str) -> float:
        """
        Stima quanto è probabile che questa informazione
        sia stabile nel tempo.
        """
        text = text.lower()

        stable_markers = [
            "sono",
            "faccio",
            "lavoro",
            "mi chiamo",
            "amo",
            "odio",
            "mi piace",
            "sono sempre",
            "non sopporto"
        ]

        score = 0.0
        for marker in stable_markers:
            if marker in text:
                score += 0.15

        return min(score, 1.0)
