"""
PROACTOR - Genesi Core v2
Orchestratore centrale con memoria persistente e user ID reali
"""

import logging
from typing import Optional, Dict, Any
from core.log import log
from core.relational_engine import generate_relational_response
from core.llm_service import llm_service
from core.tool_services import tool_service
from core.semantic_memory import semantic_memory
from core.storage import storage

logger = logging.getLogger(__name__)

class Proactor:
    """
    Proactor - Cervello di smistamento centrale con memoria persistente
    Orchestrazione completa: Memory → Tools → Relational → LLM
    """
    
    def __init__(self):
        # Intent per tool services
        self.tool_intents = [
            "weather", "news", "time", "date"
        ]
        
        # Intent per relational engine
        self.relational_intents = [
            "relational", "greeting", "how_are_you", "identity", 
            "goodbye", "help", "chat_free"
        ]
        
        # Intent per LLM service
        self.llm_intents = [
            "tecnica", "debug", "spiegazione", "architettura"
        ]
        
        logger.info("PROACTOR_ACTIVE", extra={"tool_services": len(self.tool_intents), 
            "relational_services": len(self.relational_intents), 
            "llm_services": len(self.llm_intents)})
    
    async def handle(self, message: str, intent: str, user_id: str) -> str:
        """
        Orchestrazione centrale con memoria persistente
        
        Args:
            message: Messaggio utente
            intent: Intent classificato
            user_id: ID utente reale obbligatorio
            
        Returns:
            Risposta orchestrata
        """
        try:
            # Enforce user_id reale - MAI None o unknown
            if not user_id:
                raise ValueError("Proactor received empty user_id")
            
            logger.info("PROACTOR_HANDLE", extra={"user_id": user_id, "intent": intent})
            
            # Carica profilo utente per context
            from core.semantic_memory import semantic_memory
            user_profile = await semantic_memory.get_user_profile(user_id)
            
            # 1️⃣ Tool services routing
            if intent in self.tool_intents:
                logger.info("PROACTOR_ROUTE", extra={"route": "tool", "intent": intent, "service": intent})
                return await self._handle_tool(intent, message, user_id)
            
            # 2️⃣ Relational engine routing
            elif intent in self.relational_intents:
                logger.info("PROACTOR_ROUTE", extra={"route": "relational", "intent": intent})
                return await self._handle_relational(user_id, user_profile, message)
            
            # 3️⃣ LLM service routing
            else:
                logger.info("PROACTOR_ROUTE", extra={"route": "llm", "intent": intent})
                return await self._handle_llm(user_id, user_profile, message)
                
        except Exception as e:
            logger.error("PROACTOR_ERROR", exc_info=True, extra={"error": str(e), "intent": intent, "user_id": user_id})
            return "Mi dispiace, ho avuto un problema. Riprova più tardi."
    
    async def _handle_tool(self, intent: str, message: str, user_id: str) -> str:
        """
        Gestione tool services con user ID
        
        Args:
            intent: Intent tool
            message: Messaggio utente
            user_id: ID utente reale
            
        Returns:
            Risposta tool service
        """
        try:
            # Estrai dati semantici anche per tools
            await semantic_memory.extract_and_store_personal_data(message, user_id)
            
            if intent == "weather":
                return await tool_service.get_weather(message)
            elif intent == "news":
                return await tool_service.get_news(message)
            elif intent == "time":
                return await tool_service.get_time()
            elif intent == "date":
                return await tool_service.get_date()
            else:
                return "Tool non disponibile."
                
        except Exception as e:
            logger.error("PROACTOR_TOOL_ERROR", exc_info=True, extra={"intent": intent, "error": str(e), "user_id": user_id})
            return f"Errore nel servizio {intent}."
    
    async def _handle_relational(self, user_id: str, user_profile: Dict[str, Any], message: str) -> str:
        """
        Gestione relational engine con memoria persistente
        
        Args:
            user_id: ID utente reale
            user_profile: Profilo utente completo
            message: Messaggio utente
            
        Returns:
            Risposta relational engine
        """
        try:
            return await generate_relational_response(
                user_id=user_id,
                user_profile=user_profile,
                message=message
            )
            
        except Exception as e:
            logger.error("PROACTOR_RELATIONAL_ERROR", exc_info=True, extra={"error": str(e), "user_id": user_id})
            return "Mi dispiace, ho avuto un problema relazionale."
    
    async def _handle_llm(self, user_id: str, user_profile: Dict[str, Any], message: str) -> str:
        """
        Gestione LLM service con memoria contestuale
        
        Args:
            user_id: ID utente reale
            user_profile: Profilo utente
            message: Messaggio utente
            
        Returns:
            Risposta LLM service
        """
        try:
            # Estrai dati semantici anche per LLM
            await semantic_memory.extract_and_store_personal_data(message, user_id)
            
            # Carica profilo completo per context
            full_profile = await semantic_memory.get_user_profile(user_id)
            
            # Genera risposta con contesto utente
            return await llm_service.generate_response_with_context(message, full_profile, user_id)
            
        except Exception as e:
            logger.error("PROACTOR_LLM_ERROR", exc_info=True, extra={"error": str(e), "user_id": user_id})
            return "Mi dispiace, ho avuto un problema tecnico."
    
    async def get_user_memory_summary(self, user_id: str) -> Dict[str, Any]:
        """
        Ottieni riepilogo memoria completa utente
        
        Args:
            user_id: ID utente
            
        Returns:
            Riepilogo memoria utente
        """
        try:
            # Profilo semantico
            profile = await semantic_memory.get_user_profile(user_id)
            
            # Stato relazionale
            from core.relational_state import relational_state
            state_summary = await relational_state.get_state_summary(user_id)
            
            # Storage stats
            storage_stats = await storage.get_storage_stats()
            
            return {
                "user_id": user_id,
                "profile": profile,
                "relational_state": state_summary,
                "storage_stats": storage_stats
            }
            
        except Exception as e:
            logger.error("PROACTOR_MEMORY_ERROR", exc_info=True, extra={"error": str(e), "user_id": user_id})
            return {"error": str(e)}
    
    def get_routing_stats(self) -> Dict[str, Any]:
        """
        Statistiche routing Proactor
        
        Returns:
            Dict con statistiche routing
        """
        return {
            "tool_intents": self.tool_intents,
            "relational_intents": self.relational_intents,
            "llm_intents": self.llm_intents,
            "total_routes": len(self.tool_intents) + len(self.relational_intents) + len(self.llm_intents)
        }

# Istanza globale
proactor = Proactor()
