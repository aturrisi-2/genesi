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
            "tecnica": [
                "tecnica", "tecnico", "architettura", "sistema", "implementazione",
                "codice", "programmazione", "sviluppo", "software", "hardware",
                "algoritmo", "database", "api", "framework", "libreria"
            ],
            "debug": [
                "debug", "errore", "bug", "problema", "non funziona", "crash",
                "eccezione", "exception", "fix", "risolvere", "correggere"
            ],
            "spiegazione": [
                "spiega", "spiegazione", "come funziona", "perché", "come mai",
                "dettagli", "approfondire", "chiarire", "illustrare"
            ]
        }
    
    def classify(self, message: str) -> str:
        """
        Classifica intent - logica MINIMA con priorità memoria e override per intent misti
        
        Args:
            message: Messaggio utente
            
        Returns:
            Intent classificato
        """
        message_lower = message.lower().strip()
        
        # 0️⃣ PRIORITA' MASSIMA: pattern memoria/ricordo
        if any(pattern in message_lower for pattern in self.memory_patterns):
            log("INTENT_CLASSIFIED", intent="chat_free", engine="gpt-4o", message=message[:50], override="memory_context")
            return "chat_free"
        
        # 0.5️⃣ PRIORITY OVERRIDES for mixed intents
        # Check for weather keywords (highest priority after memory)
        weather_keywords = ["tempo", "meteo", "piove", "nevica", "caldo", "freddo", "sole", "nuvolo"]
        if any(kw in message_lower for kw in weather_keywords):
            log("INTENT_OVERRIDE_APPLIED", original="mixed", final="weather", message=message[:50])
            return "weather"
        
        # Check for implicit weather patterns
        if self._is_implicit_weather(message_lower):
            log("INTENT_OVERRIDE_APPLIED", original="mixed", final="weather", message=message[:50])
            return "weather"
        
        # Check for reminder keywords
        reminder_keywords = ["ricorda", "ricordami", "promemoria", "appuntamento", "ricordare"]
        if any(kw in message_lower for kw in reminder_keywords):
            log("INTENT_OVERRIDE_APPLIED", original="mixed", final="reminder_create", message=message[:50])
            return "reminder_create"
        
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
        
        # 1️⃣ Pattern tecnici (GPT-4o)
        for intent, keywords in self.gpt_patterns.items():
            if any(keyword in message_lower for keyword in keywords):
                log("INTENT_CLASSIFIED", intent=intent, engine="gpt-4o", message=message[:50])
                logger.info("INTENT_ENGINE=gpt-4o-mini intent=%s", intent)
                return intent
        
        # 2️⃣ Pattern chat (GPT-4o)
        for intent, keywords in self.chat_patterns.items():
            if any(keyword in message_lower for keyword in keywords):
                log("INTENT_CLASSIFIED", intent=intent, engine="gpt-4o", message=message[:50])
                logger.info("INTENT_ENGINE=gpt-4o-mini intent=%s", intent)
                return intent
        
        # 3️⃣ Default: chat libera (GPT-4o)
        log("INTENT_DEFAULT", intent="chat_free", engine="gpt-4o", message=message[:50])
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

# Istanza globale
intent_classifier = IntentClassifier()
