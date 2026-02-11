"""
PROACTOR - Genesi Core v2
Orchestratore centrale per smistamento modelli e servizi
"""

from typing import Optional, Dict, Any
from core.log import log
from core.relational_engine import generate_relational_response
from core.llm_service import llm_service
from core.tool_services import tool_service

class Proactor:
    """
    Proactor - Cervello di smistamento centrale
    Orchestrazione: Tools → Relational → LLM
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
        
        log("PROACTOR_ACTIVE", tool_services=len(self.tool_intents), 
            relational_services=len(self.relational_intents), 
            llm_services=len(self.llm_intents))
    
    async def handle(self, message: str, user: Dict[str, Any], intent: str) -> str:
        """
        Orchestrazione centrale basata su intent
        
        Args:
            message: Messaggio utente
            user: Profilo utente
            intent: Intent classificato
            
        Returns:
            Risposta orchestrata
        """
        try:
            # 1️⃣ Tool services routing
            if intent in self.tool_intents:
                log("PROACTOR_ROUTE", route="tool", intent=intent, service=intent)
                return await self._handle_tool(intent, message)
            
            # 2️⃣ Relational engine routing
            elif intent in self.relational_intents:
                log("PROACTOR_ROUTE", route="relational", intent=intent)
                return await self._handle_relational(user.get("id", "anonymous"), user, message)
            
            # 3️⃣ LLM service routing
            else:
                log("PROACTOR_ROUTE", route="llm", intent=intent)
                return await self._handle_llm(message)
                
        except Exception as e:
            log("PROACTOR_ERROR", error=str(e), intent=intent)
            return "Mi dispiace, ho avuto un problema. Riprova più tardi."
    
    async def _handle_tool(self, intent: str, message: str) -> str:
        """
        Gestione tool services
        
        Args:
            intent: Intent tool
            message: Messaggio utente
            
        Returns:
            Risposta tool service
        """
        try:
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
            log("PROACTOR_TOOL_ERROR", intent=intent, error=str(e))
            return f"Errore nel servizio {intent}."
    
    async def _handle_relational(self, user_id: str, user_profile: Dict[str, Any], message: str) -> str:
        """
        Gestione relational engine
        
        Args:
            user_id: ID utente
            user_profile: Profilo utente
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
            log("PROACTOR_RELATIONAL_ERROR", error=str(e))
            return "Mi dispiace, ho avuto un problema relazionale."
    
    async def _handle_llm(self, message: str) -> str:
        """
        Gestione LLM service
        
        Args:
            message: Messaggio utente
            
        Returns:
            Risposta LLM service
        """
        try:
            return await llm_service.generate_response(message)
            
        except Exception as e:
            log("PROACTOR_LLM_ERROR", error=str(e))
            return "Mi dispiace, ho avuto un problema tecnico."
    
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
