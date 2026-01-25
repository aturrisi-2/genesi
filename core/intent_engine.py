# core/intent_engine.py

from typing import Dict, List
import re

from storage.users import save_user


class IntentEngine:
    """
    Decide COME Genesi deve rispondere.
    NON genera testo.
    NON interpreta semanticamente col LLM.
    Applica regole cognitive e strutturali.
    """

    # ===============================
    # REGEX CENTRALI (estendibili)
    # ===============================
    NAME_PATTERN = re.compile(
        r"\b(?:mi chiamo|il mio nome è|sono)\s+([A-Z][a-zA-Z]+)",
        re.IGNORECASE
    )

    def decide(
        self,
        user_message: str,
        user,
        cognitive_state: Dict,
        recent_memories: List[Dict],
        relevant_memories: List[Dict],
        tone: Dict
    ) -> Dict:
        """
        Ritorna un intent object che descrive COME rispondere.
        """

        print("🔥 INTENT ENGINE ATTIVO 🔥", flush=True)

        # ===============================
        # INTENT DI DEFAULT
        # ===============================
        intent = {
            "should_respond": True,
            "style": "naturale",
            "depth": "breve",
            "focus": "presente",
            "use_memory": False,
            "emotional_weight": 0.4
        }

        # ===============================
        # REGOLA IDENTITÀ: NOME UTENTE
        # ===============================
        name_match = self.NAME_PATTERN.search(user_message)

        if name_match:
            name = name_match.group(1).capitalize()

            # Inizializzazione sicura del profilo
            if not hasattr(user, "profile") or user.profile is None:
                user.profile = {}

            # Scrittura persistente solo se cambia
            if user.profile.get("name") != name:
                user.profile["name"] = name
                save_user(user)

            # Intent dedicato alla conferma identità
            return {
                "should_respond": True,
                "style": "caldo",
                "depth": "breve",
                "focus": "identità",
                "use_memory": False,
                "emotional_weight": 0.6
            }

        # ===============================
        # REGOLE COGNITIVE GENERICHE
        # ===============================

        # Domande dirette
        if "?" in user_message:
            intent["depth"] = "media"
            intent["focus"] = "risposta"

        # Memorie rilevanti disponibili
        if relevant_memories:
            intent["use_memory"] = True
            intent["focus"] = "connessione"

        # Tono emotivo rilevato
        if getattr(tone, "empathy", 0.5) < 0.3:
            intent["style"] = "empatico"
            intent["emotional_weight"] = 0.7

        # Conversazione lunga → risposte più compatte
        if len(recent_memories) > 10:
            intent["depth"] = "breve"

        return intent
