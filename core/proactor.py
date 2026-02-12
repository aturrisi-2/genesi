"""
PROACTOR - Genesi Core v2
Orchestratore centrale con memoria neurale persistente e user ID reali
"""

import logging
from datetime import datetime
from typing import Optional, Dict, Any
from core.log import log
from core.relational_engine import generate_relational_response
from core.llm_service import llm_service
from core.tool_services import tool_service
from core.semantic_memory import semantic_memory
from core.episodic_memory import episodic_memory
from core.memory_consolidation import memory_consolidation
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
        Orchestrazione centrale con memoria neurale persistente
        
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
            
            # 0️⃣ Analisi emozionale per memoria episodica
            from core.emotion_analyzer import analyze_emotion
            emotion = await analyze_emotion(message)
            
            # 1️⃣ Creazione contesto per memoria episodica
            context = {
                "intent": intent,
                "message_length": len(message),
                "is_personal_question": self._is_personal_question(message),
                "has_emotional_expression": emotion.get("emotion") != "neutral",
                "references_past": self._references_past(message),
                "timestamp": datetime.now().isoformat()
            }
            
            # 2️⃣ Creazione episodio episodico (se rilevante)
            episode_id = await episodic_memory.create_episode(user_id, message, emotion, context)
            
            # 3️⃣ Verifica consolidamento memoria
            if await memory_consolidation.check_consolidation_needed(user_id):
                consolidation_results = await memory_consolidation.consolidate_memory(user_id)
                logger.info("MEMORY_CONSOLIDATION", extra={"user_id": user_id, **consolidation_results})
            
            # 4️⃣ Carica profilo utente per context
            user_profile = await semantic_memory.get_user_profile(user_id)
            
            # 5️⃣ Tool services routing
            if intent in self.tool_intents:
                logger.info("PROACTOR_ROUTE", extra={"route": "tool", "intent": intent, "service": intent})
                return await self._handle_tool(intent, message, user_id)
            
            # 6️⃣ Relational engine routing con memoria episodica
            elif intent in self.relational_intents:
                logger.info("PROACTOR_ROUTE", extra={"route": "relational", "intent": intent})
                return await self._handle_relational(user_id, user_profile, message, emotion, context)
            
            # 7️⃣ LLM service routing con memoria episodica
            else:
                logger.info("PROACTOR_ROUTE", extra={"route": "llm", "intent": intent})
                return await self._handle_llm(user_id, user_profile, message, emotion, context)
                
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
    
    async def _handle_relational(self, user_id: str, user_profile: Dict[str, Any], message: str, 
                            emotion: Dict[str, Any], context: Dict[str, Any]) -> str:
        """
        Gestione relational engine con memoria episodica
        
        Args:
            user_id: ID utente reale
            user_profile: Profilo utente completo
            message: Messaggio utente
            emotion: Dati emotivi
            context: Contesto episodico
            
        Returns:
            Risposta relational engine
        """
        try:
            # Recupera episodi rilevanti per contesto
            relevant_episodes = await episodic_memory.get_relevant_episodes(user_id, limit=3)
            
            # Aggiungi episodi al contesto per relational engine
            enhanced_context = {
                **context,
                "relevant_episodes": relevant_episodes,
                "episode_count": len(relevant_episodes)
            }
            
            return await generate_relational_response(
                user_id=user_id,
                user_profile=user_profile,
                message=message,
                emotion=emotion,
                context=enhanced_context
            )
            
        except Exception as e:
            logger.error("PROACTOR_RELATIONAL_ERROR", exc_info=True, extra={"error": str(e), "user_id": user_id})
            return "Mi dispiace, ho avuto un problema relazionale."
    
    async def _handle_llm(self, user_id: str, user_profile: Dict[str, Any], message: str, 
                        emotion: Dict[str, Any], context: Dict[str, Any]) -> str:
        """
        Gestione LLM service con memoria episodica
        
        Args:
            user_id: ID utente reale
            user_profile: Profilo utente
            message: Messaggio utente
            emotion: Dati emotivi
            context: Contesto episodico
            
        Returns:
            Risposta LLM service
        """
        try:
            # Recupera episodi rilevanti per contesto
            relevant_episodes = await episodic_memory.get_relevant_episodes(user_id, limit=3)
            
            # Estrai dati semantici anche per LLM
            await semantic_memory.extract_and_store_personal_data(message, user_id)
            
            # Carica profilo completo per context
            full_profile = await semantic_memory.get_user_profile(user_id)
            
            # Aggiungi episodi al profilo per LLM
            enhanced_profile = {
                **full_profile,
                "recent_episodes": relevant_episodes,
                "episode_count": len(relevant_episodes)
            }
            
            # Genera risposta con contesto utente + episodi
            return await llm_service.generate_response_with_context(message, enhanced_profile, user_id)
            
        except Exception as e:
            logger.error("PROACTOR_LLM_ERROR", exc_info=True, extra={"error": str(e), "user_id": user_id})
            return "Mi dispiace, ho avuto un problema tecnico."
    
    def _is_personal_question(self, message: str) -> bool:
        """
        Verifica se messaggio contiene domanda personale
        
        Args:
            message: Messaggio utente
            
        Returns:
            True se domanda personale
        """
        personal_patterns = [
            "come mi chiamo", "ti ricordi il mio nome", "qual è il mio nome",
            "chi sono", "cosa sai di me", "ricordi", "ti ricordi"
        ]
        
        message_lower = message.lower()
        return any(pattern in message_lower for pattern in personal_patterns)
    
    def _references_past(self, message: str) -> bool:
        """
        Verifica se messaggio fa riferimento al passato
        
        Args:
            message: Messaggio utente
            
        Returns:
            True se riferimento al passato
        """
        past_patterns = [
            "prima", "già", "ancora", "sempre", "mai", "di nuovo",
            "ricordo", "avevamo", "avevo", "eri", "era"
        ]
        
        message_lower = message.lower()
        return any(pattern in message_lower for pattern in past_patterns)
    
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
