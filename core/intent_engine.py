# core/intent_engine.py

from typing import Dict, List
import re

from storage.users import save_user


# ===============================
# NORMALIZZAZIONI SEMANTICHE
# ===============================

def normalize_profession(raw: str) -> str:
    """
    Normalizza una professione in forma umana stabile.
    Esempi:
    - 'il construction manager' -> 'construction manager'
    - 'un muratore' -> 'muratore'
    - 'una designer' -> 'designer'
    """
    raw = raw.lower().strip()

    for prefix in ["il ", "lo ", "la ", "un ", "uno ", "una ", "l'"]:
        if raw.startswith(prefix):
            raw = raw[len(prefix):]

    return raw.strip()


class IntentEngine:
    """
    Decide COME Genesi deve rispondere.
    NON genera testo.
    NON interpreta semanticamente col LLM.
    Applica regole cognitive e strutturali.
    """

    # ===============================
    # REGEX CENTRALI (ESTENDIBILI)
    # ===============================

    NAME_PATTERN = re.compile(
        r"\b(?:mi chiamo|il mio nome è|sono)\s+([A-Z][a-zA-Z]+)",
        re.IGNORECASE
    )

    PROFESSION_PATTERN = re.compile(
        r"\b(?:faccio|lavoro come|sono un|sono una)\s+([a-zA-Z\s]+)",
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
        # REGOLA IDENTITÀ: NOME
        # ===============================
        name_match = self.NAME_PATTERN.search(user_message)

        if name_match:
            name = name_match.group(1).capitalize()

            if not hasattr(user, "profile") or user.profile is None:
                user.profile = {}

            if user.profile.get("name") != name:
                user.profile["name"] = name
                save_user(user)

            return {
                "should_respond": True,
                "style": "caldo",
                "depth": "breve",
                "focus": "identità",
                "use_memory": False,
                "emotional_weight": 0.6
            }

        # ===============================
        # REGOLA IDENTITÀ: PROFESSIONE
        # ===============================
        profession_match = self.PROFESSION_PATTERN.search(user_message)

        if profession_match:
            profession_raw = profession_match.group(1)
            profession = normalize_profession(profession_raw)

            if not hasattr(user, "profile") or user.profile is None:
                user.profile = {}

            if user.profile.get("profession") != profession:
                user.profile["profession"] = profession
                save_user(user)

            return {
                "should_respond": True,
                "style": "naturale",
                "depth": "breve",
                "focus": "identità",
                "use_memory": False,
                "emotional_weight": 0.4
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
