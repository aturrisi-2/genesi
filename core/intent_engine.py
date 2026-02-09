# core/intent_engine.py

from typing import Dict, List
import re

from storage.users import save_user
from core.local_llm import local_llm


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

    # ===============================
    # CLOSURE INTENT TRIGGERS
    # ===============================
    CLOSURE_SOFT = ["ok", "ok grazie", "va bene", "bene", "perfetto", "grazie", "grazie mille"]
    CLOSURE_HARD = ["stop", "basta", "adesso basta", "basta così", "non voglio più", "lascia perdere"]
    CLOSURE_TRANSITION_PATTERNS = [
        re.compile(r"\b(?:ok|va bene|stop|basta)\b.*\b(?:parliamo|dimmi|raccontami|cambia|altro)\b", re.I),
        re.compile(r"\b(?:lasciamo stare|ci sentiamo dopo|a dopo|più tardi)\b", re.I),
        re.compile(r"\b(?:ok|va bene|stop|basta)\b.*\b(?:d'altro|d altro)\b", re.I),
    ]

    # ===============================
    # DUAL BRAIN — FACTUAL SIGNALS
    # ===============================
    # Se il messaggio contiene questi pattern → Genesi-Fatti (gpt-4o-mini)
    FACTUAL_KEYWORDS = [
        "meteo", "tempo fa", "temperatura", "previsioni", "piove", "pioverà",
        "notizie", "notizia", "news", "cronaca", "attualità",
        "successo oggi", "successo ieri", "cosa è successo", "cos'è successo",
        "cosa sta succedendo", "cosa succede", "ultime ore", "ultima ora",
        "quanto costa", "quanto pesa", "quanto dura", "quanto è",
        "quando è", "quando nasce", "quando muore", "quando inizia", "quando finisce",
        "dove si trova", "dove è", "dov'è",
        "come funziona", "come si fa", "come si usa",
        "cos'è", "cos è", "cosa significa", "che cos'è", "che cos è", "che significa",
        "farmaco", "farmaci", "medicina", "medicinale", "ibuprofene", "tachipirina",
        "paracetamolo", "antibiotico", "antibiotici", "dose", "dosaggio",
        "sintomo", "sintomi", "diagnosi", "effetti collaterali",
        "febbre", "mal di testa", "mal di stomaco", "pressione",
        "dolore", "dolore al petto", "dolore al braccio", "dolore alla schiena",
        "tosse", "raffreddore", "influenza", "allergia", "allergie",
        "infezione", "infiammazione", "gonfiore", "nausea", "vomito", "diarrea",
        "vertigini", "capogiro", "svenimento", "tachicardia", "respiro",
        "ricetta", "ingredienti", "calorie", "proteine",
        "capitale", "popolazione", "distanza", "altitudine",
        "chi è", "chi era", "chi ha inventato", "chi ha scritto",
        "traduzione", "traduci", "tradurre",
        "calcola", "calcolo", "formula", "equazione",
        "legge", "normativa", "codice civile", "codice penale",
        "economia", "economica", "economico", "inflazione", "pil", "spread",
        "borsa", "azioni", "mercato", "mercati", "tasso", "tassi",
        "politica", "governo", "elezioni", "parlamento",
        "guerra", "conflitto", "terremoto", "alluvione",
    ]

    FACTUAL_PATTERNS = [
        re.compile(r"\b(?:quanto|quanta|quanti|quante)\b.*\b(?:cost|pes|dur|è|sono)\b", re.I),
        re.compile(r"\b(?:quando|dove|come)\b.*\b(?:è|sono|si|nasce|muore|funziona|trova)\b", re.I),
        re.compile(r"\b(?:che|cos['']?è|cosa significa)\b", re.I),
        re.compile(r"\b(?:posso prendere|si può prendere|fa male|fa bene)\b.*\b(?:con|se|la|il)\b", re.I),
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
        # PROACTOR: VALIDAZIONE INPUT STT
        # ===============================
        
        # BLOCCO INPUT VUOTO O MINIMO
        if not msg or len(msg.strip()) < 2:
            print(f"[PROACTOR] decision=BLOCK_EMPTY input='{msg}'", flush=True)
            return {
                "should_respond": False,
                "decision": "silence",
                "reason": "empty_input"
            }
        
        # BLOCCO RIPETIZIONI E CARATTERI SPURII
        if self._is_noise_input(msg):
            print(f"[PROACTOR] decision=BLOCK_NOISE input='{msg}'", flush=True)
            return {
                "should_respond": False,
                "decision": "silence",
                "reason": "noise_input"
            }
        
                
        # ===============================
        # PERSONALPLEX 7B - PRIMARIO OBBLIGATORIO
        # ===============================
        try:
            from core.local_llm import LocalLLM
            local_llm = LocalLLM()
            
            print(f"[PROACTOR] calling PERSONALPLEX first", flush=True)
            
            # ESCALATION LOGIC: usa GPT per messaggi complessi
            msg_len = len(msg)
            needs_gpt = msg_len > 80 or any(word in msg.lower() for word in ["spiega", "perché", "come funziona", "analizza", "dettagli"])
            
            if needs_gpt:
                print(f"[PROACTOR] ESCALATION_TO_GPT message_len={msg_len} complex=true", flush=True)
                return {
                    "should_respond": True,
                    "decision": "respond",
                    "reason": "complex_message_escalate_to_gpt",
                    "brain_mode": "relazione"
                }
            
            # CHIAMATA DIRETTA PERSONALPLEX - nessun health check
            print(f"[PROACTOR] PERSONALPLEX generating response", flush=True)
            
            # Genera risposta con PersonalPlex (UNA SOLA VOLTA)
            response = local_llm.generate(msg)
            
            if response and len(response.strip()) > 0:
                print(f"[PROACTOR] PERSONALPLEX response received", flush=True)
                return {
                    "should_respond": True,
                    "decision": "respond",
                    "reason": "personalplex_primary",
                    "brain_mode": "relazione",
                    "personalplex_response": response.strip()
                }
            else:
                print(f"[PROACTOR] PERSONALPLEX empty response", flush=True)
                
        except Exception as e:
            print(f"[PROACTOR] PERSONALPLEX error: {e} - fallback to GPT", flush=True)

        print(f"[PROACTOR] decision=ESCALATE_TO_CHATGPT input='{msg}'", flush=True)

        # ===============================
        # INTENT BASE
        # ===============================
        intent = {
            "should_respond": True,
            "style": "presence",
            "depth": "naturale",
            "focus": "presente",
            "use_memory": False,
            "emotional_weight": 0.3,
        }

        # ===============================
        # CLOSURE INTENT DETECTION (contextual)
        # ===============================
        closure_level = None
        # Soft closure (short)
        if msg_lower in self.CLOSURE_SOFT:
            closure_level = "soft"
        # Hard closure (short)
        elif msg_lower in self.CLOSURE_HARD:
            closure_level = "hard"
        # Transition closure (pattern, can be longer)
        elif any(p.search(msg) for p in self.CLOSURE_TRANSITION_PATTERNS):
            closure_level = "transition"

        if closure_level:
            intent["type"] = "closure"
            intent["closure_level"] = closure_level
            intent["should_respond"] = True  # We'll decide response type in ResponseGenerator
            intent["style"] = "minimal"
            intent["depth"] = "presente"
            intent["focus"] = "chiusura"
            intent["use_memory"] = False
            intent["emotional_weight"] = 0.0
            print(f"[INTENT] closure_detected level={closure_level}", flush=True)
            # Early return: closure overrides everything else
            print(f"[INTENT] final={intent}", flush=True)
            return intent

        # ===============================
        # MEMORIA ESPLICITA
        # ===============================
        memory_keywords = ["memorizza", "memorizzalo", "ricorda", "ricordalo", "salva", "salvalo", "ricordati", "tieni a mente"]
        explicit_memory = any(k in msg_lower for k in memory_keywords)
        intent["use_memory"] = explicit_memory or bool(relevant_memories)

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
        # DUAL BRAIN ROUTING
        # ===============================
        has_factual = (
            any(kw in msg_lower for kw in self.FACTUAL_KEYWORDS)
            or any(p.search(msg) for p in self.FACTUAL_PATTERNS)
        )

        if has_emotion and has_factual:
            # Misto: emozione + fatto → fatti (il fatto domina, l'emozione è contesto)
            intent["brain_mode"] = "fatti"
            intent["emotional_context"] = True
            print(f"[INTENT] brain_mode=fatti (misto: emozione+fatto)", flush=True)
        elif has_factual:
            intent["brain_mode"] = "fatti"
            intent["emotional_context"] = False
            print(f"[INTENT] brain_mode=fatti", flush=True)
        else:
            intent["brain_mode"] = "relazione"
            print(f"[INTENT] brain_mode=relazione", flush=True)

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

    def _is_noise_input(self, msg: str) -> bool:
        """
        Verifica se l'input è rumore/nonsense STT
        """
        msg_clean = msg.strip().lower()
        
        # Input troppo corto
        if len(msg_clean) < 3:
            return True
        
        # Solo caratteri ripetuti (es "aaaa", "oooo")
        if len(set(msg_clean.replace(' ', ''))) < 3 and len(msg_clean) > 5:
            return True
        
        # Troppe parole identiche
        words = msg_clean.split()
        if len(words) > 3 and len(set(words)) < 2:
            return True
        
        # Solo vocali ripetute
        if all(c in 'aeiou' for c in msg_clean.replace(' ', '')) and len(msg_clean) > 3:
            return True
        
        # Caratteri non alfabetici eccessivi
        non_alpha = sum(1 for c in msg_clean if not c.isalpha() and c != ' ')
        if non_alpha > len(msg_clean) * 0.3:
            return True
        
        return False
    
    def _needs_local_llm_analysis(self, msg: str) -> bool:
        """
        Decide se serve analisi con Local LLM
        """
        msg_clean = msg.strip().lower()
        
        # Input ambiguo o borderline (inclusi input brevi)
        if len(msg_clean) < 5:
            return True
        
        # Contiene caratteri strani
        if any(c not in 'abcdefghijklmnopqrstuvwxyzàèéìòù ' for c in msg_clean):
            return True
        
        # Parole sospette o nonsense
        suspicious_words = ['oooo', 'aaaa', 'eeee', 'iiii', 'uuuu', 'mmm', 'nnn']
        if any(word in msg_clean for word in suspicious_words):
            return True
        
        # Rapporto spazi/parole anomalo
        words = msg_clean.split()
        if len(words) > 0 and len(msg_clean.replace(' ', '')) / len(words) < 2:
            return True
        
        return False
    
    def _is_simple_human_input(self, msg: str) -> bool:
        """
        Identifica input umani semplici che possono passare a ChatGPT
        anche senza Local LLM
        """
        msg_clean = msg.strip().lower()
        
        # Saluti e interazioni semplici
        simple_greetings = [
            'ciao', 'salve', 'buongiorno', 'buonasera', 'buonanotte',
            'ok', 'va bene', 'bene', 'perfetto', 'grazie', 'grazie mille',
            'sì', 'si', 'no', 'certo', 'sicuro', 'certamente'
        ]
        
        if msg_clean in simple_greetings:
            return True
        
        # Frasi brevi e naturali (1-3 parole)
        words = msg_clean.split()
        if len(words) <= 3 and len(msg_clean) >= 2:
            # Verifica che non siano caratteri ripetuti
            if len(set(msg_clean.replace(' ', ''))) >= len(msg_clean.replace(' ', '')) * 0.5:
                return True
        
        # Domande semplici e comuni
        simple_questions = [
            'come stai', 'come va', 'tutto bene', 'tutto ok',
            'chi sei', 'cosa fai', 'di cosa parliamo'
        ]
        
        if msg_clean in simple_questions:
            return True
        
        # Parole singole significative
        if len(words) == 1 and len(msg_clean) >= 3:
            word = words[0]
            # Esclude caratteri ripetuti
            if len(set(word)) >= len(word) * 0.6:
                return True
        
        return False
