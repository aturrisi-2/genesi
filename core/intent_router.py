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
    IDENTITY = "identity"
    DATE_TIME = "date_time"  # NUOVO: per "che giorno è oggi"
    OTHER = "other"

class IntentRouter:
    """
    ROUTING DETERMINISTICO BASATO SU KEYWORD
    Classifica messaggi utente senza usare LLM
    """
    
    def __init__(self):
        # Keyword patterns per ogni categoria
        self.patterns = {
            IntentType.DATE_TIME: [
                # Data e ora
                r"che giorno è oggi",
                r"che giorno e oggi",
                r"che giorno è",
                r"che data è oggi",
                r"che data è",
                r"che ora è",
                r"che ore sono",
                r"che data e ora",
                r"giorno della settimana",
                r"data di oggi",
                r"ora attuale",
                r"ora corrente",
                r"tempo attuale",
                r"quanto manca a",
                r"che mese siamo",
                r"che anno siamo",
                r"in che giorno siamo",
                r"ci troviamo a",
                r"ci troviamo nel"
            ],
            
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
            
            IntentType.EMOTIONAL_SUPPORT: [
                # Segnali di distress emotivo
                r"depresso", r"depressa", r"depressione", r"triste", r"tristezza",
                r"ansia", r"ansioso", r"ansiosa", r"stress", r"stressato", r"stressata",
                r"panico", r"attacco di panico", r"crisi", r"crisi di pianto",
                r"mi sento solo", r"mi sento sola", r"solitudine", r"abbandonato",
                r"non ce la faccio", r"non ne posso più", r"sono stufo", r"sono stufa",
                r"mi sento male", r"sto male", r"non sto bene", r"mi sento giù",
                r"mi sento vuoto", r"senza speranza", r"disperato", r"disperata",
                r"paura", r"spaventato", r"spaventata", r"preoccupato", r"preoccupata",
                r"angoscia", r"angosciato", r"angosciata", r"tormento", r"tormentato",
                r"burnout", r"esaurimento", r"crollo", r"crollo nervoso",
                r"piangere", r"piango", r"ho pianto", r"voglio piangere",
                r"aiutami", r"salvami", r"non so cosa fare", r"sono confuso",
                r"oggi sono", r"mi sento", r"sono in", r"sono troppo"
            ],
            
            IntentType.HISTORICAL_INFO: [
                # Domande storiche generiche
                r"chi è", r"chi era", r"chi furono", r"chi sono",
                r"com'è", r"come era", r"come furono", r"come sono",
                r"quando è nato", r"quando nacque", r"quando morì", r"quando mori",
                r"dove è nato", r"dove nacque", r"dove morì", r"dove mori",
                r"cosa ha fatto", r"cosa fece", r"cosa fece famoso",
                # Definizioni e concetti
                r"cos'è", r"cosa è", r"che cos'è", r"che cosa è",
                r"definizione", r"significato", r"spiegami", r"spiega",
                r"come funziona", r"come funziona", r"come funzionano",
                # Periodi storici
                r"romani", r"greci", r"egizi", r"medioevo", r"rinascimento",
                r"antichità", r"storia", r"storico", r"storica",
                # Eventi storici
                r"guerra", r"rivoluzione", r"battaglia", r"impero", r"regno",
                r"medioevo", r"rinascimento", r"illuminismo", r"rivoluzione industriale",
                # Domande su persone storiche
                r"napoleone", r"giulio cesare", r"leonardo da vinci", r"michelangelo",
                r"dante", r"petrarca", r"galileo", r"newton", r"einstein",
                # Nomi storici comuni
                r"alessandro", r"magno", r"attila", r"carlo magno", r"marco aurelio",
                r"augusto", r"traiano", r"nerone", r"costantino", r"giustiniano"
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
                r"aiutami", r"aiuto", r"consiglio", r"parlare con",
                # Pattern specifici per distress
                r"oggi sono depresso", r"oggi sono depressa", r"sono depresso", r"sono depressa",
                r"mi sento depresso", r"mi sento depressa", r"sentendomi depresso", r"sentendomi depressa"
            ],
            
            IntentType.IDENTITY: [
                # Identità e nome - pattern più specifici
                r"mi chiamo", r"il mio nome è", r"il mio cognome è",
                r"ti ricordi il mio nome", r"ricordi il mio nome", r"come ti chiami",
                r"il mio nome", r"il cognome", r"chi sono io", r"dimmi il mio nome"
            ],
            
            IntentType.OTHER: [
                # Tempo e date
                r"che giorno è", r"che ore sono", r"che data è", r"quanti ne abbiamo",
                r"che tempo è", r"che ora è", r"che data è oggi", r"oggi che giorno è",
                r"anno corrente", r"anno in corso", r"che anno è", r"quale anno"
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
            
            IntentType.IDENTITY: {
                "source": "identity_memory",
                "llm_creative": False,
                "verified_data": True,
                "tone": "friendly"
            },
            
            IntentType.DATE_TIME: {
                "source": "system_time",
                "llm_creative": False,
                "verified_data": True,
                "tone": "informative"
            },
            
            IntentType.OTHER: {
                "source": "system_time",
                "llm_creative": False,
                "verified_data": True,
                "tone": "informative"
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
            IntentType.NEWS,
            IntentType.DATE_TIME,  # NUOVO: blocca LLM per data/ora
            IntentType.OTHER,
            IntentType.IDENTITY
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
