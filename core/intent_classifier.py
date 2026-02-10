"""
INTENT CLASSIFIER - Genesi Core v2
1 intent → 1 funzione
Classificazione rule-based semplice, nessun LLM
"""

from typing import Dict, Optional
from core.log import log

class IntentClassifier:
    """
    Classificatore intent - rule-based deterministico
    Nessun LLM, nessuna ambiguità
    """
    
    def __init__(self):
        # Pattern diretti senza complessità
        self.patterns = {
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
    
    def classify(self, message: str) -> str:
        """
        Classifica intent - 1 pattern → 1 intent
        
        Args:
            message: Messaggio utente
            
        Returns:
            Intent classificato
        """
        message_lower = message.lower().strip()
        
        # Check patterns in ordine di priorità
        for intent, keywords in self.patterns.items():
            if any(keyword in message_lower for keyword in keywords):
                log("INTENT_CLASSIFIED", intent=intent, message=message[:50])
                return intent
        
        # Default: chat libera
        log("INTENT_DEFAULT", intent="chat_free", message=message[:50])
        return "chat_free"

# Istanza globale
intent_classifier = IntentClassifier()
