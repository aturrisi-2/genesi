# core/intent_engine.py
from typing import Dict, List

class IntentEngine:
    """
    Decide COME Genesi deve rispondere.
    NON genera testo.
    """

    def decide(
        self,
        user_message: str,
        cognitive_state: Dict,
        recent_memories: List[Dict],
        relevant_memories: List[Dict],
        tone: Dict
    ) -> Dict:
        print("🔥 INTENT ENGINE ATTIVO 🔥", flush=True)
        """
        Returns an intent object that describes HOW to respond.
        """

        # Default intent
        intent = {
            "should_respond": True,
            "style": "naturale",
            "depth": "breve",
            "focus": "presente",
            "use_memory": False,
            "emotional_weight": 0.4
        }

        # ---- REGOLE COGNITIVE BASE ----

        # Se l'utente fa una domanda diretta
        if "?" in user_message:
            intent["depth"] = "media"
            intent["focus"] = "risposta"

        # Se ci sono memorie rilevanti
        if relevant_memories:
            intent["use_memory"] = True
            intent["focus"] = "connessione"

        # Se il tono è emotivo
        if tone("empathy", 0) < 0.3:
            intent["style"] = "empatico"
            intent["emotional_weight"] = 0.7


        # Se Genesi è già molto attiva (conversazione lunga)
        if len(recent_memories) > 10:
            intent["depth"] = "breve"

        return intent
