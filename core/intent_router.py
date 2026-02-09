"""
INTENT ROUTER DETERMINISTICO
Classificazione rule-based per routing delle risposte
Blocca LLM creativo per domande mediche, storiche e fattuali
"""

import re
from typing import Dict, Optional, List
from enum import Enum

class IntentType(Enum):
    CHAT_FREE = "chat_free"
    MEDICAL_INFO = "medical_info"
    HISTORICAL_INFO = "historical_info"
    WEATHER = "weather"
    NEWS = "news"
    EMOTIONAL_SUPPORT = "emotional_support"
    OTHER = "other"

class IntentRouter:
    """
    ROUTING DETERMINISTICO BASATO SU KEYWORD
    Classifica messaggi utente senza usare LLM
    """
    
    def __init__(self):
        # Keyword patterns per ogni categoria
        self.patterns = {
            IntentType.MEDICAL_INFO: [
                # Sintomi comuni
                r"mal di testa", r"mal di pancia", r"mal di schiena", r"mal di gola",
                r"dolore", r"dolor", r"fa male", r"mi fa male",
                # Condizioni mediche
                r"febbre", r"temperatura", r"tosse", r"raffreddore", r"influenza",
                r"pressione", r"diabete", r"allergia", r"asma",
                # Farmaci e trattamenti
                r"farmaco", r"medicina", r"cura", r"terapia", r"trattamento",
                # Parti del corpo
                r"testa", r"pancia", r"schiena", r"gola", r"cuore", r"stomaco",
                # Generali
                r"medico", r"medica", r"ospedale", r"pronto soccorso", r"diagnosi"
            ],
            
            IntentType.HISTORICAL_INFO: [
                # Pattern storici
                r"chi era", r"chi furono", r"chi è stato", r"chi sono stati",
                r"quando nacque", r"quando morì", r"quando visse",
                r"storia di", r"storia del", r"epoca di", r"periodo di",
                # Eventi storici
                r"guerra", r"rivoluzione", r"battaglia", r"impero", r"regno",
                r"medioevo", r"rinascimento", r"illuminismo", r"rivoluzione industriale",
                # Domande su persone storiche
                r"napoleone", r"giulio cesare", r"leonardo da vinci", r"michelangelo",
                r"dante", r"petrarca", r"galileo", r"newton", r"einstein"
            ],
            
            IntentType.WEATHER: [
                # Meteo
                r"tempo fa", r"che tempo", r"meteo", r"previsioni", r"previsione",
                r"piove", r"pioverà", r"nevica", r"nevicherà", r"torna", r"tornerà",
                r"temperatura", r"gradi", r"freddo", r"caldo", r"umido", r"umidità",
                # Luoghi
                r"a [a-z]+ fa", r"meteo [a-z]+", r"tempo [a-z]+"
            ],
            
            IntentType.NEWS: [
                # Notizie
                r"notizie", r"notizia", r"news", r"attualità", r"successo oggi",
                r"cosa è successo", r"è successo", r"ultime notizie", r"giornale"
            ],
            
            IntentType.EMOTIONAL_SUPPORT: [
                # Supporto emotivo
                r"sono triste", r"sono felice", r"sono arrabbiato", r"sono preoccupato",
                r"mi sento", r"sentimento", r"emozione", r"ansia", r"stress",
                r"depressione", r"tristezza", r"felicità", r"rabbia", r"paura",
                r"aiutami", r"aiuto", r"consiglio", r"parlare con"
            ]
        }
    
    def classify_intent(self, message: str) -> IntentType:
        """
        CLASSIFICA INTENT IN MODO DETERMINISTICO
        Rule-based + keyword-based, SENZA LLM
        
        Args:
            message: Messaggio utente
            
        Returns:
            IntentType classificato
        """
        if not message or not isinstance(message, str):
            return IntentType.OTHER
        
        message_lower = message.lower().strip()
        
        # 1. Check per ogni categoria in ordine di priorità
        for intent_type, patterns in self.patterns.items():
            for pattern in patterns:
                if re.search(pattern, message_lower, re.IGNORECASE):
                    return intent_type
        
        # 2. Default: chat libera
        return IntentType.CHAT_FREE
    
    def route_to_source(self, intent_type: IntentType) -> Dict:
        """
        DEFINISCE LA FONTE DATI PER OGNI INTENT
        
        Args:
            intent_type: Intent classificato
            
        Returns:
            Dict con routing info
        """
        routing_map = {
            IntentType.CHAT_FREE: {
                "source": "personalplex",
                "llm_creative": True,
                "verified_data": False,
                "tone": "natural"
            },
            
            IntentType.EMOTIONAL_SUPPORT: {
                "source": "psychological_branch",
                "llm_creative": False,
                "verified_data": False,
                "tone": "empathetic"
            },
            
            IntentType.MEDICAL_INFO: {
                "source": "verified_knowledge",
                "llm_creative": False,
                "verified_data": True,
                "tone": "cautious_medical",
                "disclaimer": "Non sono un medico. Per problemi di salute consulta un professionista."
            },
            
            IntentType.HISTORICAL_INFO: {
                "source": "verified_knowledge",
                "llm_creative": False,
                "verified_data": True,
                "tone": "educational"
            },
            
            IntentType.WEATHER: {
                "source": "weather_api",
                "llm_creative": False,
                "verified_data": True,
                "tone": "informative"
            },
            
            IntentType.NEWS: {
                "source": "news_api",
                "llm_creative": False,
                "verified_data": True,
                "tone": "informative"
            },
            
            IntentType.OTHER: {
                "source": "fallback",
                "llm_creative": True,
                "verified_data": False,
                "tone": "neutral"
            }
        }
        
        return routing_map.get(intent_type, routing_map[IntentType.OTHER])
    
    def should_block_creative_llm(self, intent_type: IntentType) -> bool:
        """
        DETERMINA SE BLOCCARE LLM CREATIVO
        
        Args:
            intent_type: Intent classificato
            
        Returns:
            True se deve bloccare LLM creativo
        """
        blocked_intents = {
            IntentType.MEDICAL_INFO,
            IntentType.HISTORICAL_INFO,
            IntentType.WEATHER,
            IntentType.NEWS
        }
        
        return intent_type in blocked_intents
    
    def get_routing_info(self, message: str) -> Dict:
        """
        ROUTING COMPLETO PER UN MESSAGGIO
        
        Args:
            message: Messaggio utente
            
        Returns:
            Dict con routing completo
        """
        intent_type = self.classify_intent(message)
        routing = self.route_to_source(intent_type)
        
        return {
            "intent": intent_type.value,
            "source": routing["source"],
            "block_creative_llm": self.should_block_creative_llm(intent_type),
            "verified_data": routing["verified_data"],
            "tone": routing["tone"],
            "disclaimer": routing.get("disclaimer"),
            "routing_applied": True
        }

# Istanza globale
intent_router = IntentRouter()
