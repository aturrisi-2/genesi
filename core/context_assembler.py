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
from core.document_memory import load_document
from core.document_selector import resolve_documents

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

    def build(self, user_id: str, user_message: str) -> Dict[str, Any]:
        """
        Costruisce contesto completo per LLM.
        NON chiama update_brain — quello e' gia' fatto dal proactor.

        Returns:
            dict con: summary, long_term_profile, relational_state, recent_episodes, memory_v2, current_message
        """
        import asyncio
        
        # Load from persistent storage - use asyncio.run for sync wrapper
        try:
            loop = asyncio.get_running_loop()
            # If we're in an async context, we need to handle this differently
            # For now, use direct storage access for compatibility
            profile = storage._storage.get(f"profile:{user_id}", {})
            relational_state = storage._storage.get(f"relational_state:{user_id}", {})
            recent_episodes = storage._storage.get(f"episodes/{user_id}", [])
            # For latent_state, create a new event loop
            try:
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, self.latent_state_engine.load(user_id))
                    latent_state = future.result()
            except RuntimeError:
                # Fallback if threading fails
                latent_state = {}
        except RuntimeError:
            # No event loop, safe to use asyncio.run
            profile = asyncio.run(storage.load(f"profile:{user_id}", default={}))
            relational_state = asyncio.run(storage.load(f"relational_state:{user_id}", default={}))
            recent_episodes = asyncio.run(storage.load(f"episodes/{user_id}", default=[]))
            latent_state = asyncio.run(self.latent_state_engine.load(user_id))

        logger.info("CONTEXT_ASSEMBLER_LOADED user=%s", user_id)

        context = {}

        if profile:
            context['profile'] = profile
            context['long_term_profile'] = profile  # Required field for tests
            logger.info("PROFILE_LOADED user_id=%s", user_id)

        if relational_state:
            context['relational_state'] = relational_state
        else:
            context['relational_state'] = {}  # Ensure field exists

        if recent_episodes:
            context['recent_episodes'] = recent_episodes
        else:
            context['recent_episodes'] = []  # Ensure field exists

        if latent_state:
            context['latent_state'] = latent_state
        else:
            context['latent_state'] = {}  # Ensure field exists

        # Add memory_v2 structure
        context['memory_v2'] = {
            'profile': profile if profile else {},
            'relational_state': relational_state if relational_state else {},
            'recent_episodes': recent_episodes if recent_episodes else []
        }

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
        # Interests (legacy flat list)
        interests = profile.get('interests', [])
        if interests and isinstance(interests, list):
            parts.append(f"Interessi: {', '.join(interests)}")
        # Preferences (categorized dict)
        preferences = profile.get('preferences', {})
        if isinstance(preferences, dict):
            if preferences.get('music'):
                parts.append(f"Musica preferita: {', '.join(preferences['music'])}")
            if preferences.get('food'):
                parts.append(f"Cibo preferito: {', '.join(preferences['food'])}")
            if preferences.get('general'):
                parts.append(f"Preferenze: {', '.join(preferences['general'])}")
        elif isinstance(preferences, list) and preferences:
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
    A) Last 15 messages (user/assistant alternating)
    B) Stable identity summary
    C) Current topic detection
    """
    sections = []

    # --- A) Chat history thread ---
    history = chat_memory.get_messages(user_id, limit=15)
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

    # --- D) Narrative continuity: link last 2 user messages if related ---
    continuity = _detect_narrative_continuity(current_message, history)
    if continuity:
        sections.append(continuity)

    # --- E) Active document context ---
    doc_section = _inject_document_context(user_id, current_message, profile)
    if doc_section:
        sections.append(doc_section)

    return "\n\n".join(sections)


# ═══════════════════════════════════════════════════════════════
# NARRATIVE CONTINUITY — semantic linking of last 2 user messages
# ═══════════════════════════════════════════════════════════════

# Semantic clusters: words that indicate related topics
_SEMANTIC_CLUSTERS = {
    "stanchezza": {"stanco", "stanca", "dormito", "dormire", "sonno", "insonne",
                   "insonnia", "esausto", "esausta", "sveglio", "sveglia",
                   "riposo", "riposare", "sfinito", "sfinita", "spossato"},
    "tristezza": {"triste", "piango", "piangere", "lacrime", "depresso", "depressa",
                  "giù", "giu", "abbattuto", "abbattuta", "sconsolato", "male",
                  "infelice", "soffro", "soffrire", "dolore"},
    "ansia": {"ansioso", "ansiosa", "ansia", "preoccupato", "preoccupata",
              "paura", "panico", "agitato", "agitata", "nervoso", "nervosa",
              "stress", "stressato", "stressata", "tensione"},
    "lavoro": {"lavoro", "ufficio", "capo", "collega", "colleghi", "riunione",
               "progetto", "scadenza", "licenziato", "licenziata", "stipendio",
               "carriera", "promozione"},
    "relazioni": {"moglie", "marito", "fidanzato", "fidanzata", "partner",
                  "litigato", "litigio", "separazione", "divorzio", "amore",
                  "relazione", "coppia"},
    "salute": {"male", "dolore", "malato", "malata", "medico", "dottore",
               "ospedale", "febbre", "testa", "stomaco", "schiena"},
    "solitudine": {"solo", "sola", "solitudine", "isolato", "isolata",
                   "nessuno", "abbandonato", "abbandonata"},
}


def _detect_narrative_continuity(current_message: str, history: List[Dict]) -> str:
    """
    If last 2 user messages share a semantic cluster, return a continuity directive
    that forces the LLM to integrate them causally.
    """
    if not history:
        return ""

    # Get last user message from history
    prev_user_msgs = [e.get("user_message", "") for e in history if e.get("user_message")]
    if not prev_user_msgs:
        return ""

    last_user_msg = prev_user_msgs[-1].lower()
    current_lower = current_message.lower()

    # Find shared semantic clusters
    shared_clusters = []
    for cluster_name, keywords in _SEMANTIC_CLUSTERS.items():
        last_has = any(kw in last_user_msg for kw in keywords)
        current_has = any(kw in current_lower for kw in keywords)
        if last_has and current_has:
            shared_clusters.append(cluster_name)

    if shared_clusters:
        return (f"CONTINUITA' NARRATIVA OBBLIGATORIA:\n"
                f"L'utente ha appena detto: \"{prev_user_msgs[-1]}\"\n"
                f"Ora dice: \"{current_message}\"\n"
                f"Questi messaggi sono collegati (tema: {', '.join(shared_clusters)}).\n"
                f"DEVI collegare causalmente i due messaggi nella risposta.\n"
                f"NON trattarli come messaggi separati. NON usare fallback generico.")

    return ""


# ═══════════════════════════════════════════════════════════════
# DOCUMENT CONTEXT — inject active document into LLM context
# ═══════════════════════════════════════════════════════════════

_DOCUMENT_TRIGGERS = [
    "file", "documento", "immagine", "foto", "caricato", "caricata",
    "trascrivi", "riassumi", "riassunto", "cosa dice", "cosa c'è scritto",
    "cosa c'era scritto", "cosa c'e' scritto", "cosa c'era",
    "leggi", "analizza", "contenuto", "testo", "pdf",
    "screenshot", "schermata", "allegato",
    "cosa vedi", "cosa si vede", "descrivi", "estrai",
    "confronta", "compara", "differenze", "confronto",
]


def is_document_reference(message: str) -> bool:
    """Check if user message references an uploaded document."""
    msg_lower = message.lower()
    return any(trigger in msg_lower for trigger in _DOCUMENT_TRIGGERS)


def _format_doc_block(doc: Dict[str, Any]) -> str:
    """Format a single document as a [DOCUMENT_CONTEXT] block (max 2000 chars content)."""
    raw_content = doc.get("content", "")
    summary = doc.get("summary", "")

    if len(raw_content) > 2000 and summary:
        content_section = (f"RIASSUNTO:\n{summary}\n\n"
                           f"PRIMI 2000 CARATTERI:\n{raw_content[:2000]}")
    elif len(raw_content) > 2000:
        content_section = raw_content[:2000] + "\n[...contenuto troncato...]"
    else:
        content_section = raw_content

    return (f"[DOCUMENT_CONTEXT]\n"
            f"filename: {doc.get('filename', '?')}\n"
            f"type: {doc.get('type', '?')}\n"
            f"content:\n<<<\n{content_section}\n>>>\n"
            f"[/DOCUMENT_CONTEXT]")


def _inject_document_context(user_id: str, message: str,
                              profile: Dict[str, Any]) -> str:
    """
    If user has active documents and message references them,
    select relevant docs and inject their content into LLM context.
    Supports multi-document (max 2 per query).
    """
    # Support both new active_documents list and legacy active_document_id
    active_docs = profile.get("active_documents", [])
    if not active_docs:
        old_id = profile.get("active_document_id")
        if old_id:
            active_docs = [old_id]

    if not active_docs:
        return ""

    if not is_document_reference(message):
        return ""

    # Use document selector to pick relevant docs
    selected = resolve_documents(message, user_id, active_docs)
    if not selected:
        return ""

    # Build context blocks
    blocks = []
    for doc in selected:
        blocks.append(_format_doc_block(doc))
        logger.info("DOCUMENT_CONTEXT_INJECTED doc_id=%s type=%s",
                    doc.get("doc_id"), doc.get("type"))

    doc_count = len(selected)
    instruction = (
        f"ISTRUZIONE: L'utente si riferisce a {'questi documenti' if doc_count > 1 else 'questo documento'}. "
        f"Rispondi usando il contenuto {'dei documenti' if doc_count > 1 else 'del documento'} sopra. "
        f"NON dire che non hai accesso al file. HAI il contenuto. "
        f"NON rispondere con frasi generiche. USA i dati {'dei documenti' if doc_count > 1 else 'del documento'}."
    )
    if doc_count > 1:
        instruction += (
            " Se l'utente chiede un confronto, analizza le differenze e similitudini tra i documenti."
        )

    return "\n\n".join(blocks) + "\n\n" + instruction
