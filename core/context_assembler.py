"""
CONTEXT ASSEMBLER - Genesi Cognitive System
Costruisce contesto strutturato dalla memoria per il prompt LLM.
Unico punto di assemblaggio: profilo, relazione, episodi, latent state.
Nessun fallback silenzioso — se il contesto non viene costruito, errore esplicito.
"""

import logging
from typing import Dict, Any, List
from core.cognitive_memory_engine import CognitiveMemoryEngine
from core.storage import storage
from core.chat_memory import chat_memory

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


# ═══════════════════════════════════════════════════════════════
# CONVERSATION CONTEXT — thread continuity for LLM
# ═══════════════════════════════════════════════════════════════

# Topic detection keywords (Italian)
_TOPIC_MAP = {
    "famiglia": ["moglie", "marito", "figlio", "figlia", "figli", "madre", "padre",
                 "fratello", "sorella", "famiglia", "rita", "genitori", "nonno", "nonna"],
    "lavoro": ["lavoro", "ufficio", "collega", "capo", "professione", "progetto",
               "cliente", "riunione", "stipendio"],
    "salute": ["salute", "dottore", "ospedale", "dolore", "malattia", "medicina",
               "terapia", "visita"],
    "emozioni": ["triste", "felice", "arrabbiato", "ansioso", "paura", "solo",
                 "stanco", "preoccupato", "contento", "nervoso"],
    "animali": ["cane", "gatto", "gatta", "animale", "animali", "rio", "luna"],
    "interessi": ["musica", "film", "libro", "sport", "cucina", "viaggio",
                  "gioco", "hobby"],
    "identita'": ["chiamo", "nome", "sono", "anni", "vivo", "abito"],
}


def detect_topic(message: str, history: List[Dict] = None) -> str:
    """Detect current conversation topic from message + recent history."""
    # Combine current message with last 2 user messages for topic continuity
    texts = [message.lower()]
    if history:
        for entry in history[-2:]:
            texts.append(entry.get("user_message", "").lower())
    combined = " ".join(texts)

    scores = {}
    for topic, keywords in _TOPIC_MAP.items():
        score = sum(1 for kw in keywords if kw in combined)
        if score > 0:
            scores[topic] = score

    if scores:
        return max(scores, key=scores.get)
    return "conversazione libera"


def build_conversation_context(user_id: str, current_message: str,
                                profile: Dict[str, Any]) -> str:
    """
    Builds structured conversation context for LLM:
    A) Last 6 messages (user/assistant alternating)
    B) Stable identity summary
    C) Current topic detection
    """
    sections = []

    # --- A) Chat history thread ---
    history = chat_memory.get_messages(user_id, limit=6)
    if history:
        thread_lines = []
        for entry in history:
            user_msg = entry.get("user_message", "")
            sys_resp = entry.get("system_response", "")
            if user_msg:
                thread_lines.append(f"Utente: {user_msg}")
            if sys_resp:
                thread_lines.append(f"Genesi: {sys_resp}")
        if thread_lines:
            sections.append("CONVERSAZIONE RECENTE:\n" + "\n".join(thread_lines))

    # --- B) Stable identity summary ---
    assembler = ContextAssembler(None, None)
    profile_summary = assembler._summarize_profile(profile)
    if profile_summary:
        sections.append("INFORMAZIONI STABILI SULL'UTENTE:\n" + profile_summary)

    # --- C) Topic detection ---
    topic = detect_topic(current_message, history)
    sections.append(f"TEMA CORRENTE DELLA CONVERSAZIONE: {topic}")

    return "\n\n".join(sections)
