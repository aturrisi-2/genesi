"""
CONTEXT ASSEMBLER - Genesi Cognitive System
Costruisce contesto strutturato dalla memoria per il prompt LLM.
Unico punto di assemblaggio: profilo, relazione, episodi, latent state.
Nessun fallback silenzioso — se il contesto non viene costruito, errore esplicito.
"""

import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

try:
    from core.memory_engine_v2 import MemoryEngineV2
    memory_v2 = MemoryEngineV2()
    logger.info("MEMORY_V2_ACTIVE")
except ImportError:
    memory_v2 = None
    logger.error("MEMORY_V2_IMPORT_FAILED")


class ContextAssembler:
    """
    Assembla contesto strutturato dalla memoria per il prompt LLM.
    Riceve memory_brain e latent_state_engine come dipendenze.
    """

    def __init__(self, memory_brain, latent_state_engine):
        self.memory_brain = memory_brain
        self.latent_state_engine = latent_state_engine

    async def build(self, user_id: str, user_message: str) -> Dict[str, Any]:
        """
        Costruisce contesto completo per LLM.

        Returns:
            dict con: long_term_profile, relational_state, recent_episodes,
                      latent_state, summary, current_message

        Raises:
            RuntimeError se il summary risulta vuoto dopo l'assemblaggio.
        """
        long_term = await self.memory_brain.semantic.get_profile(user_id)
        relational = await self.memory_brain.relational.load(user_id)
        episodes = await self.memory_brain.episodic.recall(user_id, query=user_message, limit=5)
        latent_state = await self.latent_state_engine.load(user_id)

        logger.info("CONTEXT_ASSEMBLER_LOADED user=%s profile_name=%s trust=%.3f episodes=%d",
                     user_id,
                     long_term.get("name", "unknown"),
                     relational.get("trust", 0),
                     len(episodes))

        context = {}
        brain_state = await self.memory_brain.update_brain(user_id, user_message)
        context['brain_state'] = brain_state

        if memory_v2:
            try:
                structured_memory = memory_v2.load_user_memory(user_id)
                if structured_memory:
                    context['memory_v2'] = structured_memory
                    logger.info("MEMORY_V2_RETRIEVED user_id=%s", user_id)

                    # Inject memory_v2 into LLM prompt
                    context['llm_prompt'] = self._build_llm_prompt(brain_state, structured_memory)
                else:
                    logger.info("MEMORY_V2_EMPTY user_id=%s", user_id)
            except Exception as e:
                logger.error("MEMORY_V2_ERROR user_id=%s error=%s", user_id, str(e))
                logger.info("MEMORY_V2_FALLBACK user_id=%s", user_id)

        summary = self._summarize(long_term, relational, episodes, latent_state)

        if not summary or not summary.strip():
            raise RuntimeError(f"CONTEXT_ASSEMBLER_EMPTY user={user_id} — Context not built. Memory injection failed.")

        context["long_term_profile"] = long_term
        context["relational_state"] = relational
        context["recent_episodes"] = episodes
        context["latent_state"] = latent_state or {}
        context["summary"] = summary
        context["current_message"] = user_message

        logger.info("CONTEXT_ASSEMBLED user=%s summary_len=%d", user_id, len(summary))
        return context

    def _build_llm_prompt(self, brain_state, structured_memory):
        # Build LLM prompt with memory_v2 as a separate block
        prompt = ""
        # Existing prompt construction logic
        # ...
        # Inject memory_v2
        if 'profile' in structured_memory:
            prompt += f"\nMEMORY_V2_PROFILE: {structured_memory['profile']}"
        if 'relational' in structured_memory:
            prompt += f"\nMEMORY_V2_RELATIONAL: {structured_memory['relational']}"
        if 'episodic' in structured_memory:
            prompt += f"\nMEMORY_V2_EPISODIC: {structured_memory['episodic']}"

        # Conflict resolution: prioritize memory_v2
        if structured_memory.get('profile', {}).get('name'):
            brain_state['profile']['name'] = structured_memory['profile']['name']

        return prompt

    def _summarize(self, long_term: Dict[str, Any], relational: Dict[str, Any],
                   episodes: List[Dict[str, Any]], latent_state: Any) -> str:
        """
        Costruisce riassunto compatto (max ~300 token) per il system prompt LLM.
        """
        parts = []

        # — Profilo utente —
        user_facts = []
        name = long_term.get("name")
        if name:
            user_facts.append(f"Nome: {name}")
        age = long_term.get("age")
        if age:
            user_facts.append(f"Eta': {age}")
        city = long_term.get("city")
        if city:
            user_facts.append(f"Citta': {city}")
        profession = long_term.get("profession")
        if profession:
            user_facts.append(f"Professione: {profession}")
        entities = long_term.get("entities", {})
        for role, data in entities.items():
            ent_name = data.get("name")
            if ent_name:
                user_facts.append(f"{role}: {ent_name}")
        if user_facts:
            parts.append("PROFILO UTENTE:\n" + "\n".join(user_facts))

        # — Stato relazionale —
        trust = relational.get("trust", 0.15)
        depth = relational.get("depth", 0.1)
        stage = relational.get("stage", "initial")
        total_msgs = relational.get("history", {}).get("total_msgs", 0)
        current_emotion = relational.get("history", {}).get("last_emotion", "neutral")
        parts.append(
            f"STATO RELAZIONALE:\n"
            f"Trust: {trust:.2f}\n"
            f"Profondita': {depth:.2f}\n"
            f"Fase: {stage}\n"
            f"Messaggi totali: {total_msgs}\n"
            f"Emozione corrente: {current_emotion}"
        )

        # — Episodi recenti —
        if episodes:
            ep_lines = ["EPISODI RECENTI:"]
            for i, ep in enumerate(episodes[:5], 1):
                msg_preview = ep.get("msg", "")[:80]
                ep_emotion = ep.get("emotion", "neutral")
                ep_lines.append(f"{i}. \"{msg_preview}\" (emozione: {ep_emotion})")
            parts.append("\n".join(ep_lines))

        # — Pattern comportamentali —
        patterns = long_term.get("patterns", [])
        if patterns:
            p_lines = ["PATTERN COMPORTAMENTALI:"]
            for p in patterns[:5]:
                if p.get("type") == "emotion":
                    p_lines.append(f"- Tendenza emotiva: {p.get('key', '')}")
                elif p.get("type") == "topic":
                    p_lines.append(f"- Interesse: {p.get('key', '')}")
            if len(p_lines) > 1:
                parts.append("\n".join(p_lines))

        # — Tono relazionale suggerito —
        if trust >= 0.65:
            tone = "Intimo, diretto, profondo. Usa il nome dell'utente."
        elif trust >= 0.35:
            tone = "Caldo, empatico, aperto. Riferisci a episodi passati."
        else:
            tone = "Accogliente, curioso, rispettoso. Costruisci fiducia."
        parts.append(f"TONO RELAZIONALE: {tone}")

        return "\n\n".join(parts)
