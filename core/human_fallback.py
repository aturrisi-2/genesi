"""
HUMAN FALLBACK HANDLER
Gestisce fallback umani per tool failure e errori tecnici
"""

from typing import Dict, Optional
import random

class HumanFallback:
    """
    FALLBACK UMANI PER TOOL FAILURE
    Nasconde errori tecnici e risponde in modo umano
    """
    
    def __init__(self):
        self.fallbacks = {
            "weather": [
                "Al momento non riesco a recuperare il meteo, ma posso aiutarti in altro modo.",
                "Non riesco a ottenere informazioni meteo in questo momento. Posso aiutarti con qualcos'altro?",
                "Il servizio meteo non è disponibile ora. C'è altro che posso fare per te?"
            ],
            
            "news": [
                "Al momento non riesco a recuperare le notizie, ma posso aiutarti in altro modo.",
                "Non riesco a ottenere notizie in questo momento. Posso aiutarti con qualcos'altro?",
                "Il servizio notizie non è disponibile ora. C'è altro che posso fare per te?"
            ],
            
            "memory": [
                "Mi dispiace, non riesco a ricordare questa informazione ora.",
                "Non ho accesso a questa informazione in questo momento.",
                "Mi dispiace, non posso recuperare questo ricordo al momento."
            ],
            
            "identity": [
                "Mi dispiace, non ricordo il tuo nome in questo momento.",
                "Non riesco a ricordare come ti chiami ora, ma sono qui per parlare con te.",
                "Mi dispiace, la memoria non è disponibile, ma possiamo comunque conversare."
            ],
            
            "general": [
                "Mi dispiace, non riesco a completare questa richiesta in questo momento.",
                "Qualcosa non ha funzionato come previsto. Possiamo riprovare o fare altro?",
                "Mi dispiace, non posso aiutarti con questo specificamente ora."
            ]
        }
    
    def get_fallback(self, context: str, user_query: str = "") -> str:
        """
        OTTIENE FALLBACK UMANO CONTESTUALE
        
        Args:
            context: Tipo di fallback (weather, news, memory, etc.)
            user_query: Query originale utente per personalizzazione
            
        Returns:
            Risposta umana, non tecnica
        """
        fallback_list = self.fallbacks.get(context, self.fallbacks["general"])
        
        # Seleziona fallback casualmente
        selected = random.choice(fallback_list)
        
        # Personalizzazione leggera basata sulla query
        if user_query and "roma" in user_query.lower():
            if context == "weather":
                selected = "Non riesco a ottenere il meteo di Roma ora. Posso aiutarti con altro?"
            elif context == "news":
                selected = "Non riesco a ottenere notizie su Roma ora. Posso aiutarti con altro?"
        
        return selected
    
    def is_tool_error(self, error_response: str) -> bool:
        """
        VERIFICA SE È UN ERRORE TECNICO
        
        Args:
            error_response: Risposta da un tool
            
        Returns:
            True se è un errore tecnico
        """
        technical_error_patterns = [
            "qualcosa non ha funzionato",
            "riprova tra poco",
            "errore",
            "error",
            "failed",
            "timeout",
            "connection",
            "api key",
            "not available",
            "non disponibile"
        ]
        
        error_lower = error_response.lower()
        return any(pattern in error_lower for pattern in technical_error_patterns)
    
    def handle_tool_failure(self, tool_type: str, error: str, user_query: str = "") -> str:
        """
        GESTISCE FALLBACK TOOL
        
        Args:
            tool_type: Tipo di tool (weather, news, etc.)
            error: Errore originale
            user_query: Query utente
            
        Returns:
            Fallback umano
        """
        print(f"[HUMAN_FALLBACK] Tool {tool_type} failed: {error}")
        
        # Nascondi completamente l'errore tecnico
        return self.get_fallback(tool_type, user_query)

# Istanza globale
human_fallback = HumanFallback()
