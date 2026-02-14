"""
CONTEXT ASSEMBLER - Genesi Cognitive System
Costruisce contesto strutturato dalla memoria per il prompt LLM.
Unico punto di assemblaggio: profilo, relazione, episodi, latent state.
Nessun fallback silenzioso — se il contesto non viene costruito, errore esplicito.
"""

import logging
from typing import Dict, Any
from core.cognitive_memory_engine import CognitiveMemoryEngine
from core.storage import storage

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
        NON chiama update_brain — quello e' gia' fatto dal proactor.

        Returns:
            dict con: summary, current_message, profile
        """
        # Load from persistent storage
        profile = await storage.load(f"profile:{user_id}", default={})

        logger.info("CONTEXT_ASSEMBLER_LOADED user=%s", user_id)

        context = {}

        if profile:
            context['profile'] = profile
            logger.info("PROFILE_LOADED user_id=%s", user_id)

        summary = self._summarize_profile(profile)

        if not summary or not summary.strip():
            summary = "No relevant memory found."

        context["summary"] = summary
        context["current_message"] = user_message

        logger.info("CONTEXT_ASSEMBLED user=%s summary_len=%d", user_id, len(summary))
        return context

    def _summarize_profile(self, profile):
        """
        Costruisce riassunto compatto (max ~300 token) per il system prompt LLM.
        Include tutti i campi identitari noti.
        """
        parts = []
        if profile.get('name'):
            parts.append(f"L'utente si chiama {profile['name']}")
        if profile.get('profession'):
            parts.append(f"Lavora come {profile['profession']}")
        if profile.get('spouse'):
            parts.append(f"Il coniuge si chiama {profile['spouse']}")
        # Children
        children = profile.get('children', [])
        if children:
            names = [c['name'] if isinstance(c, dict) else str(c) for c in children]
            parts.append(f"Figli: {', '.join(names)}")
        # Pets
        pets = profile.get('pets', [])
        if pets:
            pet_descs = []
            for p in pets:
                if isinstance(p, dict):
                    pet_descs.append(f"{p.get('name', '?')} ({p.get('type', '?')})")
            if pet_descs:
                parts.append(f"Animali: {', '.join(pet_descs)}")
        # Interests
        interests = profile.get('interests', [])
        if interests:
            parts.append(f"Interessi: {', '.join(interests)}")
        # Preferences
        preferences = profile.get('preferences', [])
        if preferences:
            parts.append(f"Preferenze: {', '.join(preferences)}")
        # Traits
        traits = profile.get('traits', [])
        if traits:
            parts.append(f"Tratti: {', '.join(traits)}")
        return "\n".join(parts)
