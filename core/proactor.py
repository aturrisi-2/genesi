"""PROACTOR - Genesi Cognitive System v3
Orchestratore centrale con memoria neurale multi-strato.
Pipeline: brain.update → latent_state.update → evolution_engine → curiosity_engine → emotional_intensity → drift_modulator
LLM chiamato SOLO per complessità cognitiva elevata. Zero API extra.
"""

import logging
from typing import Optional, Dict, Any
from core.log import log
from core.memory_brain import memory_brain
from core.evolution_engine import generate_response_from_brain
from core.latent_state import latent_state_engine
from core.drift_modulator import drift_modulator
from core.curiosity_engine import curiosity_engine
from core.emotional_intensity_engine import emotional_intensity_engine
from core.tool_services import tool_service
from core.storage import storage

logger = logging.getLogger(__name__)


class Proactor:
    """
    Proactor v3 — Pipeline con vettore latente, curiosita', intensita' emotiva e drift modulator.
    brain.update → latent_state.update → evolution_engine → curiosity_engine → emotional_intensity → drift_modulator
    Zero chiamate LLM ridondanti. Zero analisi emotiva via API.
    """

    def __init__(self):
        self.tool_intents = ["weather", "news", "time", "date"]
        self.all_intents = self.tool_intents
        logger.info("PROACTOR_V3_ACTIVE", extra={"tool_intents": len(self.tool_intents), "emotional_intensity": True})

    async def handle(self, message: str, intent: str, user_id: str) -> str:
        """
        Orchestrazione centrale v3.
        1. memory_brain.update_brain()
        2. latent_state_engine.update_latent_state()
        3. _build_relational_context() → inject into brain_state
        4. evolution_engine.generate_response_from_brain()
        5. curiosity_engine.inject()
        6. emotional_intensity_engine.enhance()
        7. drift_modulator.modulate_response_style()
        """
        try:
            if not user_id:
                raise ValueError("Proactor received empty user_id")

            logger.info("PROACTOR_START user=%s intent=%s msg_len=%d", user_id, intent, len(message))

            # ── 1. BRAIN UPDATE (emotion locale, semantic, episodic, relational, consolidation) ──
            brain_state = await memory_brain.update_brain(user_id, message)
            logger.info("PROACTOR_MEMORY_UPDATED user=%s profile_name=%s trust=%.3f episodes=%d",
                        user_id,
                        brain_state.get('profile', {}).get('name', 'unknown'),
                        brain_state.get('relational', {}).get('trust', 0),
                        len(brain_state.get('episodes', [])))

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
                logger.info("PROACTOR_ROUTE route=tool intent=%s user=%s", intent, user_id)
                return await self._handle_tool(intent, message, user_id)

            # ── 4. BUILD RELATIONAL CONTEXT — injected into brain_state for LLM ──
            relational_context = self._build_relational_context(brain_state)
            if not relational_context:
                logger.error("PROACTOR_CONTEXT_EMPTY user=%s — context builder returned empty", user_id)
            brain_state["relational_context"] = relational_context
            logger.info("PROACTOR_CONTEXT_BUILT user=%s context_len=%d", user_id, len(relational_context))

            # ── 5. EVOLUTION ENGINE (relational + LLM gate) ──
            logger.info("PROACTOR_LLM_CALL user=%s intent=%s context_len=%d", user_id, intent, len(relational_context))
            base_response = await generate_response_from_brain(user_id, message, brain_state)
            logger.info("PROACTOR_LLM_RESPONSE user=%s response_len=%d", user_id, len(base_response))

            # ── 6. CURIOSITY ENGINE (selective exploration, targeted questions) ──
            curious_response = curiosity_engine.inject(base_response, message, brain_state)

            # ── 7. EMOTIONAL INTENSITY (expand, explore, anti-passive) ──
            enhanced_response = emotional_intensity_engine.enhance(curious_response, message, brain_state)

            # ── 8. DRIFT MODULATOR (probabilistic tone modulation) ──
            latent_vector = latent_state_engine.get_vector(latent)
            response = drift_modulator.modulate_response_style(
                latent_state=latent_vector,
                relational_state=brain_state.get("relational", {}),
                base_response=enhanced_response
            )

            logger.info("PROACTOR_RESPONSE user=%s len=%d emotion=%s trust=%.3f att=%.3f eng=%.3f",
                        user_id, len(response),
                        brain_state.get("emotion", {}).get("emotion", "?"),
                        brain_state.get("relational", {}).get("trust", 0),
                        latent.get("attachment", 0), latent.get("relational_energy", 0))
            return response

        except Exception as e:
            logger.error("PROACTOR_ERROR_FULL user=%s intent=%s error=%s", user_id, intent, str(e), exc_info=True)
            # Fallback di ultima istanza — mai risposta vuota, ma sempre loggato
            try:
                profile = await memory_brain.semantic.get_profile(user_id)
                name = profile.get("name", "")
            except Exception:
                name = ""
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
            logger.error("PROACTOR_TOOL_ERROR intent=%s user=%s error=%s", intent, user_id, str(e), exc_info=True)
            return f"Errore nel servizio {intent}."

    @staticmethod
    def _build_relational_context(brain_state: Dict[str, Any]) -> str:
        """
        Costruisce blocco di contesto relazionale per il prompt LLM.
        Include: profilo utente, stato relazionale, ultimi 3 episodi, tono.
        """
        profile = brain_state.get("profile", {})
        rel = brain_state.get("relational", {})
        emotion = brain_state.get("emotion", {})
        episodes = brain_state.get("episodes", [])
        latent = brain_state.get("latent", {})

        parts = []

        # -- Profilo utente --
        user_facts = []
        if profile.get("name"):
            user_facts.append(f"Nome: {profile['name']}")
        if profile.get("age"):
            user_facts.append(f"Eta': {profile['age']}")
        if profile.get("city"):
            user_facts.append(f"Citta': {profile['city']}")
        if profile.get("profession"):
            user_facts.append(f"Professione: {profile['profession']}")
        entities = profile.get("entities", {})
        for role, data in entities.items():
            name = data.get("name")
            if name:
                user_facts.append(f"{role}: {name}")
        if user_facts:
            parts.append("PROFILO UTENTE:\n" + "\n".join(user_facts))

        # -- Stato relazionale --
        trust = rel.get("trust", 0.15)
        depth = rel.get("depth", 0.1)
        stage = rel.get("stage", "initial")
        msgs = rel.get("history", {}).get("total_msgs", 0)
        parts.append(
            f"STATO RELAZIONALE:\n"
            f"Trust: {trust:.2f}\n"
            f"Profondita': {depth:.2f}\n"
            f"Fase: {stage}\n"
            f"Messaggi totali: {msgs}\n"
            f"Emozione corrente: {emotion.get('emotion', 'neutral')} (intensita': {emotion.get('intensity', 0.3):.2f})"
        )

        # -- Ultimi 3 episodi --
        if episodes:
            ep_lines = ["EPISODI RECENTI:"]
            for i, ep in enumerate(episodes[:3], 1):
                ep_lines.append(f"{i}. \"{ep.get('msg', '')[:80]}\" (emozione: {ep.get('emotion', 'neutral')})")
            parts.append("\n".join(ep_lines))

        # -- Pattern comportamentali --
        patterns = profile.get("patterns", [])
        if patterns:
            p_lines = ["PATTERN COMPORTAMENTALI:"]
            for p in patterns[:5]:
                if p.get("type") == "emotion":
                    p_lines.append(f"- Tendenza emotiva: {p.get('key', '')}")
                elif p.get("type") == "topic":
                    p_lines.append(f"- Interesse: {p.get('key', '')}")
            parts.append("\n".join(p_lines))

        # -- Tono relazionale suggerito --
        if trust >= 0.65:
            tone = "Intimo, diretto, profondo. Usa il nome dell'utente."
        elif trust >= 0.35:
            tone = "Caldo, empatico, aperto. Riferisci a episodi passati."
        else:
            tone = "Accogliente, curioso, rispettoso. Costruisci fiducia."
        parts.append(f"TONO RELAZIONALE: {tone}")

        context = "\n\n".join(parts)
        logger.info("PROACTOR_RELATIONAL_INJECTED context_len=%d trust=%.2f stage=%s", len(context), trust, stage)
        return context

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
            "engine": "evolution_engine + curiosity_engine + emotional_intensity + drift_modulator",
            "memory": "memory_brain (4-layer) + latent_state (5-dim)",
            "llm_gate": "complexity >= 0.6"
        }


# Istanza globale
proactor = Proactor()
