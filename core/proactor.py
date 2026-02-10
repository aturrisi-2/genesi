"""
PROACTOR - Orchestrate Unico Decisionale
DECIDE CHI PARLA - NON GENERA TESTO
"""

from typing import Dict, Optional, Any
from enum import Enum

class EngineType(Enum):
    """Motori disponibili"""
    GPT_FULL = "gpt_full"          # Fatti, meteo, news, spiegazioni, psicologico
    PERSONALPLEX = "personalplex"  # Chat libera, dialogo naturale
    API_TOOLS = "api_tools"        # Meteo, news API esterne
    VERIFIED_KNOWLEDGE = "verified_knowledge"  # Knowledge base verificato
    PSYCHOLOGICAL = "psychological"  # Supporto emotivo
    DATE_TIME = "date_time"        # Data e ora corrente

class Proactor:
    """
    ORCHESTRATORE UNICO - SOLO DECISIONALE
    
    COMPITI:
    - Analizzare intent
    - Scegliere il motore corretto  
    - Impedire chiamate inutili o dannose
    - NON genera MAI testo
    
    INPUT: Intent classificato + contesto
    OUTPUT: Decisione motore + parametri
    """
    
    def __init__(self):
        # Mapping intent → motore OBBLIGATORIO
        self.intent_engine_mapping = {
            # Richiedono GPT-full (fatti verificabili)
            "medical_info": EngineType.GPT_FULL,
            "historical_info": EngineType.GPT_FULL,
            "definition": EngineType.GPT_FULL,
            "technical": EngineType.GPT_FULL,
            
            # Richiedono API esterne
            "weather": EngineType.API_TOOLS,
            "news": EngineType.API_TOOLS,
            
            # Richiedono conoscenza verificata
            "verified_knowledge": EngineType.VERIFIED_KNOWLEDGE,
            
            # Richiedono supporto psicologico
            "emotional_support": EngineType.PSYCHOLOGICAL,
            
            # Richiede data/ora corrente
            "date_time": EngineType.DATE_TIME,
            
            # Chat libera → PersonalPlex
            "chat_free": EngineType.PERSONALPLEX,
            
            # Identità → GPT-full (per coerenza)
            "identity": EngineType.GPT_FULL,
            
            # Tempo → GPT-full (system time)
            "other": EngineType.GPT_FULL,
        }
        
        # Fallback sicuro
        self.default_engine = EngineType.PERSONALPLEX
    
    def decide_engine(self, intent_type: str, message: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        DECIDE IL MOTORE CORRETTO usando IntentRouter
        
        Args:
            intent_type: Intent classificato da GPT-mini
            message: Messaggio utente
            context: Contesto aggiuntivo
            
        Returns:
            Dict con decisione motore e parametri
        """
        print(f"[PROACTOR] Deciding engine for intent: {intent_type}", flush=True)
        
        # Usa IntentRouter per routing deterministico
        from core.intent_router import intent_router
        routing_info = intent_router.get_routing_info(message)
        
        # Mappa intent → motore basato su routing
        intent_to_engine = {
            "medical_info": EngineType.GPT_FULL,
            "historical_info": EngineType.GPT_FULL,
            "definition": EngineType.GPT_FULL,
            "technical": EngineType.GPT_FULL,
            "weather": EngineType.API_TOOLS,
            "news": EngineType.API_TOOLS,
            "verified_knowledge": EngineType.VERIFIED_KNOWLEDGE,
            "emotional_support": EngineType.PSYCHOLOGICAL,
            "date_time": EngineType.DATE_TIME,  # NUOVO
            "chat_free": EngineType.PERSONALPLEX,
            "identity": EngineType.GPT_FULL,
            "other": EngineType.GPT_FULL,
        }
        
        engine = intent_to_engine.get(routing_info['intent'], self.default_engine)
        
        # Verifiche di sicurezza aggiuntive
        if self._should_block_request(routing_info['intent'], message, context):
            print(f"[PROACTOR] BLOCKED request for safety", flush=True)
            return {
                "engine": EngineType.PERSONALPLEX,
                "action": "safe_fallback",
                "reason": "safety_block",
                "params": {}
            }
        
        # Parametri specifici per motore
        params = self._get_engine_params(engine, routing_info['intent'], message, context)
        
        decision = {
            "engine": engine,
            "action": "generate",
            "intent_type": routing_info['intent'],
            "params": params,
            "confidence": 0.9,  # Sempre alta con mapping deterministico
            "routing_info": routing_info
        }
        
        print(f"[PROACTOR] Decision: {engine.value} for {routing_info['intent']}", flush=True)
        return decision
    
    def _should_block_request(self, intent_type: str, message: str, context: Optional[Dict] = None) -> bool:
        """
        Verifiche di sicurezza - blocca richieste pericolose
        """
        # Blocchi per sicurezza medica
        if intent_type == "medical_info":
            dangerous_keywords = ["suicid", "uccid", "morire", "tossic", "veleno"]
            if any(keyword in message.lower() for keyword in dangerous_keywords):
                return True
        
        # Blocchi per contenuti inappropriati
        inappropriate_patterns = [
            "bomba", "esplosiv", "terrorism", "violenza", "arma"
        ]
        if any(pattern in message.lower() for pattern in inappropriate_patterns):
            return True
        
        return False
    
    def _get_engine_params(self, engine: EngineType, intent_type: str, message: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Parametri specifici per ogni motore
        """
        if engine == EngineType.GPT_FULL:
            return {
                "mode": "factual",
                "temperature": 0.3,  # Bassa per fatti
                "max_tokens": 150,
                "style": "clean",
                "no_theatrical": True,
                "no_emoji": True
            }
        
        elif engine == EngineType.PERSONALPLEX:
            return {
                "mode": "conversational",
                "temperature": 0.7,
                "max_tokens": 80,
                "style": "natural",
                "allow_theatrical": False,  # Bloccato da filtro
                "allow_emoji": False        # Bloccato da filtro
            }
        
        elif engine == EngineType.API_TOOLS:
            return {
                "api_type": intent_type,
                "location": self._extract_location(message),
                "timeout": 5.0
            }
        
        elif engine == EngineType.VERIFIED_KNOWLEDGE:
            return {
                "knowledge_type": intent_type,
                "fallback_to_gpt": True
            }
        
        elif engine == EngineType.PSYCHOLOGICAL:
            return {
                "mode": "empathetic",
                "temperature": 0.5,
                "max_tokens": 120,
                "style": "supportive"
            }
        
        return {}
    
    def _extract_location(self, message: str) -> Optional[str]:
        """
        Estrae location da messaggio per API tools
        """
        import re
        
        # Pattern per città italiane comuni
        cities = ["roma", "milano", "napoli", "torino", "palermo", "genova", 
                 "bologna", "firenze", "bari", "catania", "venezia"]
        
        message_lower = message.lower()
        for city in cities:
            if city in message_lower:
                return city.capitalize()
        
        return None

# Istanza globale
proactor = Proactor()
