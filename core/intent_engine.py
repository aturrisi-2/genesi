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
        
        # ===============================
        # REGOLA COGNITIVA PRIORITARIA: MEMORIA
        # ===============================
        memory_keywords = ["memorizza", "memorizzalo", "ricorda", "ricordalo", "salva", "salvalo"]
        has_memory_request = any(keyword in user_message.lower() for keyword in memory_keywords)
        print(f"[INTENT_ENGINE.decide] has_memory_request = {has_memory_request}", flush=True)
        
        if has_memory_request:
            print(
                "[INTENT_ENGINE.decide] MEMORY RULE TRIGGERED | message='{}'".format(user_message),
                flush=True
            )
    
        # ===============================
        # INTENT DI DEFAULT
        # ===============================
        intent = {
            "should_respond": True,
            "style": "assertive_presence",
            "depth": "breve",
            "focus": "presente",
            "use_memory": has_memory_request,
            "emotional_weight": 0.4,
            "question_rate": 0.0
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
    
            print(f"[INTENT_ENGINE.decide] name_identity_match = True", flush=True)
            print(f"[INTENT_ENGINE.decide] question_rate = {intent['question_rate']}", flush=True)
            print(f"[INTENT_ENGINE.decide] focus = {intent['focus']}", flush=True)
            return {
                "should_respond": True,
                "style": "assertive_presence",
                "depth": "breve",
                "focus": "identità",
                "use_memory": has_memory_request,
                "emotional_weight": 0.6,
                "question_rate": 0.0
            }
    
        # ===============================
        # REGOLA IDENTITÀ: PROFESSIONE
        # ===============================
        if "lavoro come" in user_message.lower():
            import re
            profession_match = re.search(r"lavoro come\s+([a-zA-Z\s]{2,20})", user_message, re.IGNORECASE)
    
            if profession_match:
                profession = profession_match.group(1).strip().title()
    
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
                        "use_memory": has_memory_request,
                        "emotional_weight": 0.4,
                        "question_rate": 0.0
                    }

        # ===============================
        # REGOLA EMOTIVA: PERMETTI PROFONDITÀ NATURALE
        # ===============================
        emotional_phrases = [
            "stress", "stressato", "stressata", "stanco", "stanca", "stanchissimo",
            "ansia", "ansioso", "ansiosa", "preoccupato", "preoccupata", "preoccupatissima",
            "triste", "tristezza", "depresso", "depressa", "giù", "giù di morale",
            "esaurita", "burnout", "crollo", "in crisi", "disperato", "disperata"
        ]
        
        # Se c'è contenuto emotivo, permetti profondità naturale
        if any(phrase in user_message.lower() for phrase in emotional_phrases) and "?" not in user_message:
            intent["question_rate"] = 0.0  # Manteniamo poche domande
            intent["focus"] = "presenza"
            intent["depth"] = "media"  # Permetti risposte più articolate
            print(f"[INTENT_ENGINE.decide] emotional_match = True", flush=True)
            print(f"[INTENT_ENGINE.decide] question_rate = {intent['question_rate']}", flush=True)
            print(f"[INTENT_ENGINE.decide] focus = {intent['focus']}", flush=True)
    
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
        # Richieste di consiglio → permetti profondità media e focus su consiglio
        elif any(phrase in user_message.lower() for phrase in [
            "consiglio", "consigliami", "mi consigli", "cosa mi consigli", 
            "secondo te", "secondo voi", "cosa dovrei", "come posso", 
            "che faccio", "mi suggerisci", "suggerimento"
        ]):
            intent["depth"] = "media"
            intent["focus"] = "consiglio"
            intent["question_rate"] = 0.0
            print(f"[INTENT_ENGINE.decide] advice_request_detected = True", flush=True)
            print(f"[INTENT_ENGINE.decide] question_rate = {intent['question_rate']}", flush=True)
        # Richieste interpretative → permetti ipotesi e inferenze
        elif any(phrase in user_message.lower() for phrase in [
            "cosa potrebbe essere", "secondo te cos'", "da cosa può dipendere", 
            "cosa pensi sia", "perché mi fa male", "che cosa sarà", 
            "può essere", "secondo te è", "cosa mi succede"
        ]):
            intent["depth"] = "media"
            intent["focus"] = "interpretazione"
            intent["question_rate"] = 0.0
            print(f"[INTENT_ENGINE.decide] interpretation_request_detected = True", flush=True)
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
    
        print(f"[INTENT_ENGINE.decide] final_intent = {intent}", flush=True)
        print(
            "[INTENT_ENGINE.decide] FINAL use_memory = {}".format(intent.get("use_memory")),
            flush=True
        )
        return intent
