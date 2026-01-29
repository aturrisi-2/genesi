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
        r"\b(?:mi chiamo|il mio nome è)\s+([A-Z][a-zA-Z]+)",
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
        print(f"[INTENT_ENGINE.decide] incoming_message = '{user_message}'", flush=True)
        
        # 🔍 DIAGNOSI MEMORIA: check per richieste di memorizzazione
        memory_keywords = ["memorizza", "ricorda", "salva", "ricordati", "tieni a mente"]
        has_memory_request = any(keyword in user_message.lower() for keyword in memory_keywords)
        print(f"[INTENT_ENGINE.decide] has_memory_request = {has_memory_request}", flush=True)
    
        # ===============================
        # INTENT DI DEFAULT
        # ===============================
        intent = {
            "should_respond": True,
            "style": "assertive_presence",
            "depth": "breve",
            "focus": "presente",
            "use_memory": False,
            "emotional_weight": 0.4,
            "question_rate": 0.0
        }
        
        # ===============================
        # REGOLA DICHIARATIVA: MEMORIA
        # ===============================
        memory_triggers = [
            "memorizza",
            "ricorda",
            "salva",
            "tienilo a mente",
            "annota"
        ]

        if any(trigger in user_message.lower() for trigger in memory_triggers):
            intent["use_memory"] = True
            intent["focus"] = "memoria"

            print(
                "[INTENT_ENGINE.decide] MEMORY RULE TRIGGERED | message='{}'".format(user_message),
                flush=True
            )
    
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
    
            print(f"[INTENT_ENGINE.decide] name_identity_match = True", flush=True)
            print(f"[INTENT_ENGINE.decide] question_rate = {intent['question_rate']}", flush=True)
            print(f"[INTENT_ENGINE.decide] focus = {intent['focus']}", flush=True)
            return {
                "should_respond": True,
                "style": "assertive_presence",
                "depth": "breve",
                "focus": "identità",
                "use_memory": False,
                "emotional_weight": 0.6,
                "question_rate": 0.0
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

            # ✅ accettiamo SOLO professioni corte e nominali
            if (
                profession
                and len(profession.split()) <= 3
                and all(word.isalpha() for word in profession.split())
            ):
                if user.profile.get("profession") != profession:
                    user.profile["profession"] = profession
                    save_user(user)

                print(f"[INTENT_ENGINE.decide] profession_identity_match = True", flush=True)
                print(f"[INTENT_ENGINE.decide] question_rate = {intent['question_rate']}", flush=True)
                print(f"[INTENT_ENGINE.decide] focus = {intent['focus']}", flush=True)
                return {
                    "should_respond": True,
                    "style": "assertive_presence",
                    "depth": "breve",
                    "focus": "identità",
                    "use_memory": False,
                    "emotional_weight": 0.4,
                    "question_rate": 0.0
                }

        # ===============================
        # REGOLA EMOTIVA: FORZA question_rate = 0.0
        # ===============================
        emotional_phrases = [
            "stress", "stressato", "stressata", "stanco", "stanca", "stanchissimo",
            "pressione", "sotto pressione", "confuso", "confusa", "confusione",
            "ansia", "ansioso", "ansiosa", "preoccupato", "preoccupata", "preoccupazione",
            "nervoso", "nervosa", "tensione", "teso", "tesa", "frustrato", "frustrata",
            "deluso", "delusa", "delusione", "triste", "tristezza", "giù", "abbattuto",
            "sopraffatto", "sopraffatta", "sovraccarico", "sovraccarica", "esaurito",
            "esaurita", "burnout", "crollo", "in crisi", "disperato", "disperata"
        ]
        
        # Se c'è contenuto emotivo MA NESSUNA domanda esplicita
        if any(phrase in user_message.lower() for phrase in emotional_phrases) and "?" not in user_message:
            intent["question_rate"] = 0.0
            intent["focus"] = "presenza"
            intent["depth"] = "breve"
            print(f"[INTENT_ENGINE.decide] emotional_match = True", flush=True)
            print(f"[INTENT_ENGINE.decide] question_rate = {intent['question_rate']}", flush=True)
            print(f"[INTENT_ENGINE.decide] focus = {intent['focus']}", flush=True)
    
        print(
            "[INTENT_ENGINE.decide] FINAL use_memory = {}".format(intent.get("use_memory")),
            flush=True
        )
        return intent
        
        # ===============================
        # REGOLE COGNITIVE GENERICHE
        # ===============================
    
        # Domande esplicite → permetti question rate > 0
        if "?" in user_message:
            intent["depth"] = "media"
            intent["focus"] = "risposta"
            intent["question_rate"] = 0.3
            print(f"[INTENT_ENGINE.decide] explicit_question_detected = True", flush=True)
            print(f"[INTENT_ENGINE.decide] question_rate = {intent['question_rate']}", flush=True)
        # Ambiguità forte → permetti domande
        elif any(ambig in user_message.lower() for ambig in ["non so", "forse", "boh", "non sono sicuro"]):
            intent["question_rate"] = 0.2
            print(f"[INTENT_ENGINE.decide] ambiguity_detected = True", flush=True)
            print(f"[INTENT_ENGINE.decide] question_rate = {intent['question_rate']}", flush=True)
    
        if relevant_memories:
            intent["use_memory"] = True
            intent["focus"] = "connessione"
    
        if getattr(tone, "empathy", 0.5) < 0.3:
            intent["style"] = "assertive_presence"
            intent["emotional_weight"] = 0.7
    
        if len(recent_memories) > 10:
            intent["depth"] = "breve"
    
       

