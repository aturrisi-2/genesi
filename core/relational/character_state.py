from typing import Dict


class CharacterState:
    """
    Stato caratteriale DERIVATO.

    - NON viene mai salvato
    - NON prende decisioni
    - NON genera testo

    Serve solo a:
    - mantenere una base caratteriale stabile
    - modulare il comportamento in base alla relazione
    """

    def __init__(self):
        # 🎯 BASE STABILE (DECISA DA TE)
        self.base = {
            "empathy": 0.7,        # empatico ma non invadente
            "question_rate": 0.2,  # poche domande
            "verbosity": 0.5,      # equilibrio
            "directness": 0.6,     # diretto ma umano
        }

    def compute(self, relational_state: Dict) -> Dict:
        """
        Calcola il carattere corrente in modo:
        - deterministico
        - clampato
        - reversibile
        """

        score = float(relational_state.get("score", 0.0))
        signals = set(relational_state.get("signals", []))

        character = self.base.copy()

        # 📈 Evoluzione continua (molto lenta)
        character["empathy"] = self._clamp(
            character["empathy"] + score * 0.2
        )

        character["question_rate"] = self._clamp(
            character["question_rate"] - score * 0.15
        )

        # 📌 Modulatori qualitativi
        if "trust_difficulty" in signals:
            character["directness"] = self._clamp(
                character["directness"] - 0.1
            )

        if "emotional_load" in signals:
            character["verbosity"] = self._clamp(
                character["verbosity"] + 0.1
            )

        return character

    @staticmethod
    def _clamp(value: float) -> float:
        return round(min(1.0, max(0.0, value)), 2)
