"""PROACTOR - Genesi Cognitive System v3
Orchestratore centrale con memoria neurale multi-strato.
Pipeline: brain.update → latent_state.update → evolution_engine → drift_modulator
LLM chiamato SOLO per complessità cognitiva elevata. Zero API extra.
"""

import logging
from typing import Optional, Dict, Any
from core.log import log
from core.memory_brain import memory_brain
from core.evolution_engine import generate_response_from_brain
from core.latent_state import latent_state_engine
from core.drift_modulator import drift_modulator
from core.tool_services import tool_service
from core.storage import storage

logger = logging.getLogger(__name__)


class Proactor:
    """
    Proactor v3 — Pipeline con vettore latente e drift modulator.
    brain.update → latent_state.update → evolution_engine → drift_modulator
    Zero chiamate LLM ridondanti. Zero analisi emotiva via API.
    """

    def __init__(self):
        self.tool_intents = ["weather", "news", "time", "date"]
        self.all_intents = self.tool_intents
        logger.info("PROACTOR_V3_ACTIVE", extra={"tool_intents": len(self.tool_intents)})

    async def handle(self, message: str, intent: str, user_id: str) -> str:
        """
        Orchestrazione centrale v3.
        1. memory_brain.update_brain()
        2. latent_state_engine.update_latent_state()
        3. evolution_engine.generate_response_from_brain()
        4. drift_modulator.modulate_response_style()
        """
        try:
            if not user_id:
                raise ValueError("Proactor received empty user_id")

            logger.info("PROACTOR_HANDLE", extra={"user_id": user_id, "intent": intent})

            # ── 1. BRAIN UPDATE (emotion locale, semantic, episodic, relational, consolidation) ──
            brain_state = await memory_brain.update_brain(user_id, message)

            # ── 2. LATENT STATE UPDATE (zero LLM) ──
            latent = await latent_state_engine.update_latent_state(
                user_id=user_id,
                user_message=message,
                emotional_analysis=brain_state.get("emotion", {}),
                relational_state=brain_state.get("relational", {}),
                episode_stored=brain_state.get("episode_id") is not None,
                episode_tags=self._extract_episode_tags(brain_state)
            )
            brain_state["latent"] = latent

            # ── 3. TOOL ROUTING ──
            if intent in self.tool_intents:
                logger.info("PROACTOR_ROUTE", extra={"route": "tool", "intent": intent})
                return await self._handle_tool(intent, message, user_id)

            # ── 4. EVOLUTION ENGINE (relational + LLM gate) ──
            logger.info("PROACTOR_ROUTE", extra={"route": "evolution", "intent": intent})
            base_response = await generate_response_from_brain(user_id, message, brain_state)

            # ── 5. DRIFT MODULATOR (probabilistic tone modulation) ──
            latent_vector = latent_state_engine.get_vector(latent)
            response = drift_modulator.modulate_response_style(
                latent_state=latent_vector,
                relational_state=brain_state.get("relational", {}),
                base_response=base_response
            )

            logger.info("PROACTOR_RESPONSE user=%s len=%d emotion=%s trust=%.3f att=%.3f eng=%.3f",
                        user_id, len(response),
                        brain_state.get("emotion", {}).get("emotion", "?"),
                        brain_state.get("relational", {}).get("trust", 0),
                        latent.get("attachment", 0), latent.get("relational_energy", 0))
            return response

        except Exception as e:
            logger.error("PROACTOR_ERROR", exc_info=True, extra={"error": str(e), "intent": intent, "user_id": user_id})
            # Fallback di ultima istanza — mai risposta vuota
            profile = await memory_brain.semantic.get_profile(user_id)
            name = profile.get("name", "")
            prefix = f"{name}, " if name else ""
            return f"{prefix}mi dispiace, ho avuto un problema. Riprova tra poco."

    async def _handle_tool(self, intent: str, message: str, user_id: str) -> str:
        """Tool services routing (weather, news, time, date)."""
        try:
            # Semantic extraction happens in brain update already
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

    def _extract_episode_tags(self, brain_state: Dict[str, Any]) -> list:
        """Estrae tags dall'episodio appena creato."""
        episodes = brain_state.get("episodes", [])
        if episodes:
            return episodes[0].get("tags", [])
        return []

    async def get_user_memory_summary(self, user_id: str) -> Dict[str, Any]:
        """Riepilogo memoria completa utente via memory_brain + latent state."""
        try:
            profile = await memory_brain.semantic.get_profile(user_id)
            rel_state = await memory_brain.relational.load(user_id)
            episodes = await memory_brain.episodic.recall(user_id, limit=10)
            latent = await latent_state_engine.load(user_id)
            storage_stats = await storage.get_storage_stats()

            return {
                "user_id": user_id,
                "profile": profile,
                "relational_state": {
                    "trust": rel_state.get("trust", 0),
                    "depth": rel_state.get("depth", 0),
                    "stage": rel_state.get("stage", "initial"),
                    "total_msgs": rel_state.get("history", {}).get("total_msgs", 0)
                },
                "latent_state": latent_state_engine.get_vector(latent),
                "episode_count": len(episodes),
                "storage_stats": storage_stats
            }
        except Exception as e:
            logger.error("PROACTOR_MEMORY_ERROR", exc_info=True, extra={"error": str(e), "user_id": user_id})
            return {"error": str(e)}

    def get_routing_stats(self) -> Dict[str, Any]:
        """Statistiche routing Proactor."""
        return {
            "tool_intents": self.tool_intents,
            "engine": "evolution_engine + drift_modulator",
            "memory": "memory_brain (4-layer) + latent_state (5-dim)",
            "llm_gate": "complexity >= 0.6"
        }


# Istanza globale
proactor = Proactor()
