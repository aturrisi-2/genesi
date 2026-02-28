"""
INTENT CLASSIFIER - Genesi Core v2
Architettura separata: Chat libera vs Tecnica
1 intent → 1 funzione con Proactor
"""

import re
import logging
from typing import Dict, Optional
from core.log import log

logger = logging.getLogger(__name__)

EMOTIONAL_KEYWORDS = [
    "mi sento", "sono triste", "sono solo", "mi sento solo",
    "sono arrabbiato", "sono stressato", "mi sento male",
    "sono depresso", "ho paura", "sono ansioso", "piango",
    "mi manca", "soffro", "sono deluso", "mi sento inutile",
    "non ce la faccio", "sono esausto", "tutto mi pesa",
    "mi sento sopraffatto", "sono giù", "non sto bene",
    "ho il cuore pesante", "non so come andare avanti"
]

def _is_emotional(message: str) -> bool:
    msg_lower = message.lower()
    return any(kw in msg_lower for kw in EMOTIONAL_KEYWORDS)

WEATHER_EXPLICIT_KEYWORDS = [
    "meteo", "tempo", "pioggia", "sole", "temperatura", "gradi",
    "clima", "previsioni", "nuvoloso", "vento", "neve", "grandine"
]

BARE_PRONOUNS = {
    "dove", "dove?", "quale", "quale?", "quando", "quando?",
    "come", "come?", "cosa", "cosa?", "chi", "chi?", "quanto", "quanto?"
}

