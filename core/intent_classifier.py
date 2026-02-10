"""
INTENT CLASSIFIER - Genesi Core v2
Architettura separata: Chat libera vs Tecnica
1 intent → 1 funzione con Proactor
"""

from typing import Dict, Optional
from core.log import log

class IntentClassifier:
    """
    Classificatore intent - rule-based deterministico
    Separazione chiara: Qwen vs GPT
    """
    
    def __init__(self):
        # Pattern per Qwen2.5-7B-Instruct (chat libera)
        self.qwen_patterns = {
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
                "che ore sono", "che ora è", "orario", "ora"
            ],
            "date": [
                "che giorno è", "giorno", "data", "oggi che giorno è"
            ],
            "weather": [
                "tempo", "meteo", "piove", "sole", "nuvole"
            ],
            "help": [
                "aiuto", "help", "aiutami", "cosa sai fare"
            ],
            "goodbye": [
                "arrivederci", "ciao", "addio", "a dopo"
            ]
        }
        
        # Pattern per GPT (tecnica)
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
        Classifica intent - logica MINIMA
        
        Args:
            message: Messaggio utente
            
        Returns:
            Intent classificato
        """
        message_lower = message.lower().strip()
        
        # Prima controlla pattern tecnici (GPT)
        for intent, keywords in self.gpt_patterns.items():
            if any(keyword in message_lower for keyword in keywords):
                log("INTENT_CLASSIFIED", intent=intent, engine="GPT", message=message[:50])
                return intent
        
        # Poi controlla pattern chat (Qwen)
        for intent, keywords in self.qwen_patterns.items():
            if any(keyword in message_lower for keyword in keywords):
                log("INTENT_CLASSIFIED", intent=intent, engine="QWEN", message=message[:50])
                return intent
        
        # Default: chat libera (Qwen)
        log("INTENT_DEFAULT", intent="chat_free", engine="QWEN", message=message[:50])
        return "chat_free"
    
    def get_engine_for_intent(self, intent: str) -> str:
        """
        Ritorna il motore per un intent
        
        Args:
            intent: Intent classificato
            
        Returns:
            Engine: "QWEN" o "GPT"
        """
        if intent in self.gpt_patterns:
            return "GPT"
        else:
            return "QWEN"

# Istanza globale
intent_classifier = IntentClassifier()
