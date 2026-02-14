"""
CONTEXT ASSEMBLER - Genesi Cognitive System
Costruisce contesto strutturato dalla memoria per il prompt LLM.
Unico punto di assemblaggio: profilo, relazione, episodi, latent state.
Nessun fallback silenzioso — se il contesto non viene costruito, errore esplicito.
"""

import logging
from typing import Dict, Any
from core.cognitive_memory_engine import CognitiveMemoryEngine

logger = logging.getLogger(__name__)

cognitive_engine = CognitiveMemoryEngine()

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
            dict con: summary, current_message

        Raises:
            RuntimeError se il summary risulta vuoto dopo l'assemblaggio.
        """
        # Use cognitive memory only
        cognitive_memory = cognitive_engine.evaluate_event(user_id, user_message, {})

        logger.info("CONTEXT_ASSEMBLER_LOADED user=%s", user_id)

        context = {}
        brain_state = await self.memory_brain.update_brain(user_id, user_message)
        context['brain_state'] = brain_state

        if cognitive_memory['persist']:
            context['cognitive_memory'] = cognitive_memory
            logger.info("COGNITIVE_MEMORY_UPDATE user_id=%s", user_id)
        else:
            logger.info("COGNITIVE_MEMORY_EMPTY user_id=%s", user_id)

        summary = self._summarize_cognitive(cognitive_memory)

        if not summary or not summary.strip():
            summary = "No relevant memory found."

        context["summary"] = summary
        context["current_message"] = user_message

        logger.info("CONTEXT_ASSEMBLED user=%s summary_len=%d", user_id, len(summary))
        return context

    def _summarize_cognitive(self, cognitive_memory):
        """
        Costruisce riassunto compatto (max ~300 token) per il system prompt LLM.
        """
        # Build summary from cognitive memory
        parts = []
        if cognitive_memory.get('memory_type') == 'profile':
            parts.append(f"Name: {cognitive_memory.get('value', '')}")
        elif cognitive_memory.get('memory_type') == 'relational':
            parts.append(f"Spouse: {cognitive_memory.get('value', '')}")
        elif cognitive_memory.get('memory_type') == 'episodic':
            parts.append(f"Event: {cognitive_memory.get('value', '')}")
        return "\n".join(parts)
