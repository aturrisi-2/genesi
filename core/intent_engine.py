# core/intent_engine.py

from typing import Dict, List
import re

from storage.users import save_user


# ===============================
# NORMALIZZAZIONI SEMANTICHE
# ===============================

def normalize_profession(raw: str) -> str:
    raw = raw.lower().strip()
    for prefix in ["il ", "lo ", "la ", "un ", "uno ", "una ", "l'"]:
        if raw.startswith(prefix):
            raw = raw[len(prefix):]
    return raw.strip()


class IntentEngine:
    """
    Decide COME Genesi deve rispondere.
    NON genera testo. NON interpreta col LLM.
    Estrae identità, rileva contesto emotivo, decide profondità.
    """

    NAME_PATTERN = re.compile(
        r"\b(?:mi chiamo|il mio nome è)\s+([A-Z][a-zA-Z]+)",
        re.IGNORECASE
    )

    PROFESSION_PATTERN = re.compile(
        r"\blavoro come\s+([a-zA-Z\s]{2,20})",
        re.IGNORECASE
    )

    EMOTIONAL_SIGNALS = [
        "stanco", "stanca", "esausto", "esausta", "non ce la faccio",
        "stress", "stressato", "stressata", "ansia", "ansioso", "ansiosa",
        "triste", "tristezza", "depresso", "depressa", "giù", "giù di morale",
        "arrabbiato", "arrabbiata", "incazzato", "incazzata", "furioso", "furiosa",
        "non ne posso più", "mi hanno rotto", "sono stufo", "sono stufa",
        "mi sento solo", "mi sento sola", "non ho voglia", "non ho più voglia",
        "in crisi", "disperato", "disperata", "burnout", "crollo",
        "paura", "spaventato", "spaventata", "preoccupato", "preoccupata",
        "mi sento male", "sto male", "non sto bene", "fa schifo",
        "piango", "ho pianto", "voglio piangere"
    ]

    def decide(
        self,
        user_message: str,
        user,
        cognitive_state,
        recent_memories: List[Dict],
        relevant_memories: List[Dict],
        tone
    ) -> Dict:

        msg = user_message.strip()
        msg_lower = msg.lower()

        print(f"[INTENT] message='{msg}'", flush=True)

        # ===============================
        # MEMORIA ESPLICITA
        # ===============================
        memory_keywords = ["memorizza", "memorizzalo", "ricorda", "ricordalo", "salva", "salvalo", "ricordati", "tieni a mente"]
        explicit_memory = any(k in msg_lower for k in memory_keywords)

        # ===============================
        # INTENT BASE
        # ===============================
        intent = {
            "should_respond": True,
            "style": "presence",
            "depth": "naturale",
            "focus": "presente",
            "use_memory": explicit_memory or bool(relevant_memories),
            "emotional_weight": 0.3,
        }

        # ===============================
        # ESTRAZIONE IDENTITÀ: NOME
        # ===============================
        name_match = self.NAME_PATTERN.search(msg)
        if name_match:
            name = name_match.group(1).capitalize()
            if not hasattr(user, "profile") or user.profile is None:
                user.profile = {}
            if user.profile.get("name") != name:
                user.profile["name"] = name
                save_user(user)
                print(f"[INTENT] name_saved={name}", flush=True)
            intent["focus"] = "identità"
            intent["emotional_weight"] = 0.5

        # ===============================
        # ESTRAZIONE IDENTITÀ: PROFESSIONE
        # ===============================
        prof_match = self.PROFESSION_PATTERN.search(msg)
        if prof_match:
            profession = normalize_profession(prof_match.group(1))
            if not hasattr(user, "profile") or user.profile is None:
                user.profile = {}
            if (
                profession
                and len(profession.split()) <= 3
                and all(w.isalpha() for w in profession.split())
            ):
                if user.profile.get("profession") != profession:
                    user.profile["profession"] = profession
                    save_user(user)
                    print(f"[INTENT] profession_saved={profession}", flush=True)
                intent["focus"] = "identità"

        # ===============================
        # RILEVAMENTO EMOTIVO
        # ===============================
        has_emotion = any(signal in msg_lower for signal in self.EMOTIONAL_SIGNALS)
        if has_emotion:
            intent["emotional_weight"] = 0.7
            intent["focus"] = "presenza"
            intent["use_memory"] = True
            print(f"[INTENT] emotional_signal_detected", flush=True)

        # ===============================
        # CONTESTO DALLA MEMORIA
        # ===============================
        if relevant_memories:
            intent["use_memory"] = True
            if intent["focus"] == "presente":
                intent["focus"] = "connessione"

        # ===============================
        # MESSAGGIO BREVE / SALUTO / RITORNO
        # ===============================
        word_count = len(msg.split())
        if word_count <= 3 and not has_emotion:
            intent["depth"] = "presente"

        # ===============================
        # TONO BASSO → PIÙ PRESENZA
        # ===============================
        if getattr(tone, "empathy", 0.5) > 0.7:
            intent["emotional_weight"] = max(intent["emotional_weight"], 0.6)

        print(f"[INTENT] final={intent}", flush=True)
        return intent