class IntentClassifier:
    """
    Classificatore intent - rule-based deterministico
    Engine: GPT-4o-mini per intent classification
    """
    
    def __init__(self):
        # Pattern memoria/ricordo - hanno priorità massima
        self.memory_patterns = [
            "ricordi", "ricordo", "ricordare", "ricordati",
            "memoria", "detto", "finora", "fin ora",
            "ti ho detto", "cosa sai di me", "ricordi di me",
            "cosa ti ricordi", "ti ricordi"
        ]
        
        # Pattern per chat libera (GPT-4o)
        self.chat_patterns = {
            "greeting": [
                "ciao", "salve", "hey", "buongiorno", "buonasera", "buon pomeriggio"
            ],
            "how_are_you": [
                "come stai", "come va", "tutto bene", "tutto ok"
            ],
            "identity": [
                "chi sei", "chi è", "tu chi sei", "presentati"
            ],
            "time": [
                "che ore sono", "che ora è", "che ora e'",
                "dimmi l'ora", "dimmi l'orario",
                "dimmi che ore sono", "sai che ore sono", "sai l'ora"
            ],
            "date": [
                "che giorno è oggi", "che giorno e' oggi",
                "che data è", "che data e'",
                "che data è oggi", "che data e' oggi",
                "oggi che giorno è", "oggi che giorno e'",
                "dimmi la data", "dimmi che giorno è", "dimmi che giorno e'"
            ],
            "news": [
                "notizie", "news", "cosa succede", "aggiornamenti",
                "ultime notizie", "cosa sta succedendo",
                "che notizie", "ultime news", "novita'", "novità"
            ],
            "weather": [
                "che tempo fa", "com'è il meteo", "previsioni meteo",
                "piove", "nevica", "fa caldo", "fa freddo"
            ],
            "help": [
                "aiuto", "help", "aiutami", "cosa sai fare"
            ],
            "goodbye": [
                "arrivederci", "addio", "a dopo", "ci vediamo"
            ]
        }
        
        # Pattern per GPT-4o (tecnica)
        self.gpt_patterns = {
            "reminder_create": [
                "ricordami", "ricordamelo", "segnami un promemoria", "promemoria", "appuntamento",
                "imposta promemoria", "crea promemoria", "nuovo promemoria", "memorizza promemoria",
                "metti in agenda", "segna in agenda", "nuovo appuntamento", "meeting", "riunione"
            ],
            "reminder_list": [
                "quali promemoria ho", "che appuntamenti ho", "lista promemoria",
                "i miei promemoria", "mostra promemoria", "elenco appuntamenti",
                "promemoria attivi", "appuntamenti impostati", "ricordami i promemoria",
                "appuntamenti ho", "quali appuntamenti", "cosa ho da fare", "miei impegni",
                "agenda di oggi", "agenda di domani", "cosa ho in agenda", "cosa devo fare",
                "cosa ho da fare oggi", "cosa ho da fare domani"
            ],
            "reminder_delete": [
                "cancella promemoria", "cancella tutti i promemoria", "elimina promemoria",
                "annulla promemoria", "cancella appuntamenti", "elimina appuntamenti",
                "rimuovi promemoria", "rimuovi tutti i promemoria"
            ],
            "reminder_update": [
                "modifica promemoria", "sposta promemoria", "cambia orario",
                "spostalo alle", "anticipa alle", "posticipa alle", "sposta a",
                "cambia a", "modifica orario", "cambia data", "sposta domani",
                "anticipa oggi", "posticipa domani", "sposta il promemoria"
            ],
            "tecnica": [
                "tecnica", "tecnico", "architettura", "sistema", "implementazione",
                "codice", "programmazione", "sviluppo", "software", "hardware",
                "algoritmo", "database", "api", "framework", "libreria",
                "script", "python", "javascript", "java", "c++", "rust", "html", "css"
            ],
            "debug": [
                "debug", "errore", "bug", "problema", "non funziona", "crash",
                "eccezione", "exception", "fix", "risolvere", "correggere"
            ],
            "spiegazione": [
                "spiega", "spiegazione", "come funziona", "perché", "come mai",
                "dettagli", "approfondire", "chiarire", "illustrare"
            ],
            "icloud_sync": [
                "sincronizza icloud", "aggiorna icloud", "scarica da icloud",
                "sincronizza promemoria", "importa promemoria"
            ],
            "calendar_sync_all": [
                "sincronizza i miei calendari", "sincronizza calendari", "integra calendari", 
                "collega calendari", "aggiorna tutto", "sincronizza tutto", "aggiorna calendari"
            ],
            "google_setup": [
                "collega google", "configura google", "imposta google", "accesso google",
                "connetti google", "login google", "account google", "attiva google", "usa google"
            ],
            "google_sync": [
                "sincronizza google", "aggiorna google", "scarica da google", "scarica google"
            ],
            "icloud_setup": [
                "collega icloud", "configura icloud", "imposta icloud", "password icloud",
                "accesso icloud", "account icloud", "attiva icloud", "usa icloud"
            ],
            "image_generation": [
                "genera un'immagine", "genera una immagine", "genera un immagine",
                "crea un'immagine", "crea una immagine",
                "disegna", "crea un'illustrazione", "genera una foto", "crea una foto",
                "illustra", "crea una picture", "genera grafica", "dipingi", "disegni",
                "genera immagine", "crea immagine", "genera foto",
            ]
        }
    
    def classify(self, message: str, user_id: str = None) -> str:
        """
        Classifica intent - logica MINIMA con priorità memoria e override per intent misti
        APPLICA REMINDER GUARD LAYER post-processing
        
        Args:
            message: Messaggio utente
            
        Returns:
            Intent classificato e normalizzato
        """
        message_lower = message.lower().strip()
        
        # 0️⃣ PRIORITA' MASSIMA: Cloud patterns (Robust)
        if "google" in message_lower:
            if any(kw in message_lower for kw in ["sincronizza", "aggiorna", "scarica"]):
                log("INTENT_CLASSIFIED", intent="google_sync", user_id=user_id, engine="regex_robust", message=message[:50])
                return "google_sync"
            if any(kw in message_lower for kw in ["collega", "configura", "imposta", "accesso", "login", "usa", "account", "user", "email"]):
                log("INTENT_CLASSIFIED", intent="google_setup", user_id=user_id, engine="regex_robust", message=message[:50])
                return "google_setup"
        
        if "icloud" in message_lower or "apple" in message_lower:
            if any(kw in message_lower for kw in ["sincronizza", "aggiorna", "importa", "scarica"]):
                log("INTENT_CLASSIFIED", intent="icloud_sync", user_id=user_id, engine="regex_robust", message=message[:50])
                return "icloud_sync"
            if any(kw in message_lower for kw in ["collega", "configura", "imposta", "accesso", "login", "usa", "account", "user", "email"]):
                log("INTENT_CLASSIFIED", intent="icloud_setup", user_id=user_id, engine="regex_robust", message=message[:50])
                return "icloud_setup"

        # 0.5️⃣ PRIORITA' ALTA: Cloud patterns (Exact)
        for intent in ["icloud_setup", "icloud_sync", "google_setup", "google_sync"]:
            keywords = self.gpt_patterns.get(intent, [])
            for keyword in keywords:
                if re.search(rf'\b{re.escape(keyword)}\b', message_lower):
                    log("INTENT_CLASSIFIED", intent=intent, user_id=user_id, engine="regex", message=message[:50])
                    return intent

        # 1️⃣ PRIORITA' ALTA: reminder patterns (tutti) + image generation
        for intent, keywords in self.gpt_patterns.items():
            if intent.startswith('reminder_') or intent == 'image_generation':
                if any(keyword in message_lower for keyword in keywords):
                    log("INTENT_CLASSIFIED", intent=intent, user_id=user_id, engine="regex", message=message[:50])
                    # APPLICA REMINDER GUARD LAYER solo per reminder intents
                    if intent.startswith('reminder_'):
                        normalized_intent = self.normalize_reminder_intent(message, intent)
                        return normalized_intent
                    return intent
        
        # 0.1️⃣ PRIORITA' ALTA: pattern memoria/ricordo
        if any(pattern in message_lower for pattern in self.memory_patterns):
            log("INTENT_CLASSIFIED", intent="chat_free", user_id=user_id, engine="gpt-4o", message=message[:50], override="memory_context")
            return "chat_free"
        
        # 0.5️⃣ PRIORITY OVERRIDES for mixed intents
        
        # Check for reminder keywords
        reminder_keywords = [
            "ricordami", "ricordamelo", "promemoria", "appuntamento", 
            "segnami un promemoria", "calendario", "agenda", "metti nel", "segna nel"
        ]
        if any(kw in message_lower for kw in reminder_keywords):
            log("INTENT_OVERRIDE_APPLIED", original="mixed", final="reminder_create", message=message[:50])
            # APPLICA REMINDER GUARD LAYER
            normalized_intent = self.normalize_reminder_intent(message, "reminder_create")
            return normalized_intent
        
        # Check for technical keywords
        technical_keywords = ["tecnica", "tecnico", "architettura", "sistema", "implementazione",
                            "codice", "programmazione", "sviluppo", "software", "hardware",
                            "algoritmo", "database", "api", "framework", "libreria",
                            "debug", "errore", "bug", "problema", "non funziona", "crash",
                            "eccezione", "exception", "fix", "risolvere", "correggere",
                            "spiega", "spiegazione", "come funziona", "perché", "come mai",
                            "dettagli", "approfondire", "chiarire", "illustrare"]
        if any(kw in message_lower for kw in technical_keywords):
            log("INTENT_OVERRIDE_APPLIED", original="mixed", final="tecnica", message=message[:50])
            return "tecnica"
        
        # 2️⃣ Altri pattern tecnici (GPT-4o)
        for intent, keywords in self.gpt_patterns.items():
            if intent.startswith('icloud_'): continue # Già gestiti sopra
            if any(keyword in message_lower for keyword in keywords):
                log("INTENT_CLASSIFIED", intent=intent, user_id=user_id, engine="regex", message=message[:50])
                # APPLICA REMINDER GUARD LAYER solo per reminder intents (anche se qui non dovrebbero essercene rimasti)
                if intent.startswith('reminder_'):
                    normalized_intent = self.normalize_reminder_intent(message, intent)
                    return normalized_intent
                return intent
        
        # 2️⃣ Pattern chat (GPT-4o)
        for intent, keywords in self.chat_patterns.items():
            if any(keyword in message_lower for keyword in keywords):
                log("INTENT_CLASSIFIED", intent=intent, user_id=user_id, engine="gpt-4o", message=message[:50])
                logger.info("INTENT_ENGINE=gpt-4o-mini intent=%s", intent)
                return intent
        
        # 2.5️⃣ Emotional check - prima di default chat_free
        if any(keyword in message_lower for keyword in EMOTIONAL_KEYWORDS):
            log("INTENT_OVERRIDE_APPLIED", original="chat_free", final="emotional", message=message[:50])
            return "emotional"
        
        # 3️⃣ Default: chat libera (GPT-4o) con normalizzazione finale
        intent = "chat_free"
        normalized_intent = self.normalize_reminder_intent(message, intent)
        
        if normalized_intent != intent:
             log("INTENT_GUARD_RECOVERY", original=intent, final=normalized_intent, message=message[:50])
             return normalized_intent

        log("INTENT_DEFAULT", intent="chat_free", user_id=user_id, engine="gpt-4o", message=message[:50])
        logger.info("INTENT_ENGINE=gpt-4o-mini intent=chat_free")
        return "chat_free"
    
    def get_engine_for_intent(self, intent: str) -> str:
        """
        Ritorna il motore per un intent
        
        Args:
            intent: Intent classificato
            
        Returns:
            Engine: "gpt-4o" o "gpt-4o-mini"
        """
        if intent in self.gpt_patterns:
            return "gpt-4o"
        else:
            return "gpt-4o"
    
    def _is_implicit_weather(self, message_lower: str) -> bool:
        """
        Detect implicit weather requests without explicit weather keywords.
        Patterns like "a Roma oggi?", "temperatura Roma", "situazione meteo Napoli"
        """
        import re
        
        # Weather-related words
        weather_words = ["meteo", "temperatura", "clima", "vento", "umidità", "situazione", "aria"]
        
        # Check for weather words + city pattern
        for wword in weather_words:
            if wword in message_lower:
                # Look for city name after weather word
                pattern = rf"{wword}\s+(?:a|di|in|su|per)?\s*([a-zà-ú]{2,})"
                m = re.search(pattern, message_lower)
                if m:
                    city = m.group(1)
                    # Skip common non-city words
                    if city not in ["oggi", "domani", "ieri", "ora", "qui", "li", "la"]:
                        return True
                # Also check if city is before weather word
                pattern = rf"([a-zà-ú]{2,})\s+(?:a|di|in|su|per)?\s*{wword}"
                m = re.search(pattern, message_lower)
                if m:
                    city = m.group(1)
                    if city not in ["oggi", "domani", "ieri", "ora", "qui", "li", "la"]:
                        return True
        
        # Check for "a {city}" pattern with context words
        context_words = ["fa", "è", "c'è", "quanto", "come", "stato"]
        for cword in context_words:
            if cword in message_lower:
                # Look for "a {city}" pattern
                pattern = rf"a\s+([a-zà-ú]{2,})"
                matches = re.findall(pattern, message_lower)
                for city in matches:
                    # Skip common non-city words
                    if city not in ["oggi", "domani", "ieri", "ora", "qui", "li", "la", "casa", "lavoro"]:
                        return True
        
        # Check for standalone city names with weather context
        # "Roma oggi?", "Milano come sta"
        words = message_lower.split()
        for i, word in enumerate(words):
            # Check if word could be a city (starts with capital in original)
            # For lowercase input, check if it's followed by weather context
            if len(word) >= 3 and word not in ["che", "come", "quando", "dove", "cosa"]:
                # Check if followed by weather context
                if i < len(words) - 1:
                    next_word = words[i + 1]
                    if next_word in ["oggi", "domani", "ieri", "ora", "fa", "è", "c'è", "stato"]:
                        return True
                    # Check if preceded by weather words
                    if i > 0:
                        prev_word = words[i - 1]
                        if prev_word in ["temperatura", "meteo", "clima", "vento", "umidità", "situazione", "aria"]:
                            return True
        
        return False
    
    def _should_block_weather_override(self, message_lower: str) -> bool:
        """
        Blocca override weather per messaggi brevi contestuali.
        Returns True se l'override deve essere bloccato.
        """
        words = message_lower.strip().split()
        
        # Messaggi molto corti (1-3 parole) senza keyword esplicite → NON overridare
        if len(words) <= 3:
            WEATHER_KEYWORDS = ["meteo", "tempo", "pioggia", "sole", "temperatura", 
                               "gradi", "clima", "previsioni", "nuvoloso", "vento", "umidità", "temporale"]
            has_weather_keyword = any(kw in message_lower for kw in WEATHER_KEYWORDS)
            if not has_weather_keyword:
                return True  # Blocca override
        
        # Pronomi interrogativi isolati → mai weather
        bare_pronouns = {"dove", "dove?", "quale", "quale?", "quando", "quando?", 
                        "come", "come?", "cosa", "cosa?", "chi", "chi?"}
        if message_lower.strip() in bare_pronouns:
            return True  # Blocca override
        
        return False  # Non bloccare - comportamento originale

    def _is_followup_weather(self, message_lower: str) -> bool:
        """
        Detect follow-up weather requests after previous weather intent.
        Patterns: "A Firenze?", "Milano?", "E Bologna?"
        """
        import re
        
        # Pattern per follow-up weather
        followup_patterns = [
            r'^a\s+([a-zà-ú]{2,})\?$',  # "A Firenze?"
            r'^([a-zà-ú]{2,})\?$',      # "Milano?"
            r'^e\s+([a-zà-ú]{2,})\?$',  # "E Bologna?"
        ]
        
        for pattern in followup_patterns:
            if re.match(pattern, message_lower):
                city = re.search(r'([a-zà-ú]{2,})', message_lower)
                if city:
                    city_name = city.group(1)
                    # Skip common non-city words
                    if city_name not in ["oggi", "domani", "ieri", "ora", "qui", "li", "la", "casa", "lavoro", "stato", "tempo", "meteo"]:
                        return True
        
        return False

    def normalize_reminder_intent(self, message: str, intent: str) -> str:
        """
        REMINDER GUARD LAYER - Post-processing deterministico per reminder intents.
        Intercetta e corregge classificazioni errate basandosi su parole chiave specifiche.
        
        Args:
            message: Messaggio utente originale
            intent: Intent classificato dal sistema
            
        Returns:
            Intent normalizzato (reminder_*, chat_free, o intent originale)
        """
        message_lower = message.lower().strip()
        
        # 0️⃣ Parole chiave iCloud → forza icloud_sync / icloud_setup
        if any(kw in message_lower for kw in ["icloud", "apple"]):
            if any(kw in message_lower for kw in ["sincronizza", "aggiorna", "importa", "scarica"]):
                return "icloud_sync"
            if any(kw in message_lower for kw in ["collega", "configura", "imposta", "accesso", "login", "usa", "account", "user", "email"]):
                return "icloud_setup"
        
        if "google" in message_lower:
            if any(kw in message_lower for kw in ["sincronizza", "aggiorna", "scarica"]):
                return "google_sync"
            if any(kw in message_lower for kw in ["collega", "configura", "imposta", "accesso", "login", "usa", "account", "user", "email"]):
                return "google_setup"
                
        forced_intent = False
        
        # 1️⃣ Parole chiave CANCELLAZIONE → forza reminder_delete
        delete_keywords = ["cancella", "elimina", "rimuovi", "annulla"]
        if any(keyword in message_lower for keyword in delete_keywords):
            if "promemoria" in message_lower or "appuntament" in message_lower:
                log("REMINDER_GUARD_FORCED", original_intent=intent, forced_intent="reminder_delete", reason="delete_keyword", message=message[:50])
                return "reminder_delete"
        
        # 2️⃣ Parole chiave LISTA → forza reminder_list  
        list_keywords = [
            "quali", "mostra", "lista", "che appuntamenti", "che promemoria", "i miei", 
            "elenco", "appuntamenti ho", "cosa mi devi ricordare", "cosa devi ricordarmi", 
            "cosa devo fare", "dimmi i promemoria", "elenca i promemoria", "che promemoria ho",
            "impegni", "agenda", "cosa ho oggi", "cosa ho domani", "programmi"
        ]
        if any(keyword in message_lower for keyword in list_keywords):
            if any(kw in message_lower for kw in ["promemoria", "appuntament", "impegn", "agenda"]):
                log("REMINDER_GUARD_FORCED", original_intent=intent, forced_intent="reminder_list", reason="list_keyword", message=message[:50])
                return "reminder_list"
        
        # 3️⃣ Parole chiave MODIFICA → forza reminder_update
        update_keywords = ["modifica", "sposta", "cambia", "posticipa", "anticipa"]
        if any(keyword in message_lower for keyword in update_keywords):
            if "promemoria" in message_lower or "appuntament" in message_lower:
                log("REMINDER_GUARD_FORCED", original_intent=intent, forced_intent="reminder_update", reason="update_keyword", message=message[:50])
                return "reminder_update"
        
        # 4️⃣ Se intent == reminder_create → verifica presenza data/orario
        if intent == "reminder_create":
            has_datetime = self._has_datetime_reference(message_lower)
            
            if not has_datetime:
                # NON fare downgrade a chat_free, lasciare passare reminder_create
                # Il proactor gestirà il caso chiedendo data/orario
                log("REMINDER_GUARD_NO_DATETIME", intent=intent, has_datetime=False, message=message[:50])
                return intent
            else:
                log("REMINDER_GUARD_VALIDATED", intent=intent, has_datetime=True, message=message[:50])
        
        # 5️⃣ Altri casi ambigui con parole reminder ma azione non chiara
        reminder_keywords = [
            "ricordami", "ricordamelo", "promemoria", "appuntamento", 
            "segnami un promemoria", "calendario", "agenda", "metti nel", "segna nel"
        ]
        if any(keyword in message_lower for keyword in reminder_keywords):
            # Forza reminder_create se c'è una data/ora
            if self._has_datetime_reference(message_lower):
                log("REMINDER_GUARD_FORCED", original_intent=intent, forced_intent="reminder_create", reason="reminder_keyword_with_dt", message=message[:50])
                return "reminder_create"
            
            # Se contiene reminder keywords ma non è stato classificato come reminder_*
            # e non ha data/orario chiara → downgrade a chat_free
            # MA solo se non è già un intent tecnico o esplicito (weather, news, tecnica, etc.)
            if not intent.startswith('reminder_') and not self._has_datetime_reference(message_lower):
                protected_intents = ["weather", "news", "tecnica", "debug", "spiegazione", "icloud_sync", "google_sync", "identity"]
                if intent in protected_intents:
                    return intent
                
                log("REMINDER_GUARD_AMBIGUOUS", original_intent=intent, final_intent="chat_free", reason="ambiguous_reminder", message=message[:50])
                return "chat_free"
        
        return intent
    
    def _has_datetime_reference(self, message_lower: str) -> bool:
        """
        Verifica presenza di riferimenti a data/orario nel messaggio.
        Pattern: HH:MM, domani, oggi, dopodomani, giorni settimana.
        
        Args:
            message_lower: Messaggio in minuscolo
            
        Returns:
            True se presente riferimento temporale
        """
        import re
        
        # Pattern orario HH:MM
        if re.search(r'\b\d{1,2}:\d{2}\b', message_lower):
            return True
        
        # Pattern "alle H" (senza minuti)
        if re.search(r'\balle\s+\d{1,2}\b', message_lower):
            return True
        
        # Parole chiave data
        date_keywords = ["domani", "oggi", "dopodomani", "ieri", "stasera", "pomeriggio", "mattina"]
        if any(keyword in message_lower for keyword in date_keywords):
            return True
        
        # Giorni della settimana
        weekdays = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica", "lunedi", "martedi", "mercoledi", "giovedi", "venerdi"]
        if any(day in message_lower for day in weekdays):
            return True
            
        # Pattern relativo "tra X minuti/ore"
        if re.search(r'\b(tra|fra|entro)\s+(\d+|un|una|uno|due|tre)\s+(minut|or|second|giorn|settiman)\b', message_lower):
            return True
        
        return False
    
    def _should_override_to_weather(self, message: str) -> bool:
        msg_lower = message.lower().strip()
        words = msg_lower.split()
        
        # Pronomi isolati → mai weather
        if msg_lower in BARE_PRONOUNS:
            return False
        
        # Messaggi corti senza keyword esplicite → non overridare
        if len(words) <= 3:
            if not any(kw in msg_lower for kw in WEATHER_EXPLICIT_KEYWORDS):
                return False
        
        return True

    async def classify_async(self, message: str, user_id: str = None) -> str:
        """
        Classificazione tramite LLM con valutazione score e contesto.
        Sostituisce le keyword statiche come logica primaria.
        """
        message_lower = (message or "").lower().strip()

        # PRIORITÀ ASSOLUTA: image generation deterministico (evita false chat_free dal classificatore LLM)
        image_keywords = self.gpt_patterns.get("image_generation", [])
        if any(keyword in message_lower for keyword in image_keywords):
            log("INTENT_CLASSIFIED", intent="image_generation", user_id=user_id, engine="regex_priority", message=message[:50])
            return ["image_generation"]

        # PRIORITÀ ALTA: dove_sono — "dove sono", "dove mi trovo", ecc.
        _location_self_kw = [
            "dove sono", "dove mi trovo", "dove siamo",
            "in che zona sono", "in che posto sono",
            "la mia posizione", "dove sono adesso",
        ]
        if any(kw in message_lower for kw in _location_self_kw):
            log("INTENT_CLASSIFIED", intent="dove_sono", user_id=user_id, engine="regex_priority", message=message[:50])
            return ["dove_sono"]

        # PRIORITÀ ALTA: memory_correction — patterns inequivocabili di correzione profilo
        _correction_kw = [
            "non mi chiamo", "hai sbagliato il mio nome", "correggiti",
            "dimentica che", "aggiorna il mio", "cambia quello che sai",
            "in realtà mi chiamo", "in realtà sono", "non vivo a",
            "non lavoro come", "non ho figli", "non ho un cane", "non ho una gatta",
            "il mio nome non è", "la mia città non è", "la mia professione non è",
            # Correzioni professione ("hai sbagliato, non sono un ingegnere")
            "hai sbagliato",
            "non sono un ", "non sono una ",
            # Varianti "in realtà"
            "in realtà vivo", "in realtà lavoro", "in realtà ho",
            # Cambiamenti di stato
            "non lavoro più", "non abito più", "non vivo più a",
            "non sono più", "non ho più",
            # Negazioni partner/famiglia
            "non sono sposato", "non sono sposata", "non ho animali",
        ]
        if any(kw in message_lower for kw in _correction_kw):
            log("INTENT_CLASSIFIED", intent="memory_correction", user_id=user_id, engine="regex_priority", message=message[:50])
            return ["memory_correction"]

        from core.chat_memory import chat_memory
        from core.llm_service import llm_service
        import json
        import re

        # Raccogli ultimi messaggi per il contesto
        history = chat_memory.get_messages(user_id, limit=5) if user_id else []
        history_text = "\n".join([f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in history])
        
        system_prompt = """Sei un classificatore di intent. Analizza l'ultimo messaggio dell'utente considerando il contesto recente.
Valuta il parametro "score" tra 0.0 e 1.0 (dove 1.0 è certezza assoluta).

INTENT POSSIBILI:
- weather: richieste sul meteo o temperatura
- news: richieste di notizie o aggiornamenti
- time: richieste sull'ora
- date: richieste sulla data
- reminder_create: creare un promemoria (es: "ricordami di", "segna un impegno")
- reminder_list: elenco promemoria, appuntamenti o impegni (es: "i miei impegni", "cosa ho da fare")
- reminder_delete: cancellare promemoria
- reminder_update: modificare promemoria
- tecnica: questioni tecniche, programmazione, architettura
- debug: errori codice, malfunzionamenti software
- spiegazione: richiesta di spiegazione "perchè", "come mai", o correzione/frustrazione (es: "perchè non hai risposto?", "hai sbagliato")
- identity: chi sono io, che lavoro faccio, i miei account, i miei dati, ho figli?, sono sposato?, ho animali? (domande su sé stessi)
- memory_correction: l'utente AFFERMA ESPLICITAMENTE che un dato è sbagliato o da aggiornare (nome, città, professione, figli, animali, partner). NON usare per semplici domande come "ho figli?", "sono sposato?", "ho un cane?" — quelle sono "identity"
- dove_sono: l'utente chiede dove si trova o la sua posizione attuale
- icloud_setup: collegare o impostare account iCloud
- icloud_sync: sincronizzare dati da iCloud
- google_setup: collegare Google Calendar
- google_sync: sincronizzare appuntamenti da Google
- emotional: stato d'animo utente
- memory_context: riferimento ESPLICITO a messaggi passati (es: "cosa ho detto prima?")
- chat_free: salutare, ringraziare, generico

Devi restituire esclusivamente un payload JSON valido in questa forma:
{"intents": ["scelta1", "scelta2"], "score": 0.95}

REGOLE SPECIALI:
- Se l'utente chiede "impegni", "agenda" o "programma", usa SEMPRE "reminder_list".
- Se l'utente chiede "perchè" su un comportamento passato o manifesta insoddisfazione, usa "spiegazione".
- Se il messaggio contiene "cosa pensi", "cosa ne pensi", "ti piace", "ti sembra", "sei d'accordo" riguardo al meteo/temperatura/freddo/caldo, usa "relational" o "chat_free" — NON "weather".
- Se l'intenzione non è chiara, usa uno score basso.
"""

        user_prompt = f"Contesto recente della chat:\n{history_text}\n\nUltimo messaggio utente:\n{message}"
        
        try:
            response = await llm_service._call_with_protection(
                model="gpt-4o-mini",
                prompt=system_prompt,
                message=user_prompt,
                user_id=user_id or "system",
                route="classification"
            )
            
            if response:
                json_match = re.search(r'\{.*\}', response, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group(0))
                    intents = data.get("intents", [])
                    if not intents and "intent" in data:
                        intents = [data["intent"]]
                    
                    if not intents:
                        intents = ["chat_free"]

                    score = float(data.get("score", 0.0))
                    
                    # LOGGING
                    log("LLM_INTENT_CLASSIFICATION", intents=intents, score=score, message=message[:50], user_id=user_id)
                    logger.info(f"LLM_INTENT_CLASSIFICATION intents={intents} score={score}")
                    
                    # Se lo score < 0.8 per intent che azionano tool/api specifiche, ferma e chiedi chiarimenti
                    # (Solo se c'è un solo intent critico)
                    tool_intents = [
                        "weather", "news", "time", "date", 
                        "reminder_create", "reminder_delete", "reminder_update", "reminder_list"
                    ]
                    if len(intents) == 1 and score < 0.8 and intents[0] in tool_intents:
                        if intents[0] == "weather":
                            return ["ambiguous_weather"]
                        return ["ambiguous_tool"]
                    
                    # Normalize all intents
                    normalized = []
                    for i in intents:
                        norm = self.normalize_reminder_intent(message, i)
                        if norm not in normalized:
                            normalized.append(norm)
                    return normalized
        except Exception as e:
            logger.error(f"Errore nella classificazione JSON LLM: {str(e)}")
            
        # Fallback alla vecchia regex classification se LLM fallisce
        return [self.classify(message, user_id)]


# Istanza globale
intent_classifier = IntentClassifier()
