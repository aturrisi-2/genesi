"""PROACTOR v4.1 - Genesi Cognitive System (cost_optimized_v1)
Orchestratore centrale deterministico. GPT e' uno strumento subordinato.
Default model: gpt-4o-mini. Claude Opus solo per deep analysis.

Routing obbligatorio:
    INPUT -> Intent Classifier -> Proactor Decision Engine
        |-- Identity Router   (deterministico, zero GPT)
        |-- Tool Router       (deterministico, zero GPT su errore)
        |-- Relational Router  (ContextAssembler + EmotionalIntensity + GPT controllato)
        +-- Knowledge Router   (GPT senza contaminazione relazionale)

GPT chiamato SOLO da Relational Router o Knowledge Router.
"""

import logging
import re
import json
from typing import Dict, Any, Optional, List, Tuple, Union
from datetime import datetime, timedelta
from core.log import log
from core.memory_brain import memory_brain
from core.latent_state import latent_state_engine
from core.drift_modulator import drift_modulator
from core.curiosity_engine import curiosity_engine
from core.emotional_intensity_engine import emotional_intensity_engine
from core.tool_services import tool_service
from core.storage import storage
from core.context_assembler import ContextAssembler, build_conversation_context, is_document_reference
from core.llm_service import llm_service, model_selector, LLM_DEFAULT_MODEL
from core.fallback_knowledge import lookup_fallback
from core.identity_service import handle_identity_question
from core.response_filter import filter_response
from core.tool_context import (save_tool_context, resolve_elliptical_city,
                               is_elliptical_weather_followup,
                               is_elliptical_news_followup, resolve_elliptical_news,
                               resolve_inherited_intent)
from core.chat_memory import chat_memory
from core.intent_classifier import intent_classifier
from core.reminder_engine import reminder_engine
from core.document_context_manager import get_document_context_manager
from core.image_search_service import get_image_search_service, extract_image_query
from core.bedrock_image_service import bedrock_image_service
import unidecode
import os
import asyncio
import random
import pytz
from core.time_awareness import get_time_context, get_formatted_time
from core.weight_tracker import weight_tracker

logger = logging.getLogger(__name__)

logger.info("ARCHITECTURE_MODE=production_hardened_v2")
logger.info("PRIMARY_MODEL=gpt-4o")
logger.info("FALLBACK_MODEL=gpt-4o-mini")
logger.info("ARCHITECTURE_MODE=cost_optimized_v1")


# ═══════════════════════════════════════════════════════════════
# DETERMINISTIC DETECTORS — zero GPT, puro matching
# ═══════════════════════════════════════════════════════════════

IDENTITY_TRIGGERS = [
    "come mi chiamo", "chi sono", "dove vivo", "dove abito",
    "che lavoro faccio", "che lavoro svolgo", "qual è il mio nome",
    "qual e' il mio nome", "il mio nome", "ricordi il mio nome",
    "sai come mi chiamo", "quanti anni ho", "cosa faccio",
    "sai dove vivo", "sai dove abito", "sai quanti anni ho",
    "quale è il mio nome", "quale e' il mio nome",
    "come si chiama mia moglie", "come si chiama mio marito",
    "come si chiama il mio cane", "come si chiama la mia gatta",
    "come si chiamano i miei figli",
    "cosa mi piace", "che musica mi piace", "quali sono i miei interessi",
    "quali sono le mie preferenze", "come sono", "che tipo di persona sono",
    "quale frutto mi piace", "cosa sai di me", "account collegati",
    "miei account", "quali account ho", "i miei account", "e icloud", "e google",
    # Domande su Genesi stessa
    "chi sei", "cosa sei", "descriviti", "presentati",
    "come ti chiami", "qual è il tuo nome", "chi è genesi",
]

RELATIONAL_TRIGGERS = [
    "mi sento", "sono triste", "sono depresso", "sto male",
    "sono felice", "sono arrabbiato", "ho paura", "mi fa male",
    "sono ansioso", "sono preoccupato", "mi manca", "sono stanco",
    "non ce la faccio", "mi sento solo", "mi sento sola",
    "sono in ansia", "mi sento inadeguato", "mi sento inadeguata",
    "sono nervoso", "sono nervosa", "mi sento vuoto", "mi sento vuota",
]

KNOWLEDGE_TRIGGERS = [
    "cos'è", "cos'e'", "cosa significa", "spiegami", "definisci",
    "come funziona", "che cos'è", "che cos'e'", "cosa vuol dire",
    "che capitale", "quanto e'", "quanto è",
]

# Intent che devono saltare completamente il relational router
SKIP_RELATIONAL_INTENTS = ["tecnica", "debug", "spiegazione"]


def is_identity_question(message: str) -> bool:
    """Rileva domande sull'identita' dell'utente. Deterministico, zero GPT."""
    msg_lower = message.lower().strip()
    if any(trigger in msg_lower for trigger in IDENTITY_TRIGGERS):
        return True
    
    # Elliptical follow-ups for accounts
    if msg_lower.startswith("e ") or msg_lower.startswith("invece "):
        return any(kw in msg_lower for kw in ["icloud", "google", "apple", "account", "calendario"])
    
    return False


def is_relational_message(message: str) -> bool:
    """Rileva messaggi con contenuto emotivo/relazionale esplicito."""
    msg_lower = message.lower().strip()
    return any(trigger in msg_lower for trigger in RELATIONAL_TRIGGERS)


def is_knowledge_question(message: str) -> bool:
    """Rileva domande di definizione/conoscenza."""
    msg_lower = message.lower().strip()
    return any(trigger in msg_lower for trigger in KNOWLEDGE_TRIGGERS)


def is_memory_reference(message: str) -> bool:
    """Rileva riferimenti alla memoria conversazionale precedente."""
    msg_lower = message.lower().strip()
    # Triggers più specifici per evitare collisioni con 'mi ricordi' (reminders)
    memory_triggers = [
        "cosa abbiamo detto", "cosa dicevamo", "di cosa abbiamo parlato",
        "ci siamo detti", "avevamo detto", "riferimento a prima",
        "parlato l'altra volta", "discusso ieri",
        "abbiamo parlato", "avevamo parlato", "l'altra volta",
        "discusso", "di cosa", "come mi chiamo",
        "sai cosa", "ricordi cosa", "prima", "ieri",
    ]
    
    # Se contiene "ricordi" ma NON contiene parole chiave di promemoria/impegni
    data_keywords = ["promemoria", "impegni", "appuntamenti", "cosa ho", "da fare", "calendario"]
    if any(m in msg_lower for m in ["ricordi", "ti ricordi", "mi ricordi", "ricordarmi"]):
        if not any(d in msg_lower for d in data_keywords):
            return True
            
    return any(trigger in msg_lower for trigger in memory_triggers)


def is_reminder_request(message: str) -> bool:
    """Rileva richieste di promemoria."""
    msg_lower = message.lower().strip()
    # Includiamo 'impegni' e 'cose da fare'
    reminder_triggers = [
        "ricordamelo", "ricordami", "promemoria", "appuntamento",
        "imposta promemoria", "imposta un promemoria", "metti un promemoria",
        "segna questo", "segna un impegno"
    ]
    return any(trigger in msg_lower for trigger in reminder_triggers)


def is_list_reminders_request(message: str) -> bool:
    """Rileva richieste di elenco promemoria."""
    msg_lower = message.lower().strip()
    list_triggers = [
        "quali appuntamenti", "cosa devo fare", "promemoria attivi",
        "i miei promemoria", "elenco promemoria", "lista appuntamenti",
        "cosa ho da fare", "appuntamenti oggi", "promemoria di oggi",
        "i miei impegni", "cosa ho domani", "programma di domani"
    ]
    return any(trigger in msg_lower for trigger in list_triggers)


class Proactor:
    """
    Proactor v4 — Decision Engine deterministico.
    GPT e' subordinato: chiamato SOLO da Relational Router o Knowledge Router.
    Identity e Tool sono 100% deterministici.
    """

    def __init__(self):
        self.latent_state_engine = latent_state_engine
        self.tool_intents = ["weather", "news", "time", "date"]
        self.context_assembler = ContextAssembler(memory_brain, latent_state_engine)
        self.last_reminder_per_user = {} # {user_id: {"text": str, "dt": datetime}}
        self._last_route_per_user: Dict[str, str] = {}  # {user_id: last_route}
        logger.info("PROACTOR_V4_ACTIVE routers=identity,tool,relational,knowledge default_model=%s", LLM_DEFAULT_MODEL)

    # ═══════════════════════════════════════════════════════════════
    # HANDLE — Entry point, routing obbligatorio
    # ═══════════════════════════════════════════════════════════════

    async def handle(self, user_id: str, message: str = None, intent: str = None, conversation_id: str = None) -> str:
        """
        Orchestrazione centrale v4.
        Returns: response_text (SOLO stringa - nessuna tupla, nessun dict)
        Ordine di routing:
            1. Identity Router  (deterministico)
            2. Tool Router      (deterministico)
            3. Knowledge Router (deterministico)
            4. Relational Router (deterministico)
        
        NOTE: user_id validation for empty values is handled in _handle_internal
        """
        result = await self._handle_internal(user_id, message, intent, conversation_id)
        # Handle nested tuples: ((response, source), source) -> response
        if isinstance(result, tuple):
            if len(result) == 2 and isinstance(result[0], tuple):
                # Nested tuple case
                response = result[0][0] if isinstance(result[0], tuple) else result[0]
            else:
                # Normal tuple case
                response = result[0]
        else:
            response = result
            
            # PROACTIVE CLOUD SUGGESTION (Fluid Onboarding)
            try:
                profile = await storage.load(f"profile:{user_id}", default={})
                rel_sum = await memory_brain.relational.get_state_summary(user_id)
                total_msgs = rel_sum.get("total_messages", 0)
                
                # Check if is admin for global credentials fallback
                from auth.config import ADMIN_EMAILS
                user_email = profile.get("email", "")
                is_admin = user_email in ADMIN_EMAILS
                
                # Suggest only if: 
                # 1. Early in the relationship (0 to 10 messages)
                # 2. No cloud user (for admin, check env too)
                has_icloud = profile.get("icloud_user") or (is_admin and os.environ.get("ICLOUD_USER"))
                from calendar_manager import calendar_manager
                has_google = profile.get("google_token") or (is_admin and calendar_manager._admin_google_service is not None)
                
                if total_msgs < 1 and not has_icloud and not has_google:
                    if not any(kw in response.lower() for kw in ["cloud", "icloud", "google", "calendar", "sincronizza", "collega"]):
                        # Suggest only on the very first message
                        if is_admin:
                            tip = "\n\n✨ *Benvenuto! Prima di iniziare, se vuoi posso aiutarti a sincronizzare i tuoi calendari. Basta dirmi 'collega account Google' o 'usa iCloud'.*"
                        else:
                            tip = "\n\n✨ *Benvenuto! Posso gestire i tuoi promemoria internamente o collegare il tuo account iCloud. Basta dirmi 'imposta iCloud' se vuoi sincronizzarli.*"
                        response += tip
            except Exception as e:
                logger.error(f"ONBOARDING_ERROR: {e}")
            
        return response

    def handle_response_only(self, user_id: str, message: str = None, intent: str = None, conversation_id: str = None) -> str:
        """
        New contract: returns only response_string.
        Uses asyncio.run() only if no event loop is active.
        Returns: response_text
        """
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            # Event loop is already running, we can't use asyncio.run()
            # This should not happen in normal synchronous contexts
            raise RuntimeError("Cannot call handle_response_only from within async context")
        except RuntimeError:
            # No event loop running, safe to use asyncio.run()
            response, _ = asyncio.run(self.handle(user_id, message, intent, conversation_id))
            return response
    
    async def _handle_internal(self, user_id: str, message: str = None, intent: str = None, conversation_id: str = None) -> tuple[str, str]:
        try:
            # STEP 0.4: Unified Calendar Command (/cal)
            if message.startswith("/cal"):
                log("ROUTING_DECISION", route="calendar_command", user_id=user_id)
                response = await self._handle_calendar_command(user_id, message)
                return response, "calendar"

            # STEP 0.5: Image Search detection (prima del routing normale)
            
            # STEP 1: SANITY CHECK
            if not user_id:
                raise ValueError("Proactor received empty user_id")
            
            # Compatibilità test: se message è None, user_id è in realtà il message
            if message is None:
                message = user_id
                user_id = "test_user"
            
            # Compatibilità test: se user_id è una domanda identity e message è un intent
            # significa che i test stanno usando la firma vecchia (message, intent, user_id)
            if is_identity_question(user_id) and message and intent:
                # Probabile firma vecchia: (message, intent, user_id)
                # In questo caso user_id è il message e message è l'intent
                real_message = user_id
                real_user_id = intent
                user_id = real_user_id
                message = real_message
                intent = None  # Reset intent per evitare confusione
            elif self._contains_identity_statement(user_id) and message and intent:
                # Pattern identity statement come "Mi chiamo Luca e vivo a Milano"
                real_message = user_id
                real_user_id = intent
                user_id = real_user_id
                message = real_message
                intent = None  # Reset intent per evitare confusione
            
            # STEP 0: PROFILE AUTO-UPDATE (PRIMA DI QUALSIASI ROUTING)
            await self._update_profile_from_message(user_id, message)

            msg_lower = message.lower().strip()

            logger.info("PROACTOR_HANDLE_ENTRY user=%s intent=%s", user_id, intent)

            # STEP 0.5: IMAGE SEARCH ROUTE (web images) — priorità su richieste esplicite "cerca/mostra immagini"
            image_query = extract_image_query(message)
            if image_query:
                log("ROUTING_DECISION", route="image_search", user_id=user_id)
                response = await self._handle_image_search(user_id, image_query)
                return response, "tool"

            # STEP 1: IDENTITY ROUTE (PRIMA DI TUTTO - MASSIMA PRIORITÀ)
            if is_identity_question(message):
                log("ROUTING_DECISION", route="identity", user_id=user_id)
                logger.info("IDENTITY_ROUTE_EXECUTION_ORDER_OK user=%s", user_id)
                profile = await storage.load(f"profile:{user_id}", default={})
                brain_state_identity = {"profile": profile}
                response = await self._handle_identity(user_id, message, brain_state_identity)
                return response, "identity"

            # Load profile for other routing (non-identity)
            profile = await storage.load(f"profile:{user_id}", default={})

            # STEP 3: MEMORY UPDATE
            brain_state = await memory_brain.update_brain(user_id, message)
            if brain_state is None:
                brain_state = {"profile": {}, "latent": {}, "relational": {}}
            logger.info("PROACTOR_MEMORY_UPDATED user=%s profile_name=%s trust=%.3f episodes=%d",
                        user_id,
                        brain_state.get('profile', {}).get('name', 'unknown'),
                        brain_state.get('relational', {}).get('trust', 0),
                        len(brain_state.get('episodes', [])))

            # Load the profile from persistent storage
            # (profile già caricato sopra per non-identity)

            # Use the profile in the context assembly
            context = await self.context_assembler.build(user_id, message)
            context['profile'] = profile

            # STEP 3.5: ELLIPTICAL TOOL FOLLOW-UP (e.g. "e domani?" after weather)
            if is_elliptical_weather_followup(msg_lower):
                resolved_city = resolve_elliptical_city(user_id, msg_lower)
                if resolved_city:
                    logger.info("ELLIPTICAL_WEATHER_FOLLOWUP user=%s city=%s", user_id, resolved_city)
                    enriched_msg = f"che tempo fa a {resolved_city} {message.strip('?').strip()}"
                    response = await self._handle_tool("weather", enriched_msg, user_id)
                    return response, "tool"

            # STEP 3.6: ELLIPTICAL NEWS FOLLOW-UP (e.g. "e di politica?" after news)
            if is_elliptical_news_followup(msg_lower):
                resolved_topic = resolve_elliptical_news(user_id, msg_lower)
                if resolved_topic:
                    logger.info("ELLIPTICAL_NEWS_FOLLOWUP user=%s topic=%s", user_id, resolved_topic)
                    enriched_msg = f"notizie {resolved_topic}"
                    response = await self._handle_tool("news", enriched_msg, user_id)
                    return response, "tool"

            # STEP 3.7: DOCUMENT MODE — override to document_query if active docs + reference
            active_docs = profile.get("active_documents", [])
            # Backward compat: migrate old active_document_id
            if not active_docs and profile.get("active_document_id"):
                active_docs = [profile["active_document_id"]]

            # NON intercettare se è una richiesta di image generation:
            # "immagine"/"foto" sono in _DOCUMENT_TRIGGERS ma in questo contesto
            # significano "genera", non "analizza il documento caricato".
            _IMAGE_GEN_PREFIXES = (
                "genera", "crea", "disegna", "dipingi", "illustra",
                "genera un", "genera una", "crea un", "crea una",
                "fa una foto", "voglio vedere",
            )
            _is_image_gen_request = any(msg_lower.startswith(p) for p in _IMAGE_GEN_PREFIXES)

            if active_docs and is_document_reference(message) and not _is_image_gen_request:
                logger.info("DOCUMENT_MODE_TRIGGERED user=%s doc_count=%d", user_id, len(active_docs))
                response = await self._handle_document_query(user_id, message, profile, brain_state, conversation_id)
                return response, "tool"

            # STEP 3.8: MEMORY ROUTING OVERRIDE — bypass classifier for memory references
            chat_count = chat_memory.get_message_count(user_id)
            if (chat_count > 0 or conversation_id) and is_memory_reference(message):
                logger.info("MEMORY_ROUTING_OVERRIDE user=%s chat_count=%d msg=%s", user_id, chat_count, message[:40])
                intent = "memory_context"

            # STEP 3.9: REMINDER ROUTING STRICT — SOLO per intent espliciti
            # RIMOSSO: routing basato su testo, ora SOLO intent classificati

            # STEP 4: INTENT CLASSIFICATION
            if intent is None:
                intents = await intent_classifier.classify_async(message, user_id)
            else:
                intents = [intent] if isinstance(intent, str) else intent
                
            if not intents:
                intents = ["chat_free"]
            
            # STEP 4.1: CONVERSATIONAL INTEGRATION FORCE
            # Ensures tool/technical responses are wrapped in Genesi's voice via Relational synthesis
            if intents and not any(i in ["chat_free", "relational", "emotional"] for i in intents):
                # Intents that require a human "wrap" according to user preferences
                integrate_intents = self.tool_intents + [
                    "reminder_create", "reminder_list", "reminder_delete", "reminder_update",
                    "tecnica", "debug", "spiegazione", "icloud_sync", "google_sync",
                    "calendar_sync_all"
                ]
                if any(i in integrate_intents for i in intents):
                    # Don't force relational for clarification prompts
                    if intents[0] not in ["ambiguous_weather", "ambiguous_tool"]:
                        intents.append("relational")
                        logger.info("PROACTOR_FORCE_RELATIONAL_INTEGRATION user=%s intents=%s", user_id, intents)

            if len(intents) == 1 and intents[0] == "ambiguous_weather":
                return random.choice([
                    "Di quale città vuoi il meteo?",
                    "Per quale posto ti serve la previsione?",
                    "Dove vuoi sapere il meteo?",
                    "Dimmi la città e ti dico subito il tempo.",
                ]), "tool"

            if len(intents) == 1 and intents[0] == "ambiguous_tool":
                # Se il messaggio parla di caricamento/configurazione/calendario, sii specifico
                msg_lower = message.lower()
                if any(kw in msg_lower for kw in ["calendario", "account", "collega", "configura", "setup", "calendari"]):
                    if "icloud" not in msg_lower and "google" not in msg_lower:
                        # Intelligence: Check if something is already configured
                        profile = await storage.load(f"profile:{user_id}", default={})
                        has_icloud = profile.get("icloud_user")
                        has_google = profile.get("google_token")

                        if has_icloud and not has_google:
                            return random.choice([
                                f"Hai già iCloud collegato ({has_icloud}). Vuoi sincronizzare quello o aggiungere anche Google?",
                                f"Il tuo iCloud ({has_icloud}) è già attivo. Aggiungi anche Google Calendar?",
                            ]), "tool"
                        elif has_google and not has_icloud:
                            return random.choice([
                                "Google Calendar è attivo. Vuoi aggiungere anche iCloud?",
                                "Hai già Google Calendar. Collego anche iCloud?",
                            ]), "tool"

                        return random.choice([
                            "Configuro il calendario? Posso usare Google o iCloud — quale preferisci?",
                            "Vuoi Google Calendar o iCloud? Dimmi tu.",
                        ]), "tool"

                return random.choice([
                    "Non ho capito bene. Stai pensando a un promemoria, al meteo, o qualcos'altro?",
                    "Puoi essere più preciso? Non sono sicuro di cosa vuoi fare.",
                    "Dimmi di più — cosa hai in mente?",
                ]), "tool"

            # Multi-intent execution state
            final_responses = []
            final_source = "relational" # Default to relational if no tools hit
            
            # STEP 4.5: LOOP THROUGH INTENTS
            # Grouping: process tools first, then one final terminal response if present
            # We skip terminal intents (chat_free, relational, etc) if there are multiple tools
            # unless it's a specific technical request.
            
            terminal_intents = ["chat_free", "relational", "tecnica", "debug", "spiegazione", "identity", "memory_context", "emotional", "memory_correction", "dove_sono"]
            
            processed_message = message # Keep track if we need to modify it or pass it through
            
            for current_intent in intents:
                current_response = None
                
                # STEP 4.6: INTENT INHERITANCE
                inherited = resolve_inherited_intent(user_id, processed_message, current_intent)
                if inherited:
                    logger.info("PROACTOR_INTENT_INHERITED user=%s classified=%s inherited=%s", user_id, current_intent, inherited)
                    current_intent = inherited

                # DISPATCHER
                if current_intent in self.tool_intents:
                    log("ROUTING_DECISION", route="tool", user_id=user_id, intent=current_intent)
                    current_response = await self._handle_tool(current_intent, processed_message, user_id)
                    final_source = "tool"

                elif current_intent == "memory_context":
                    log("ROUTING_DECISION", route="memory_context", user_id=user_id)
                    current_response = await self._handle_memory_context(user_id, processed_message, brain_state, conversation_id)
                    final_source = "tool"
                
                elif current_intent == "calendar_sync_all":
                    log("ROUTING_DECISION", route="calendar_sync_all", user_id=user_id)
                    current_response = await self._handle_calendar_sync_all(user_id, processed_message)
                    final_source = "tool"
                    
                elif current_intent == "icloud_setup":
                    log("ROUTING_DECISION", route="icloud_setup", user_id=user_id)
                    current_response = await self._handle_icloud_setup(user_id, processed_message)
                    final_source = "tool"
                
                elif current_intent == "icloud_sync":
                    log("ROUTING_DECISION", route="icloud_sync", user_id=user_id)
                    current_response = await self._handle_icloud_sync(user_id, processed_message)
                    final_source = "tool"

                elif current_intent == "google_setup":
                    log("ROUTING_DECISION", route="google_setup", user_id=user_id)
                    current_response = await self._handle_google_setup(user_id, processed_message)
                    final_source = "tool"

                elif current_intent == "google_sync":
                    log("ROUTING_DECISION", route="google_sync", user_id=user_id)
                    current_response = await self._handle_google_sync(user_id, processed_message)
                    final_source = "tool"

                elif current_intent == "reminder_create":
                    log("ROUTING_DECISION", route="reminder_create", user_id=user_id)
                    reminder_result = await self._handle_reminder_creation(user_id, processed_message)
                    # 3-tuple (text, "reminder", True) = domanda chiarificatrice → return immediato, senza synthesis
                    if isinstance(reminder_result, tuple) and len(reminder_result) >= 3 and reminder_result[2]:
                        return reminder_result[0], "reminder"
                    current_response = reminder_result[0] if isinstance(reminder_result, tuple) else reminder_result
                    final_source = "tool"
                
                elif current_intent == "reminder_list":
                    log("ROUTING_DECISION", route="reminder_list", user_id=user_id)
                    current_response = await self._handle_reminder_list(user_id, processed_message)
                    final_source = "tool"
                
                elif current_intent == "reminder_delete":
                    log("ROUTING_DECISION", route="reminder_delete", user_id=user_id)
                    current_response = await self._handle_reminder_delete(user_id, processed_message)
                    final_source = "tool"
                
                elif current_intent == "reminder_update":
                    log("ROUTING_DECISION", route="reminder_update", user_id=user_id)
                    current_response = await self._handle_reminder_update(user_id, processed_message)
                    final_source = "tool"

                elif current_intent == "image_generation":
                    log("ROUTING_DECISION", route="image_generation", user_id=user_id)
                    current_response = await self._handle_image_generation(user_id, processed_message)
                    final_source = "tool"

                elif current_intent == "spiegazione":
                    log("ROUTING_DECISION", route="explanation", user_id=user_id)
                    # "Awake" explanation prompt
                    conversation_ctx = build_conversation_context(user_id, processed_message, profile, conversation_id)
                    exp_prompt = f"""Sei Genesi. L'utente ti sta chiedendo una spiegazione sul tuo comportamento, ti sta correggendo o è frustrato perché non hai capito qualcosa.
                    
                    {conversation_ctx}
                    
                    REGOLE DI SPIEGAZIONE:
                    - Sii onesto, trasparente e "sveglio".
                    - Se hai sbagliato a capire un intento in precedenza, ammettilo (es. "Scusami, avevo confuso la tua richiesta di ricordi con un promemoria").
                    - Se c'è stato un problema tecnico (limiti API, quota), accennalo con garbo (es. "Ho avuto un rallentamento con i miei servizi esterni o un limite di quota").
                    - Spiega il tuo ragionamento attuale in modo che l'utente capisca che sei "presente".
                    - NESSUNA chiusura meccanica o scusa standardizzata. Sii umano.
                    - NON dire mai "Ci sono", "Ti ascolto" o frasi simili.
                    - Non essere robotico. Non scusarti come un chatbot ("Mi scuso per il disagio"). Scusati come un compagno ("Hai ragione, mi sono perso un attimo").
                    """
                    model = model_selector(processed_message, route="knowledge")
                    current_response = await llm_service._call_with_protection(
                        model, exp_prompt, processed_message, user_id=user_id, route="explanation"
                    )
                    final_source = "explanation"

                elif current_intent in SKIP_RELATIONAL_INTENTS:
                    # Knowledge/Technical Strict (tecnica, debug)
                    if self._should_override_to_relational(processed_message, user_id):
                        log("ROUTING_DECISION", route="relational_override", user_id=user_id)
                        current_response = await self._handle_relational(user_id, processed_message, brain_state, conversation_id)
                        final_source = "relational"
                    else:
                        log("ROUTING_DECISION", route="knowledge_strict", user_id=user_id)
                        current_response = await self._handle_knowledge(user_id, processed_message, conversation_id)
                        final_source = "knowledge"

                elif current_intent == "identity":
                    log("ROUTING_DECISION", route="identity", user_id=user_id)
                    current_response = await self._handle_identity(user_id, processed_message, brain_state)
                    final_source = "identity"

                elif current_intent == "memory_correction":
                    log("ROUTING_DECISION", route="memory_correction", user_id=user_id)
                    current_response = await self._handle_memory_correction(user_id, processed_message, brain_state)
                    final_source = "identity"

                elif current_intent == "dove_sono":
                    log("ROUTING_DECISION", route="dove_sono", user_id=user_id)
                    current_response = await self._handle_location(user_id, processed_message, brain_state)
                    final_source = "tool"

                elif current_intent == "emotional":
                    log("ROUTING_DECISION", route="emotional", user_id=user_id)
                    current_response = await self._handle_relational(user_id, processed_message, brain_state, conversation_id)
                    final_source = "relational"

                elif current_intent in ["chat_free", "relational"]:
                    # Default Relational
                    if len(intents) > 1 and final_responses:
                        # If we already have tool responses, maybe we don't need a full relational response 
                        # or we just need it to wrap everything up.
                        # For now, let's just let it execute to be safe.
                        pass
                    log("ROUTING_DECISION", route="relational", user_id=user_id)
                    current_response = await self._handle_relational(user_id, processed_message, brain_state, conversation_id)
                    final_source = "relational"

                if current_response:
                    # Clean response if it's a tuple (source leaked from inner handlers)
                    if isinstance(current_response, tuple):
                        current_response = current_response[0]

                    if current_response not in final_responses:
                        final_responses.append(current_response)

                    # Fire-and-forget: aggiorna peso sinaptico per questa route
                    self._last_route_per_user[user_id] = current_intent
                    asyncio.create_task(weight_tracker.record_success_async(user_id, current_intent))

                # If we have multiple hits, we stop at the first generic terminal intent
                # We allow multiple tools and technical intents to chain.
                if current_intent in ["chat_free", "relational"] and len(final_responses) > 0:
                    break
            
            if not final_responses:
                # Emergency fallback if no intent worked
                final_responses.append(await self._handle_relational(user_id, message, brain_state, conversation_id))
                final_source = "relational"

            # STEP 5: SYNTHESIS
            if len(final_responses) > 1:
                log("PROACTOR_SYNTHESIS_START", count=len(final_responses))
                synthesized = await self._synthesize_responses(user_id, message, final_responses)
                return synthesized, final_source

            return final_responses[0] if final_responses else "", final_source

        except Exception as e:
            logger.exception("PROACTOR_FATAL_ERROR user=%s intent=%s", user_id, intent, exc_info=True)
            if os.getenv('TEST_MODE', '0') == '1':
                raise
            try:
                profile = await memory_brain.semantic.get_profile(user_id)
                name = profile.get("name", "")
            except Exception:
                name = ""
            prefix = f"{name}, " if name else ""
            return f"{prefix}Mi dispiace, ho avuto un problema. Riprova tra poco.", "error"

    # ═══════════════════════════════════════════════════════════════
    # IDENTITY ROUTER — 100% deterministico, zero GPT
    # ═══════════════════════════════════════════════════════════════

    async def _handle_identity(self, user_id: str, message: str, brain_state: Dict[str, Any]) -> str:
        """
        Risponde a domande sull'identita' dell'utente in modo naturale tramite LLM.
        I dati del profilo vengono raccolti deterministicamente — zero hallucination.
        L'LLM produce solo la fraseggiatura, non inventa fatti.
        """
        profile = brain_state.get("profile", {})
        msg_lower = message.lower().strip()

        # AUTO-CLEAN CORRUPTED DATA (Guard against old bugs)
        _CORRUPTED_PROF_KW = [
            "account", "collega", "miei", "quali", "a cena", "a casa",
            "da mio", "da mia", "tempo", "fuori", "stanco", "stanca",
            "bene sono", "sono a", "sono in", "andato", "andata", "tornato",
            # Stato civile finito erroneamente in profession (bug parser LLM)
            "sposato", "sposata", "single", "celibe", "nubile", "divorziato", "divorziata",
            "vedovo", "vedova",
        ]
        prof = profile.get("profession", "")
        if prof and isinstance(prof, str) and (
            any(kw in prof.lower() for kw in _CORRUPTED_PROF_KW)
            or (prof.split() and prof.split()[0].lower() in {"a", "da", "con", "per", "di", "in"})
            or len(prof.split()) > 4
        ):
            logger.info("IDENTITY_AUTO_CLEAN corrupted_profession=%s", prof)
            profile["profession"] = None
            try:
                import asyncio
                asyncio.create_task(storage.save(f"profile:{user_id}", profile))
            except: pass

        # AUTO-CLEAN DUPLICATED CHILDREN/PETS (one-time repair for old data)
        _profile_dirty = False
        raw_children = profile.get("children", [])
        if isinstance(raw_children, list) and len(raw_children) > 1:
            seen_cn = set()
            deduped_children = []
            for c in raw_children:
                k = (c.get("name", "") if isinstance(c, dict) else str(c)).lower().strip()
                if k and k not in seen_cn:
                    seen_cn.add(k)
                    deduped_children.append(c)
            if len(deduped_children) != len(raw_children):
                logger.info("IDENTITY_AUTO_CLEAN children_dedup old=%d new=%d", len(raw_children), len(deduped_children))
                profile["children"] = deduped_children
                _profile_dirty = True

        raw_pets = profile.get("pets", [])
        if isinstance(raw_pets, list) and len(raw_pets) > 1:
            seen_pn = set()
            deduped_pets = []
            for p in raw_pets:
                k = (p.get("name", "") if isinstance(p, dict) else str(p)).lower().strip()
                if k and k not in seen_pn:
                    seen_pn.add(k)
                    deduped_pets.append(p)
            if len(deduped_pets) != len(raw_pets):
                logger.info("IDENTITY_AUTO_CLEAN pets_dedup old=%d new=%d", len(raw_pets), len(deduped_pets))
                profile["pets"] = deduped_pets
                _profile_dirty = True

        # AUTO-CLEAN TRAITS: rimuove valori professione finiti erroneamente in traits
        _PROF_KW_TRAITS = [
            "manager", "medico", "architetto", "ingegnere", "avvocato", "dottore",
            "comandante", "direttore", "tecnico", "analista", "developer", "programmer",
            "designer", "consulente", "construction", "project", "responsabile",
        ]
        raw_traits = profile.get("traits", [])
        if isinstance(raw_traits, list) and raw_traits:
            _current_prof = (profile.get("profession") or "").lower().strip()
            cleaned_traits = [
                t for t in raw_traits
                if isinstance(t, str)
                and not any(kw in t.lower() for kw in _PROF_KW_TRAITS)
                and t.lower().strip() != _current_prof
            ]
            if len(cleaned_traits) != len(raw_traits):
                logger.info("IDENTITY_AUTO_CLEAN traits old=%s new=%s", raw_traits, cleaned_traits)
                profile["traits"] = cleaned_traits
                _profile_dirty = True

        if _profile_dirty:
            try:
                asyncio.create_task(storage.save(f"profile:{user_id}", profile))
            except Exception: pass

        logger.info("IDENTITY_ROUTER user=%s profile=%s", user_id,
                     {k: v for k, v in profile.items() if k != "entities" and v})
        logger.info("MEMORY_DIRECT_RESPONSE user=%s route=identity", user_id)

        # Domanda su Genesi stessa (chi sei, cosa sei, presentati) — risposta LLM varia ogni volta
        _genesi_self_kw = ["chi sei", "cosa sei", "descriviti", "presentati", "come ti chiami", "chi è genesi",
                           "il tuo nome", "qual è il tuo", "come ti chiami"]
        if any(kw in msg_lower for kw in _genesi_self_kw):
            _name_str = profile.get("name", "")
            _ctx = f"L'utente si chiama {_name_str}. " if _name_str else ""
            _genesi_intro_prompt = (
                "Sei Genesi, un'assistente personale intelligente, calda, curiosa e con personalità. "
                f"{_ctx}"
                "L'utente ti ha chiesto chi sei o come ti chiami. "
                "Rispondi in modo naturale e VARIO — mai la stessa frase. "
                "Puoi essere ironica, calda, diretta o elaborare un po'. "
                "Non elencare le tue funzionalità come una lista. Parla come una persona. "
                "Rispondi in italiano, 1-3 frasi al massimo."
            )
            try:
                _intro_resp = await llm_service._call_with_protection(
                    "gpt-4o-mini", _genesi_intro_prompt, message, user_id=user_id, route="identity"
                )
                if _intro_resp and _intro_resp.strip():
                    return _intro_resp.strip()
            except Exception as _e:
                logger.warning("IDENTITY_INTRO_LLM_FALLBACK error=%s", _e)
            return "Sono Genesi — la tua assistente personale."

        # Domanda account collegati — resta deterministica (sicurezza, no LLM)
        if any(kw in msg_lower for kw in ["account collegati", "miei account", "quali account ho", "icloud", "google", "apple"]):
            linked = []
            from auth.config import ADMIN_EMAILS
            user_email = profile.get("email", "")
            is_admin = user_email in ADMIN_EMAILS

            if profile.get("icloud_user") or profile.get("icloud_verified"):
                email = profile.get("icloud_user") or "iCloud"
                linked.append(f"iCloud ({email})")
            elif is_admin and os.environ.get("ICLOUD_USER"):
                linked.append("iCloud (Admin)")

            from calendar_manager import calendar_manager
            if profile.get("google_token") or (is_admin and calendar_manager._admin_google_service):
                linked.append("Google Calendar")

            if not linked:
                return "Non hai ancora collegato alcun account. Puoi dirmi 'collega iCloud' o 'usa Google' per iniziare."
            return "Hai collegato i seguenti account: " + ", ".join(linked) + "."

        # Raccoglie fatti deterministici e genera risposta naturale via LLM
        profile_facts = self._collect_profile_facts(profile)
        try:
            system_prompt = self._build_identity_system_prompt(profile_facts)
            response = await llm_service._call_with_protection(
                "gpt-4o-mini", system_prompt, message, user_id=user_id, route="identity"
            )
            if response and response.strip():
                logger.info("IDENTITY_LLM_RESPONSE user=%s", user_id)
                return response.strip()
        except Exception as e:
            logger.warning("IDENTITY_LLM_FALLBACK error=%s", e)

        # Fallback deterministico
        return self._build_identity_response(profile)

    @staticmethod
    def _collect_profile_facts(profile: dict) -> dict:
        """Raccoglie fatti del profilo in modo deterministico per il prompt LLM."""
        children_raw = profile.get("children")  # None se campo mancante, [] se vuoto
        children_names = []
        _seen_children = set()
        if isinstance(children_raw, list):
            for c in children_raw:
                if isinstance(c, dict):
                    name = c.get("name", "")
                elif c:
                    name = str(c)
                else:
                    continue
                key = name.lower().strip()
                if key and key not in _seen_children:
                    _seen_children.add(key)
                    children_names.append(name)

        pets_raw = profile.get("pets", [])
        pet_descs = []
        _seen_pets = set()
        for pet in (pets_raw if isinstance(pets_raw, list) else []):
            if isinstance(pet, dict):
                pet_name = pet.get('name', '')
                key = pet_name.lower().strip()
                if key and key not in _seen_pets:
                    _seen_pets.add(key)
                    pet_descs.append(f"{pet_name} ({pet.get('type', '?')})")
            elif pet:
                key = str(pet).lower().strip()
                if key and key not in _seen_pets:
                    _seen_pets.add(key)
                    pet_descs.append(str(pet))

        return {
            "name": profile.get("name"),
            "city": profile.get("city"),
            "profession": profile.get("profession"),
            "age": profile.get("age"),
            "spouse": profile.get("spouse"),
            "children_names": children_names,
            "children_field_exists": children_raw is not None,
            "pets": pet_descs,
            "interests": profile.get("interests", []),
            "preferences": profile.get("preferences", []),
            "traits": profile.get("traits", []),
        }

    @staticmethod
    def _build_identity_system_prompt(facts: dict) -> str:
        """Costruisce il system prompt per risposta identità naturale via LLM."""
        lines = [
            "Sei Genesi, un'assistente personale intelligente, calda e curiosa.",
            "Stai rispondendo a una domanda dell'utente su se stesso o su informazioni che lo riguardano.",
            "Usa SOLO i dati elencati qui sotto — non inventare, non presumere, non aggiungere nulla.",
            "",
        ]
        known = []
        if facts.get("name"):
            known.append(f"Nome: {facts['name']}")
        if facts.get("city"):
            known.append(f"Città: {facts['city']}")
        if facts.get("profession"):
            known.append(f"Professione: {facts['profession']}")
        if facts.get("age"):
            known.append(f"Età: {facts['age']} anni")
        if facts.get("spouse"):
            known.append(f"Coniuge/partner: {facts['spouse']}")
        children = facts.get("children_names", [])
        if children:
            known.append(f"Figli: {', '.join(children)}")
        elif facts.get("children_field_exists"):
            known.append("Figli: nessuno registrato nel profilo")
        pets = facts.get("pets", [])
        if pets:
            known.append(f"Animali domestici: {', '.join(pets)}")
        interests = facts.get("interests", [])
        if interests:
            known.append(f"Interessi: {', '.join(interests)}")
        preferences = facts.get("preferences", [])
        if preferences:
            known.append(f"Preferenze: {', '.join(preferences)}")
        traits = facts.get("traits", [])
        if traits:
            known.append(f"Tratti: {', '.join(traits)}")

        if known:
            lines.append("Dati disponibili:")
            lines.extend(f"  - {k}" for k in known)
        else:
            lines.append("Non ci sono ancora dati su questa persona.")

        lines += [
            "",
            "Regole:",
            "- Rispondi in italiano in modo naturale, caldo e conciso.",
            "- NON usare formule robotiche come 'Ecco cosa so di te:' o 'Le informazioni che ho sono:'.",
            "- Se l'informazione richiesta non è nei dati, dillo con naturalezza (es: 'Non me lo hai ancora detto.').",
            "- Eccezione: se l'utente chiede 'cosa sai di me', 'dimmi tutto quello che sai', 'raccontami di me' "
            "→ dai un riassunto COMPLETO e fluente di TUTTI i dati disponibili sopra, in tono caldo.",
            "- In tutti gli altri casi, rispondi solo a quello che è stato chiesto, senza elencare tutto il profilo.",
            "- Varia il tuo stile — non rispondere sempre nello stesso modo.",
        ]
        return "\n".join(lines)

    @staticmethod
    def _build_identity_response(profile: dict) -> str:
        """Fallback deterministico per risposta identità."""
        parts = []
        name = profile.get("name")
        city = profile.get("city")
        profession = profile.get("profession")
        spouse = profile.get("spouse")
        pets = profile.get("pets", [])

        if pets and isinstance(pets, list):
            pet_descs = []
            for pet in pets:
                if isinstance(pet, dict):
                    pet_descs.append(f"{pet.get('name', '?')} ({pet.get('type', '?')})")
                else:
                    pet_descs.append(str(pet))
            if pet_descs:
                parts.append(f"hai {', '.join(pet_descs)}")

        if name:
            parts.append(f"ti chiami {name}")
        if city:
            parts.append(f"vivi a {city}")
        if profession:
            parts.append(f"lavori come {profession}")
        if spouse:
            parts.append(f"il tuo coniuge si chiama {spouse}")

        if not parts:
            return "Non mi hai ancora detto molto di te."
        return "So che " + ", ".join(parts) + "."

    # ═══════════════════════════════════════════════════════════════
    # MEMORY CORRECTION — Correzione di dati sbagliati nel profilo
    # ═══════════════════════════════════════════════════════════════

    async def _handle_memory_correction(self, user_id: str, message: str, brain_state: dict) -> str:
        """
        Aggiorna il profilo utente in base a quanto comunicato.
        Un solo LLM call: parsifica il campo E genera risposta umana.
        """
        import json as _json
        import re as _re
        from core.llm_service import llm_service

        profile = await storage.load(f"profile:{user_id}", default={})

        profile_summary = {
            "nome": profile.get("name"),
            "città": profile.get("city"),
            "professione": profile.get("profession"),
            "partner": profile.get("spouse"),
            "figli": [c.get("name") if isinstance(c, dict) else str(c) for c in profile.get("children", [])],
            "animali": [f"{p.get('type','?')} {p.get('name','?')}" for p in profile.get("pets", []) if isinstance(p, dict)],
            "interessi": profile.get("interests", []),
            "tratti": profile.get("traits", []),
        }

        parse_prompt = f"""Sei Genesi. L'utente ti sta comunicando qualcosa su di sé — aggiorna il profilo.

Profilo attuale: {_json.dumps(profile_summary, ensure_ascii=False)}
Messaggio: "{message}"

Rispondi SOLO con JSON valido su una riga:
{{"field":"...","action":"...","new_value":...,"old_value":...,"reply":"..."}}

CAMPI:
- name: nome dell'utente
- city: città di residenza
- profession: lavoro/professione attuale (NON lo stato civile)
- spouse: partner o coniuge ("non sono sposato" → clear spouse, non profession!)
- children: figli → new_value = lista di {{"name":"..."}}
- pets: animali → new_value = lista di {{"type":"cat|dog|bird|altro","name":"..."}}
- interests: hobby e interessi → lista di stringhe
- traits: caratteristiche personali → lista di stringhe

AZIONI: "update" (sostituisce), "delete" (rimuove elemento da lista), "clear" (svuota campo)

REPLY: Una sola frase breve e naturale — come direbbe un amico che ti conosce bene.
Varia ogni volta, non ripetere sempre la stessa. NON usare mai parole come "salvato", "cancellato", "aggiornato", "rimosso", "registrato".
Stile giusto: "Ok, lo tengo a mente!", "Capito!", "Ah, buono a sapersi.", "Perfetto.", "Certo, ci penso io.", "Fatto.", "Me lo segno.", "Lo sapevo che l'avevo sbagliata!", "Grazie per dirmelo.", "Ottimo, ora lo so."

ESEMPI:
- "non sono un architetto, sono un medico" → {{"field":"profession","action":"update","new_value":"medico","old_value":"architetto","reply":"Ah, medico! Lo tengo a mente."}}
- "non sono sposato" → {{"field":"spouse","action":"clear","new_value":null,"old_value":null,"reply":"Capito, me lo segno."}}
- "ho due figli, Ennio e Zoe" → {{"field":"children","action":"update","new_value":[{{"name":"Ennio"}},{{"name":"Zoe"}}],"old_value":null,"reply":"Ennio e Zoe, bello!"}}
- "ho un cane Rio e due gatti Mignolo e Prof" → {{"field":"pets","action":"update","new_value":[{{"type":"dog","name":"Rio"}},{{"type":"cat","name":"Mignolo"}},{{"type":"cat","name":"Prof"}}],"old_value":null,"reply":"Rio, Mignolo e Prof — che bella famiglia!"}}
- Se non capisci → {{"field":null,"action":null,"new_value":null,"old_value":null,"reply":"Non ho capito — puoi dirmi meglio cosa cambiare?"}}"""

        correction = {}
        reply_fallback = "Non ho capito — puoi dirmi più chiaramente cosa cambiare?"
        try:
            result_str = await llm_service._call_with_protection(
                model="gpt-4o-mini", prompt=parse_prompt,
                message=message, user_id=user_id, route="memory_correction"
            )
            m = _re.search(r'\{.*\}', result_str or "", _re.DOTALL)
            if m:
                correction = _json.loads(m.group(0))
        except Exception as ex:
            logger.error("MEMORY_CORRECTION_PARSE_ERROR user=%s err=%s", user_id, ex)
            return reply_fallback

        field = correction.get("field")
        action = correction.get("action")
        new_value = correction.get("new_value")
        natural_reply = (correction.get("reply") or reply_fallback).strip()

        if not field or not action:
            return natural_reply

        # Sanitizza: pets e children devono essere lista di dict (sicurezza contro LLM che restituisce stringhe)
        if field == "pets" and action == "update" and isinstance(new_value, list):
            sanitized = []
            for item in new_value:
                if isinstance(item, dict) and "name" in item:
                    sanitized.append({"type": item.get("type", "?"), "name": item["name"]})
                elif isinstance(item, str) and item.strip():
                    parts = item.strip().split(" ", 1)
                    sanitized.append({"type": parts[0], "name": parts[1]} if len(parts) == 2 else {"type": "?", "name": item})
            new_value = sanitized

        if field == "children" and action == "update" and isinstance(new_value, list):
            new_value = [
                item if isinstance(item, dict) and "name" in item else {"name": str(item)}
                for item in new_value if item
            ]

        # Applica la correzione
        if action == "update":
            profile[field] = new_value
        elif action == "clear":
            profile[field] = [] if field in ("children", "pets", "interests", "traits") else None
        elif action == "delete" and isinstance(profile.get(field), list):
            profile[field] = [
                x for x in profile[field]
                if (x.get("name", "") if isinstance(x, dict) else str(x)).lower() != str(new_value or "").lower()
            ]

        # Se abbiamo aggiornato la professione, rimuovila da traits se c'era finita per bug
        if field == "profession" and action in ("update", "clear"):
            raw_traits = profile.get("traits", [])
            if raw_traits:
                _pv = str(new_value or "").lower().strip()
                cleaned = [t for t in raw_traits if not _pv or t.lower().strip() != _pv]
                if len(cleaned) != len(raw_traits):
                    profile["traits"] = cleaned
                    logger.info("MEMORY_CORRECTION_TRAITS_CLEAN removed=%s from traits", new_value)

        await storage.save(f"profile:{user_id}", profile)
        log("MEMORY_CORRECTION_APPLIED", user_id=user_id, field=field, action=action, new_value=new_value)

        return natural_reply

    # ═══════════════════════════════════════════════════════════════
    # LOCATION — Dove sono: GPS + ora locale + momento del giorno
    # ═══════════════════════════════════════════════════════════════

    async def _handle_location(self, user_id: str, message: str, brain_state: dict) -> str:
        """
        Risposta contestuale sulla posizione dell'utente.
        Usa GPS e timezone dal profilo. Zero LLM, 100% deterministico.
        """
        import pytz
        from datetime import datetime

        profile = brain_state.get("profile", {})
        city = profile.get("city")
        tz_name = profile.get("timezone", "Europe/Rome")
        gps_lat = profile.get("gps_lat")
        gps_lon = profile.get("gps_lon")

        if not city and not gps_lat:
            return "Non ho la tua posizione. Apri l'app e permetti l'accesso alla posizione così posso aiutarti meglio."

        # Ora locale
        try:
            tz = pytz.timezone(tz_name)
            now_local = datetime.now(tz)
        except Exception:
            now_local = datetime.now()

        hour = now_local.hour
        time_str = now_local.strftime("%H:%M")

        # Momento del giorno + pool di frasi contestuali variate
        _ctx_pool = {
            "mattina presto": ["Inizio giornata!", "Già sveglio a quest'ora?", "Buona partenza.", "Si parte!"],
            "mattina": ["Buona mattinata!", "Come inizia la giornata?", "Bella mattina.", "In piena forma?"],
            "mezzogiorno": ["Quasi l'ora di pranzo.", "Hai già mangiato?", "Pausa pranzo?", "È mezzogiorno."],
            "pomeriggio": ["Buon pomeriggio!", "Come va il pomeriggio?", "Stai lavorando?", "Pomeriggio in pieno."],
            "sera": ["Bella serata!", "Come è andata oggi?", "Stai riposando?", "Serata tranquilla?"],
            "sera tardi": ["È tardi — prenditi cura di te.", "Non andare a letto troppo tardi.", "Già così tardi?", "Domani si ricomincia."],
            "notte": ["Sei sveglio di notte?", "Non dormi?", "Tutto ok a quest'ora?", "Nottambulo!"],
        }

        if 5 <= hour < 9:
            moment = "mattina presto"
        elif 9 <= hour < 12:
            moment = "mattina"
        elif 12 <= hour < 14:
            moment = "mezzogiorno"
        elif 14 <= hour < 18:
            moment = "pomeriggio"
        elif 18 <= hour < 21:
            moment = "sera"
        elif 21 <= hour < 24:
            moment = "sera tardi"
        else:
            moment = "notte"

        context = random.choice(_ctx_pool[moment])
        city_str = city.strip().title() if city else "la tua ultima posizione nota"
        log("LOCATION_RESPONSE", user_id=user_id, city=city_str, hour=hour, moment=moment)
        return f"Sei a {city_str}. Sono le {time_str} — {moment}. {context}"

    # ═══════════════════════════════════════════════════════════════
    # TOOL ROUTER — 100% deterministico, zero GPT su errore
    # ═══════════════════════════════════════════════════════════════

    async def _handle_tool(self, intent: str, message: str, user_id: str) -> str:
        """
        Tool routing deterministico.
        Errori gestiti con messaggi deterministici, MAI GPT.
        Returns: (response_text: str, source: str)
        """
        try:
            if intent == "weather":
                result = await tool_service.get_weather(message, user_id)
                # Save tool context for follow-up
                from core.location_resolver import extract_city_from_message
                city = extract_city_from_message(message) or "Roma"
                save_tool_context(user_id, "weather", city=city)
                logger.info("TOOL_ROUTER_OK intent=weather user=%s city=%s", user_id, city)
                return result, "tool"
            elif intent == "news":
                result = await tool_service.get_news(message)
                save_tool_context(user_id, "news")
                logger.info("TOOL_ROUTER_OK intent=news user=%s", user_id)
                return result, "tool"
            elif intent == "time":
                result = await tool_service.get_time()
                return result, "tool"
            elif intent == "date":
                result = await tool_service.get_date()
                return result, "tool"
            else:
                return "Tool non disponibile.", "tool"
        except Exception as e:
            logger.error("PROACTOR_TOOL_ERROR intent=%s user=%s error=%s", intent, user_id, str(e), exc_info=True)
            if intent == "weather":
                return "Il servizio meteo non è disponibile al momento.", "tool"
            elif intent == "news":
                return "Il servizio notizie non è configurato correttamente.", "tool"
            return f"Errore nel servizio {intent}.", "tool"

    # ═══════════════════════════════════════════════════════════
    # MEMORY CONTEXT ROUTER — conversational memory responses
    # ═══════════════════════════════════════════════════════════

    async def _handle_memory_context(self, user_id: str, message: str, brain_state: Dict[str, Any], conversation_id: str = None) -> tuple[str, str]:
        """
        Handle memory_context intent — responses based on conversation history.
        Loads last N interactions, summarizes dynamically, responds naturally.
        Never responds with "non posso aiutarti".
        Returns: (response_text: str, source: str)
        """
        try:
            # Load last interactions from specific conversation if provided
            messages = []
            if conversation_id:
                try:
                    from api.conversations import _load_conv
                    conv = _load_conv(user_id, conversation_id)
                    if conv and "messages" in conv:
                        raw_msgs = conv["messages"]
                        current_pair = {}
                        for m in raw_msgs:
                            role = m.get("role")
                            content = m.get("content", "")
                            if role == "user":
                                if current_pair.get("user_message"):
                                    messages.append(current_pair)
                                    current_pair = {}
                                current_pair["user_message"] = content
                            elif role in ("assistant", "genesi", "system", "model") and current_pair.get("user_message"):
                                current_pair["system_response"] = content
                                messages.append(current_pair)
                                current_pair = {}
                        # Keep last 10 for better context
                        messages = messages[-10:]
                except Exception as e:
                    logger.error("Failed to load conversation history for memory_context: %s", str(e))
                
            if not messages:
                # Fallback to volatile memory
                messages = chat_memory.get_messages(user_id, limit=5)
                
            if not messages:
                logger.warning("MEMORY_CONTEXT_NO_HISTORY user=%s", user_id)
                return "Non abbiamo ancora parlato abbastanza. Di cosa vorresti conversare?", "memory_context"
            
            # Build conversation summary
            conversation_summary = []
            for msg in messages:
                user_msg = msg.get("user_message", "")
                sys_msg = msg.get("system_response", "")
                if user_msg and sys_msg:
                    conversation_summary.append(f"Tu: {user_msg}\nIo: {sys_msg}")
            
            summary_text = "\n\n".join(conversation_summary)
            
            # Build memory-aware prompt
            memory_prompt = f"""Basandoti sulla nostra conversazione recente:

{summary_text}

L'utente ora chiede: "{message}"

Rispondi in modo naturale facendo riferimento ai nostri scambi precedenti quando pertinente.
Non aggiungere frasi fatte o conferme robotiche all'inizio o alla fine, la conversazione deve sembrare fluida e naturale.
Sii coerente con quanto abbiamo detto. Non dire che non puoi aiutare."""

            # Use LLM for natural response
            model = model_selector(message, route="memory")
            response = await llm_service._call_with_protection(
                model, memory_prompt, message, user_id=user_id, route="memory"
            )
            
            if response is None:
                # Fallback: simple acknowledgment
                return "Ricordo i nostri scambi. C'è qualcosa di specifico che vorresti approfondire?", "memory_context"
            
            logger.info("MEMORY_CONTEXT_RESPONSE user=%s history_count=%d", user_id, len(messages))
            return response, "memory_context"
            
        except Exception as e:
            logger.error("MEMORY_CONTEXT_ERROR user=%s error=%s", user_id, str(e), exc_info=True)
            return "Mi dispiace, ho avuto un problema nel recuperare i nostri ricordi. Riprova.", "memory_context"

    # ═══════════════════════════════════════════════════════════
    # REMINDER HANDLERS — deterministic reminder management
    # ═══════════════════════════════════════════════════════════

    # Parole trigger che da sole non costituiscono il contenuto del promemoria
    _REMINDER_TRIGGER_ONLY = {
        "ricordami", "promemoria", "memorizza", "segna", "appuntamento",
        "evento", "reminder", "ricorda", "nota", "annota",
    }
    # Frasi multi-parola che sono comandi/trigger, non contenuto dell'evento
    _REMINDER_TRIGGER_PHRASES = [
        "imposta una sveglia", "imposta sveglia", "metti sveglia", "metti una sveglia",
        "aggiungi un promemoria", "crea un promemoria", "aggiungi promemoria",
        "segna un appuntamento", "crea un appuntamento", "metti un appuntamento",
        "aggiungi un appuntamento", "metti nel calendario", "aggiungi al calendario",
        "segna nel calendario", "metti in agenda", "aggiungi in agenda",
    ]

    async def _handle_reminder_creation(self, user_id: str, message: str) -> str:
        """
        Handle reminder creation requests with STRICT logic.
        Se il contenuto è mancante chiede "cosa devo ricordarti?".
        Scrive sempre su entrambi i calendari (Google + iCloud) simultaneamente.
        """
        try:
            # 1. TENTA PARSING DETERMINISTICO (STRICT)
            reminder_text, reminder_datetime = self._parse_reminder_request_strict(message)

            # 2. FALLBACK A PARSING NATURALE SE MANCANO DATI
            if not reminder_text or not reminder_datetime:
                logger.info("FALLBACK_NATURAL_PARSING message=%s", message)
                reminder_text, reminder_datetime = await self._parse_reminder_natural(message, user_id)

            # 3. Se il testo è solo una parola-trigger o frase-trigger, azzeralo
            if reminder_text:
                _text_low = reminder_text.lower().strip()
                if (_text_low in self._REMINDER_TRIGGER_ONLY or
                        any(phrase in _text_low for phrase in self._REMINDER_TRIGGER_PHRASES)):
                    reminder_text = None

            # 4. Se manca il CONTENUTO → chiedi prima cosa ricordare
            if not reminder_text:
                return "Certo! Cosa devo ricordarti?", "reminder", True  # is_ask=True → salta synthesis

            # 5. Se manca solo il QUANDO → chiedi l'ora/data
            if not reminder_datetime:
                return "Quando vuoi che te lo ricordi? Dimmi l'ora o il giorno.", "reminder", True  # is_ask=True

            if reminder_text and reminder_datetime:
                # 3. DETERMINA SOURCE INIZIALE (con priorità)
                pref_source = "local"
                if "google" in message.lower():
                    pref_source = "google"
                elif "icloud" in message.lower() or "apple" in message.lower():
                    pref_source = "icloud"
                elif "calendario" in message.lower():
                    pref_source = "google" # Default calendario -> google
                
                # Creazione LOCALE (con tag iniziale)
                reminder_id, response = reminder_engine.create_reminder_with_response(user_id, reminder_text, reminder_datetime, source=pref_source)
                
                # Salva in sessione per follow-up (es. "Aggiungilo a Google")
                self.last_reminder_per_user[user_id] = {"text": reminder_text, "dt": reminder_datetime}
                
                # 3. CREAZIONE CLOUD — scrive su ENTRAMBI i calendari contemporaneamente (VEVENT)
                from auth.config import ADMIN_EMAILS
                profile = await storage.load(f"profile:{user_id}", default={})
                user_email = profile.get("email", "")
                is_admin = user_email in ADMIN_EMAILS

                from calendar_manager import calendar_manager
                can_use_google = bool(profile.get("google_token")) or (
                    is_admin and calendar_manager._admin_google_service is not None
                )
                can_use_icloud = bool(profile.get("icloud_user") and profile.get("icloud_password")) or (
                    is_admin and bool(os.environ.get("ICLOUD_USER"))
                )

                cloud_destinations = []

                # Google + iCloud in parallelo (non bloccante)
                _cal_tasks = []
                _cal_names = []
                _cal_keys = []
                if can_use_google:
                    _cal_tasks.append(asyncio.get_event_loop().run_in_executor(
                        None, calendar_manager.add_event, user_id, reminder_text, reminder_datetime, 'google'
                    ))
                    _cal_names.append("Google Calendar")
                    _cal_keys.append("google")
                if can_use_icloud:
                    _cal_tasks.append(asyncio.get_event_loop().run_in_executor(
                        None, calendar_manager.add_event, user_id, reminder_text, reminder_datetime, 'apple'
                    ))
                    _cal_names.append("iCloud Calendario")
                    _cal_keys.append("apple")

                if _cal_tasks:
                    _cal_results = await asyncio.gather(*_cal_tasks, return_exceptions=True)
                    for _name, _key, _result in zip(_cal_names, _cal_keys, _cal_results):
                        if _result and not isinstance(_result, Exception):
                            cloud_destinations.append(_name)
                            # Salva UID cloud nel reminder locale per la cancellazione futura
                            if reminder_id and isinstance(_result, str):
                                if _key == "apple":
                                    reminder_engine.update_reminder_cloud_ids(user_id, reminder_id, icloud_uid=_result)
                                elif _key == "google":
                                    reminder_engine.update_reminder_cloud_ids(user_id, reminder_id, google_event_id=_result)
                        else:
                            logger.warning("CALENDAR_WRITE_FAIL provider=%s user=%s", _key, user_id)

                if cloud_destinations:
                    dest_str = " e ".join(cloud_destinations)
                    if "Perfetto." in response:
                        response = response.replace("Perfetto.", f"Perfetto, aggiunto su {dest_str}.")
                    else:
                        response = response.rstrip(".") + f". Segnato su {dest_str}."

                return response, "reminder"
            
            return "Cosa vuoi che ti ricordi?", "reminder"
                
        except Exception as e:
            logger.error("REMINDER_CREATION_ERROR user=%s error=%s", user_id, str(e), exc_info=True)
            return "Mi dispiace, ho avuto un problema con il promemoria. Riprova.", "reminder"

    async def _handle_reminder_list(self, user_id: str, message: str) -> str:
        """
        Handle reminder list requests.
        Return formatted list of user's reminders.
        Returns: (response_text: str, source: str)
        """
        try:
            # Get pending reminders
            reminders = await reminder_engine.list_reminders(user_id, status_filter="pending", include_icloud=True)
            
            # Intelligence: Check account status
            profile = await storage.load(f"profile:{user_id}", default={})
            has_icloud = bool(profile.get("icloud_user") and profile.get("icloud_password"))
            has_google = bool(profile.get("google_token"))
            
            # DETERMINA SE LA RICHIESTA È "NATURALE" O "ESPLICITA"
            msg_lower = message.lower()
            explicit_triggers = ["lista", "elenco", "fammi vedere", "mostrami", "stampa", "elencami", "/list"]
            is_explicit = any(trigger in msg_lower for trigger in explicit_triggers)

            if not reminders:
                if is_explicit:
                    return "Non hai promemoria impostati nell'agenda locale.", "reminder"
                
                # Conversational "Awake" response
                if not has_icloud and not has_google:
                    return "Non ho trovato alcun impegno. Forse è perché non hai ancora collegato i tuoi account iCloud o Google? Se vuoi, posso aiutarti a farlo ora!", "reminder"
                else:
                    return "Sembra che la tua agenda sia libera! Non ho trovato alcun impegno programmato per ora.", "reminder"
            
            if not is_explicit:
                # Conversational response via LLM
                reminders_summary = reminder_engine.format_reminders_list(reminders)
                now_str = datetime.now().strftime("%A %d %B %H:%M")
                prompt = f"""Oggi è {now_str}.
L'utente chiede del suo programma: "{message}"
I suoi impegni nel programma sono:
{reminders_summary}

Rispondi in modo naturale, empatico e discorsivo (non usare elenchi numerati o punti elenco nel testo della risposta parlata).
Spiega all'utente i suoi impegni in modo fluido come farebbe un assistente personale.
Fai riferimento alle fonti (Google, iCloud) solo se necessario per chiarezza, ma in modo naturale.
Se non ci sono impegni per il periodo richiesto, faglielo presente con calore."""

                model = model_selector(message, route="reminder")
                response = await llm_service._call_with_protection(
                    model, prompt, message, user_id=user_id, route="reminder"
                )
                if response:
                    return response, "reminder"

            # Format and return the list with NO_TTS tag
            formatted_list = reminder_engine.format_reminders_list(reminders)
            return "[NO_TTS]" + formatted_list, "reminder"
            
        except Exception as e:
            logger.error("REMINDER_LIST_ERROR user=%s error=%s", user_id, str(e), exc_info=True)
            return "Mi dispiace, non riesco a vedere i tuoi promemoria. Riprova.", "reminder"

    async def _handle_reminder_delete(self, user_id: str, message: str) -> str:
        """
        Handle reminder deletion requests with deterministic parsing.
        Support: numero, "tutti", testo parziale (fuzzy)
        Returns: (response_text: str, source: str)
        """
        try:
            msg_lower = message.lower()
            
            # 1️⃣ "tutti" → elimina tutti i pending
            if "tutti" in msg_lower:
                deleted = reminder_engine.delete_all_pending(user_id)
                if deleted:
                    asyncio.create_task(reminder_engine.delete_cloud_events(user_id, deleted))
                    return f"Fatto! Ho rimosso tutti i {len(deleted)} promemoria dall'agenda e dai calendari collegati.", "reminder"
                else:
                    return "Non ho trovato promemoria attivi da cancellare, l'agenda è già pulita.", "reminder"

            # 1b️⃣ "passati"/"vecchi"/"scaduti" → elimina solo quelli con data nel passato
            if any(kw in msg_lower for kw in ["passati", "vecchi", "scaduti"]):
                from datetime import datetime as _dt
                all_pending = await reminder_engine.list_reminders(user_id, status_filter="pending")
                now = _dt.now()
                to_delete_ids = []
                for r in all_pending:
                    dt_str = r.get("datetime")
                    if not dt_str:
                        continue
                    try:
                        rdt = _dt.fromisoformat(dt_str.rstrip("Z"))
                        if rdt < now:
                            to_delete_ids.append(r["id"])
                    except Exception:
                        continue
                if to_delete_ids:
                    deleted = []
                    for rid in to_delete_ids:
                        d = reminder_engine.delete_reminder(user_id, rid)
                        if d:
                            deleted.append(d)
                    if deleted:
                        asyncio.create_task(reminder_engine.delete_cloud_events(user_id, deleted))
                        n = len(deleted)
                        label = "promemoria scaduto" if n == 1 else "promemoria scaduti"
                        return f"Ho rimosso {n} {label} dall'agenda e dai calendari collegati.", "reminder"
                return "Non ho trovato promemoria scaduti da cancellare.", "reminder"
            
            # 2️⃣ Numero → elimina per indice
            import re
            number_match = re.search(r'(\d+)', message)
            if number_match:
                index = int(number_match.group(1)) - 1  # Convert to 0-based
                
                reminders = await reminder_engine.list_reminders(user_id, status_filter="pending")
                
                if 0 <= index < len(reminders):
                    reminder_id = reminders[index]["id"]
                    deleted = reminder_engine.delete_reminder(user_id, reminder_id)

                    if deleted:
                        asyncio.create_task(reminder_engine.delete_cloud_events(user_id, [deleted]))
                        return f"Ho cancellato il promemoria {index + 1}.", "reminder"
                    else:
                        return "Mi dispiace, non sono riuscito a cancellare il promemoria.", "reminder"
                else:
                    return f"Non hai un promemoria numero {index + 1}.", "reminder"
            
            # 3️⃣ Testo parziale → fuzzy match semplice
            # Estrai testo dopo verbi di cancellazione
            delete_patterns = ["cancella promemoria", "elimina promemoria", "annulla promemoria", 
                              "cancella appuntamento", "elimina appuntamento", "rimuovi promemoria"]
            
            search_text = None
            for pattern in delete_patterns:
                if pattern in msg_lower:
                    parts = msg_lower.split(pattern, 1)
                    if len(parts) > 1:
                        search_text = parts[1].strip()
                        break
            
            if search_text:
                reminders = await reminder_engine.list_reminders(user_id, status_filter="pending")
                
                # Fuzzy match semplice: cerca testo parziale
                for reminder in reminders:
                    if search_text in reminder["text"].lower():
                        deleted = reminder_engine.delete_reminder(user_id, reminder["id"])

                        if deleted:
                            asyncio.create_task(reminder_engine.delete_cloud_events(user_id, [deleted]))
                            return f"Ho cancellato il promemoria: {reminder['text']}", "reminder"
                        else:
                            return "Mi dispiace, non sono riuscito a cancellare il promemoria.", "reminder"
                
                return f"Non trovo promemoria con '{search_text}'.", "reminder"
            
            # 4️⃣ Default → elimina il più recente
            latest_reminder = reminder_engine.get_latest_pending(user_id)

            if latest_reminder:
                deleted = reminder_engine.delete_reminder(user_id, latest_reminder["id"])

                if deleted:
                    asyncio.create_task(reminder_engine.delete_cloud_events(user_id, [deleted]))
                    return "Ho cancellato l'ultimo promemoria.", "reminder"
                else:
                    return "Mi dispiace, non sono riuscito a cancellare il promemoria.", "reminder"
            else:
                return "Non hai promemoria da cancellare.", "reminder"
                
        except Exception as e:
            logger.error("REMINDER_DELETE_ERROR user=%s error=%s", user_id, str(e), exc_info=True)
            return "Mi dispiace, ho avuto un problema con la cancellazione. Riprova.", "reminder"

    async def _handle_reminder_update(self, user_id: str, message: str) -> str:
        """
        Handle reminder update requests with deterministic parsing.
        Support: numero, testo parziale, nuova data/ora
        Returns: (response_text: str, source: str)
        """
        try:
            msg_lower = message.lower()
            
            # 1️⃣ Numero → modifica per indice
            import re
            number_match = re.search(r'(\d+)', message)
            target_reminder = None
            
            if number_match:
                index = int(number_match.group(1)) - 1  # Convert to 0-based
                
                reminders = await reminder_engine.list_reminders(user_id, status_filter="pending")
                
                if 0 <= index < len(reminders):
                    target_reminder = reminders[index]
                else:
                    return f"Non hai un promemoria numero {index + 1}.", "reminder"
            else:
                # 2️⃣ Senza numero → usa il più recente
                target_reminder = reminder_engine.get_latest_pending(user_id)
            
            if not target_reminder:
                return "Non hai promemoria da modificare.", "reminder"
            
            # 3️⃣ Parsing nuova data/ora
            new_datetime = self._parse_update_datetime_strict(message)
            
            if not new_datetime:
                return "Non ho capito a quando vuoi spostare il promemoria. Prova con 'sposta alle 18' o 'a domani'.", "reminder"
            
            # 4️⃣ Aggiorna il reminder
            success = reminder_engine.update_reminder_datetime(user_id, target_reminder["id"], new_datetime)
            
            if success:
                # Format confirmation message
                date_str = new_datetime.strftime("%d %b %H:%M")
                return f"Ho aggiornato il promemoria al {date_str}.", "reminder"
            else:
                return "Mi dispiace, non sono riuscito ad aggiornare il promemoria.", "reminder"
                
        except Exception as e:
            logger.error("REMINDER_UPDATE_ERROR user=%s error=%s", user_id, str(e), exc_info=True)
            return "Mi dispiace, ho avuto un problema con l'aggiornamento. Riprova.", "reminder"

    # ═══════════════════════════════════════════════════════════════
    # IMAGE GENERATION ROUTER — Bedrock integration
    # ═══════════════════════════════════════════════════════════════

    async def _handle_image_search(self, user_id: str, query: str) -> str:
        """Search web images and return frontend-compatible JSON payload."""
        try:
            service = get_image_search_service()
            results = await service.search(query, max_results=4)
            if not results:
                return "Non ho trovato immagini rilevanti. Prova con una descrizione più specifica.", "tool"

            payload = {
                "text": f"Ho trovato alcune immagini per: {query}",
                "images": [
                    {
                        "url": r.url,
                        "thumbnail": r.thumbnail or r.url,
                        "title": r.title or query,
                        "source": r.source,
                    }
                    for r in results
                ],
                "tts_text": f"Ho trovato alcune immagini per {query}."
            }
            return json.dumps(payload, ensure_ascii=False), "tool"
        except Exception as e:
            logger.error("IMAGE_SEARCH_ROUTE_ERROR user=%s query=%s err=%s", user_id, query, e, exc_info=True)
            return "Ho avuto un problema durante la ricerca immagini sul web. Riprova tra poco.", "tool"

    async def _handle_image_generation(self, user_id: str, message: str) -> str:
        """
        Handle image generation requests via AWS Bedrock.
        Extracts prompt from message and generates image.
        Returns: (response_text: str, source: str) → but we return only str here
        """
        try:
            from core.openrouter_image_service import openrouter_image_service as _or_img_svc
            if not bedrock_image_service.enabled and not _or_img_svc.enabled:
                logger.warning("IMAGE_GENERATION_DISABLED user=%s no_providers_configured", user_id)
                fallback_prompt = message.strip()
                fallback = await self._handle_image_search(user_id, fallback_prompt)
                if isinstance(fallback, tuple) and fallback and isinstance(fallback[0], str) and fallback[0].startswith("{"):
                    return fallback
                return "La generazione immagini non è disponibile al momento. Posso però cercare immagini sul web se me lo chiedi con 'cerca immagini di ...'.", "tool"
            
            # Extract the prompt from the message
            # Remove common trigger phrases: "genera un'immagine di", "disegna", "crea una foto di", etc.
            msg_clean = message.lower().strip()
            
            # Remove trigger keywords to get the actual prompt
            trigger_words = [
                "genera un'immagine di", "genera un'immagine",
                "genera una immagine di", "genera una immagine",
                "genera un immagine di", "genera un immagine",
                "genera una foto di", "genera una foto", "genera foto di", "genera foto",
                "crea un'immagine di", "crea un'immagine",
                "crea una immagine di", "crea una immagine",
                "crea una foto di", "crea una foto",
                "disegna una foto", "disegna un'immagine", "disegna di", "disegna",
                "mostra una foto di", "mostra un'immagine di", "mostra una foto", "mostra un'immagine",
                "crea un'illustrazione di", "crea un'illustrazione",
                "illustra", "crea una picture di", "crea una picture",
                "genera grafica", "dipingi", "disegni",
                "voglio vedere", "immagina che", "come appare", "come sarebbe",
                "genera", "crea", "fa una foto",
            ]

            prompt = message
            for trigger in trigger_words:
                if msg_clean.startswith(trigger):
                    prompt = message[len(trigger):].strip()
                    break

            # Final cleanup
            prompt = prompt.strip()
            if not prompt:
                return "Dimmi cosa vuoi che disegni! Ad esempio: 'una montagna con le nuvole' o 'un unicorno che vola'.", "tool"

            # Se il prompt è troppo lungo per Bedrock (max 512 chars), condensalo via LLM
            if len(prompt) > 450:
                try:
                    condense_sys = (
                        "Sei un prompt engineer per generatori di immagini. "
                        "Ricevi una descrizione lunga e la condensi in una descrizione visiva chiara, "
                        "entro 400 caratteri, mantenendo i dettagli più importanti. "
                        "Rispondi SOLO con il prompt condensato, niente altro."
                    )
                    condensed = await llm_service._call_with_protection(
                        "gpt-4o-mini", condense_sys, prompt, user_id=user_id, route="image_condensing"
                    )
                    if condensed and condensed.strip() and len(condensed.strip()) <= 500:
                        logger.info("IMAGE_PROMPT_CONDENSED original=%d condensed=%d", len(prompt), len(condensed.strip()))
                        prompt = condensed.strip()
                except Exception as _ce:
                    logger.warning("IMAGE_PROMPT_CONDENSE_FAILED error=%s — truncating", _ce)
                    prompt = prompt[:500]
            
            # Generazione immagine: OpenRouter (Nano Banana 2) → Bedrock fallback
            openrouter_image_service = _or_img_svc  # già importato sopra

            image_url: Optional[str] = None
            image_source = "Genesi AI"

            # 1️⃣ Prova OpenRouter — Gemini 3.1 Flash Image Preview (Nano Banana 2)
            if openrouter_image_service.enabled:
                logger.info("IMAGE_GENERATION_TRY provider=openrouter user=%s prompt_len=%d", user_id, len(prompt))
                image_url = await openrouter_image_service.generate_image(prompt=prompt, user_id=user_id)
                if image_url:
                    image_source = "Gemini 3.1 Flash Image"
                    logger.info("IMAGE_GENERATION_OK provider=openrouter user=%s", user_id)
                else:
                    logger.warning("IMAGE_GENERATION_MISS provider=openrouter user=%s — trying Bedrock", user_id)

            # 2️⃣ Fallback: AWS Bedrock
            if image_url is None and bedrock_image_service.enabled:
                logger.info("IMAGE_GENERATION_TRY provider=bedrock user=%s prompt_len=%d", user_id, len(prompt))
                image_url = await bedrock_image_service.generate_image(
                    prompt=prompt,
                    user_id=user_id,
                    width=512,
                    height=512,
                    steps=50,
                    guidance_scale=7.5,
                )
                if image_url:
                    image_source = "AWS Bedrock"
                    logger.info("IMAGE_GENERATION_OK provider=bedrock user=%s", user_id)

            if image_url is None:
                logger.error("IMAGE_GENERATION_FAILED_ALL_PROVIDERS user=%s prompt=%s", user_id, prompt[:50])
                fallback = await self._handle_image_search(user_id, prompt)
                if isinstance(fallback, tuple) and fallback and isinstance(fallback[0], str) and fallback[0].startswith("{"):
                    return fallback
                return "Ho avuto un problema nella generazione dell'immagine. Riprova con una descrizione diversa o più semplice.", "tool"

            # Stats Bedrock (solo se usato)
            stats = {}
            if image_source == "AWS Bedrock":
                try:
                    stats = await bedrock_image_service.get_user_stats(user_id)
                except Exception:
                    pass

            response_text = "Ecco l'immagine che ho creato per te!"

            # Prepare image response in the format frontend expects
            image_response = {
                "text": response_text,
                "images": [
                    {
                        "url": image_url,
                        "source": image_source,
                        "title": prompt,
                        "cost": f"${stats.get('total_cost_usd', 0):.4f}" if stats else "",
                    }
                ],
                "tts_text": response_text,
            }

            # Return JSON string with images so frontend can render gallery
            logger.info(
                "IMAGE_GENERATION_SUCCESS user=%s provider=%s url_len=%d",
                user_id, image_source, len(image_url),
            )

            return json.dumps(image_response, ensure_ascii=False), "tool"
            
        except Exception as e:
            logger.error("IMAGE_GENERATION_ERROR user=%s error=%s", user_id, str(e), exc_info=True)
            return "Mi dispiace, ho avuto un errore nella generazione dell'immagine. Riprova tra poco.", "tool"

    async def _handle_icloud_setup(self, user_id: str, message: str) -> str:
        """
        Gestisce la configurazione dell'account iCloud dell'utente.
        Estrae email e password (specifica per app) dal messaggio.
        """
        try:
            msg_lower = message.lower()
            
            # Use LLM to extract credentials safely
            setup_prompt = f"""Estrai l'email iCloud e la password specifica per le app dal seguente messaggio.
Rispondi con un JSON nel formato: {{"email": "...", "password": "..."}}
Se i dati mancano, lascia i campi null. Non inventare dati.

Messaggio: {message}"""
            
            from core.llm_service import llm_service
            import json
            
            response = await llm_service._call_with_protection(
                "gpt-4o-mini", setup_prompt, message, user_id=user_id, route="icloud"
            )
            
            creds = {}
            if response:
                try:
                    import re
                    json_match = re.search(r'\{.*\}', response, re.DOTALL)
                    if json_match:
                        creds = json.loads(json_match.group(0))
                except: pass
            
            email = creds.get("email")
            password = creds.get("password")
            
            # AUTO-FIX COMMON TYPOS (e.g. .com.com)
            if email and isinstance(email, str):
                if email.endswith(".com.com"):
                    email = email.replace(".com.com", ".com")
                    logger.info("ICLOUD_SETUP_AUTOFIX_EMAIL original=%s current=%s", creds.get("email"), email)
                elif email.endswith(".it.it"):
                    email = email.replace(".it.it", ".it")

            if not email or not password:
                return (
                    "Ti guido io, passo dopo passo — ci vogliono 2 minuti.\n\n"
                    "**Passo 1** → Vai su [appleid.apple.com](https://appleid.apple.com) e fai il login con il tuo Apple ID.\n\n"
                    "**Passo 2** → Clicca su **\"Accedi e sicurezza\"** (o \"Sicurezza dell'account\") "
                    "→ poi **\"Password specifiche per le app\"**.\n\n"
                    "**Passo 3** → Premi il **+** in fondo alla lista, scrivi `Genesi` come nome "
                    "e premi **Crea**. Apple ti darà una password di 16 caratteri nel formato:\n"
                    "`xxxx-xxxx-xxxx-xxxx`\n\n"
                    "**Passo 4** → Copia quella password e torna qui. Poi scrivimi così:\n"
                    "> Collega **tuaemail@icloud.com** con password **xxxx-xxxx-xxxx-xxxx**\n\n"
                    "Sono qui quando sei pronto! 🍎"
                )
            
            # Salva nel profilo
            profile = await storage.load(f"profile:{user_id}", default={})
            profile["icloud_user"] = email
            profile["icloud_password"] = password
            profile["icloud_verified"] = False # Richiede primo test
            await storage.save(f"profile:{user_id}", profile)
            
            # Verifica credenziali immediatamente
            from core.icloud_service import ICloudService
            svc = ICloudService(username=email, password=password)
            
            if svc.validate_credentials():
                profile["icloud_verified"] = True
                await storage.save(f"profile:{user_id}", profile)
                return f"Fantastico! Ho collegato correttamente il tuo account iCloud ({email}). Ora posso sincronizzare i tuoi promemoria."
            else:
                logger.warning("ICLOUD_AUTH_TEST_FAIL: email=%s", email)
                return "Le credenziali sembrano errate o iCloud ha rifiutato la connessione. Assicurati di usare l'email corretta e la **password specifica per le app**."
                
        except Exception as e:
            logger.error("ICLOUD_SETUP_ERROR user=%s error=%s", user_id, str(e))
            return "Problema tecnico durante la configurazione di iCloud. Riprova più tardi."

    async def _handle_icloud_sync(self, user_id: str, message: str) -> str:
        """Sincronizza i promemoria iCloud o aggiunge l'ultimo creato."""
        try:
            msg_lower = message.lower()
            
            # Caso follow-up: "Aggiungilo a iCloud"
            if any(kw in msg_lower for kw in ["aggiungi", "salva", "metti", "scrivi"]) and user_id in self.last_reminder_per_user:
                last_rem = self.last_reminder_per_user[user_id]
                success = await reminder_engine.create_icloud_reminder(user_id, last_rem["text"], last_rem["dt"])
                if success:
                    return f"Fatto! Ho aggiunto '{last_rem['text']}' al tuo account iCloud."
                else:
                    return "Non sono riuscito a scriverlo su iCloud. Verifica la configurazione."

            # Forza fetch da iCloud
            reminders = await reminder_engine.fetch_icloud_reminders(user_id)
            if reminders:
                return f"Sincronizzazione completata! Ho trovato {len(reminders)} promemoria sul tuo account iCloud."
            else:
                profile = await storage.load(f"profile:{user_id}", default={})
                if not profile.get("icloud_user"):
                    return "Il tuo account iCloud non è ancora configurato. Dimmi 'collega icloud' per iniziare."
                return "Sincronizzazione completata. Non ho trovato nuovi promemoria su iCloud."
        except Exception as e:
            logger.error("ICLOUD_SYNC_ERROR user=%s error=%s", user_id, str(e))
            return "Errore durante la sincronizzazione con iCloud."

    def _parse_update_datetime_strict(self, message: str) -> Optional[datetime]:
        """
        Parse update datetime with STRICT logic.
        SOLO orario esplicito (HH:MM) o data esplicita.
        MAI fallback automatici.
        
        Args:
            message: User message like "sposta alle 18" or "a domani"
            
        Returns:
            New datetime or None if invalid
        """
        import re
        
        msg_lower = message.lower().strip()
        now = datetime.now()
        
        # 1️⃣ Pattern orario esplicito HH:MM
        time_match = re.search(r'(\d{1,2}):(\d{2})', message)
        hour = None
        minute = None
        
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
        
        # 2️⃣ Pattern data esplicita
        target_date = None
        
        # Oggi
        if "oggi" in msg_lower:
            target_date = now.date()
        # Domani
        elif "domani" in msg_lower:
            target_date = (now + timedelta(days=1)).date()
        # Ieri
        elif "ieri" in msg_lower:
            target_date = (now - timedelta(days=1)).date()
        # Giorni della settimana
        elif any(day in msg_lower for day in ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]):
            day_map = {
                "lunedì": 0, "martedì": 1, "mercoledì": 2, "giovedì": 3, 
                "venerdì": 4, "sabato": 5, "domenica": 6
            }
            
            for day_name, day_num in day_map.items():
                if day_name in msg_lower:
                    days_ahead = day_num - now.weekday()
                    if days_ahead <= 0:
                        days_ahead += 7
                    target_date = (now + timedelta(days=days_ahead)).date()
                    break
        
        # 3️⃣ Costruisci datetime SOLO se abbiamo almeno ora o data
        new_datetime = None
        
        if hour is not None and minute is not None:
            # Abbiamo orario esplicito
            if target_date:
                # Data + ora
                new_datetime = datetime.combine(target_date, datetime.min.time().replace(hour=hour, minute=minute))
            else:
                # Solo ora → usa oggi
                new_datetime = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                # Se ora è nel passato → sposta a domani
                if new_datetime <= now:
                    new_datetime += timedelta(days=1)
        elif target_date:
            # Solo data → usa ora corrente
            new_datetime = datetime.combine(target_date, now.time())
        
        return new_datetime

    def _parse_reminder_request_strict(self, message: str) -> tuple[str, Optional[datetime]]:
        """
        Parse reminder request with STRICT logic.
        SOLO orario esplicito (HH:MM) o data esplicita.
        MAI fallback automatici.
        
        Args:
            message: User message like "ricordami di chiamare il medico domani alle 18"
            
        Returns:
            Tuple of (reminder_text, reminder_datetime)
        """
        import re
        from typing import Optional
        
        # Dizionario conversione numeri italiani
        NUMERI_ITALIANI = {
            'uno': 1, 'due': 2, 'tre': 3, 'quattro': 4, 'cinque': 5,
            'sei': 6, 'sette': 7, 'otto': 8, 'nove': 9, 'dieci': 10,
            'quindici': 15, 'venti': 20, 'trenta': 30, 'quaranta': 40,
            'cinquanta': 50, 'sessanta': 60
        }
        
        msg_lower = message.lower().strip()
        
        # Normalizza numeri in lettere prima del parsing
        msg_normalized = msg_lower
        for parola, cifra in NUMERI_ITALIANI.items():
            msg_normalized = re.sub(rf'\b{parola}\b', str(cifra), msg_normalized)
        
        now = datetime.now()
        
        # 1️⃣ Estrai testo dopo "ricordami di" / "ricordami che"
        reminder_text = ""
        if "ricordami di " in msg_lower:
            # Estrai fino ai pattern temporali
            parts = msg_lower.split("ricordami di ", 1)
            if len(parts) > 1:
                reminder_text = parts[1].strip()
                # Rimuovi pattern temporali dalla fine
                temp_patterns = [
                    r'\s+domani(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
                    r'\s+oggi(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
                    r'\s+(?:lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica)(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
                    r'\s+alle\s+\d{1,2}(?::\d{2})?',
                    r'\s+tra\s+\d+\s+(?:minut[oi]|or[ae]|second[oi]|giorn[oi])'
                ]
                for pattern in temp_patterns:
                    reminder_text = re.sub(pattern, '', reminder_text)
                reminder_text = reminder_text.strip()
        elif "ricordami che " in msg_lower:
            parts = msg_lower.split("ricordami che ", 1)
            if len(parts) > 1:
                reminder_text = parts[1].strip()
                # Rimuovi pattern temporali dalla fine
                temp_patterns = [
                    r'\s+domani(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
                    r'\s+oggi(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
                    r'\s+(?:lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica)(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
                    r'\s+alle\s+\d{1,2}(?::\d{2})?',
                    r'\s+tra\s+\d+\s+(?:minut[oi]|or[ae]|second[oi]|giorn[oi])'
                ]
                for pattern in temp_patterns:
                    reminder_text = re.sub(pattern, '', reminder_text)
                reminder_text = reminder_text.strip()
        elif "ricordami " in msg_lower:
            parts = msg_lower.split("ricordami ", 1)
            if len(parts) > 1:
                reminder_text = parts[1].strip()
                # Rimuovi pattern temporali dalla fine
                temp_patterns = [
                    r'\s+dopodomani(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
                    r'\s+domani(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
                    r'\s+stasera(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
                    r'\s+oggi(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
                    r'\s+(?:lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica)(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
                    r'\s+alle\s+\d{1,2}(?::\d{2})?',
                    r'\s+tra\s+\d+\s+(?:minut[oi]|or[ae]|second[oi]|giorn[oi])'
                ]
                for pattern in temp_patterns:
                    reminder_text = re.sub(pattern, '', reminder_text)
                reminder_text = reminder_text.strip()
        
        # 1b️⃣ Pattern durata relativa: "tra X minuti", "tra X ore", "tra X secondi"
        relative_match = re.search(
            r'tra\s+(\d+)\s+(minut[oi]|or[ae]|second[oi]|giorn[oi])',
            msg_normalized
        )
        if relative_match:
            quantity = int(relative_match.group(1))
            unit = relative_match.group(2)

            if unit.startswith("minut"):
                delta = timedelta(minutes=quantity)
            elif unit.startswith("or") or unit.startswith("or"):
                delta = timedelta(hours=quantity)
            elif unit.startswith("second"):
                delta = timedelta(seconds=quantity)
            elif unit.startswith("giorn"):
                delta = timedelta(days=quantity)
            else:
                delta = None

            if delta:
                reminder_datetime = now + delta
                # Rimuovi pattern relativo dal reminder_text
                reminder_text = re.sub(
                    r'\s*tra\s+\d+\s+(?:minut[oi]|or[ae]|second[oi]|giorn[oi])',
                    '',
                    reminder_text,
                    flags=re.IGNORECASE
                ).strip()
                return reminder_text, reminder_datetime

        # 2️⃣ Pattern orario esplicito HH:MM o H:MM
        time_match = re.search(r'(\d{1,2}):(\d{2})', message)
        hour = None
        minute = None
        
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2))
        else:
            # Pattern "alle H" senza minuti
            time_match_simple = re.search(r'alle\s+(\d{1,2})(?::(\d{2}))?', msg_lower)
            if time_match_simple:
                hour = int(time_match_simple.group(1))
                minute = int(time_match_simple.group(2)) if time_match_simple.group(2) else 0
        
        # 3️⃣ Pattern data esplicita
        target_date = None
        
        # Oggi / Stasera
        if "oggi" in msg_lower or "stasera" in msg_lower:
            target_date = now.date()
            if "stasera" in msg_lower and hour is None:
                hour = 20
                minute = 0
        # Domani
        elif "domani" in msg_lower:
            target_date = (now + timedelta(days=1)).date()
        # Dopodomani
        elif "dopodomani" in msg_lower:
            target_date = (now + timedelta(days=2)).date()
        # Ieri
        elif "ieri" in msg_lower:
            target_date = (now - timedelta(days=1)).date()
        # Giorni della settimana
        elif any(day in msg_lower for day in ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]):
            day_map = {
                "lunedì": 0, "martedì": 1, "mercoledì": 2, "giovedì": 3, 
                "venerdì": 4, "sabato": 5, "domenica": 6
            }
            
            for day_name, day_num in day_map.items():
                if day_name in msg_lower:
                    days_ahead = day_num - now.weekday()
                    if days_ahead <= 0:
                        days_ahead += 7
                    target_date = (now + timedelta(days=days_ahead)).date()
                    break
        
        # 4️⃣ Costruisci datetime SOLO se abbiamo almeno ora o data
        reminder_datetime = None
        
        if hour is not None and minute is not None:
            # Abbiamo orario esplicito
            if target_date:
                # Data + ora
                reminder_datetime = datetime.combine(target_date, datetime.min.time().replace(hour=hour, minute=minute))
            else:
                # Solo ora → usa oggi
                reminder_datetime = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                # Se ora è nel passato → non creare (chiedere)
                if reminder_datetime <= now:
                    reminder_datetime = None
        elif target_date:
            # Solo data → non creare (chiedere ora)
            reminder_datetime = None
        
        return reminder_text, reminder_datetime

    async def _parse_reminder_natural(self, message: str, user_id: str) -> tuple[Optional[str], Optional[datetime]]:
        """
        Extrazione naturale tramite LLM per promemoria complessi.
        """
        try:
            from core.llm_service import llm_service
            import json
            import re
            
            now = datetime.now()
            prompt = f"""Estrai il TESTO del promemoria e la DATA/ORA dal messaggio dell'utente.
Data e ora corrente: {now.strftime('%A %d %B %Y, %H:%M')}

REGOLE:
1. Se l'utente dice "domani", intende { (now + timedelta(days=1)).strftime('%Y-%m-%d') }.
2. Restituisci un JSON nel formato: {{"text": "cosa fare", "dt": "YYYY-MM-DD HH:MM"}}
3. Se non riesci a capire l'ora, usa 09:00 come default.
4. Se non riesci a capire la data, usa null.

Messaggio: "{message}" """

            response = await llm_service._call_with_protection(
                "gpt-4o-mini", prompt, message, user_id=user_id, route="reminder"
            )
            
            if response:
                json_match = re.search(r'\{.*\}', response, re.S)
                if json_match:
                    try:
                        data = json.loads(json_match.group(0))
                        text = data.get("text")
                        dt_str = data.get("dt")
                        
                        if text and dt_str:
                            dt = datetime.strptime(dt_str, '%Y-%m-%d %H:%M')
                            return text, dt
                    except: pass
            
            return None, None
        except Exception as e:
            logger.error("NATURAL_PARSING_ERROR: %s", str(e))
            return None, None

    def _parse_reminder_request(self, message: str) -> tuple[str, datetime]:
        """
        Parse reminder request to extract text and datetime.
        LEGACY METHOD - mantenuto per compatibilità test.
        
        Args:
            message: User message like "ricordami di chiamare il medico domani alle 18"
            
        Returns:
            Tuple of (reminder_text, reminder_datetime)
        """
        import re
        from datetime import datetime, timedelta
        
        msg_lower = message.lower().strip()
        
        # Simple approach: extract text between "ricordami" and date/time keywords
        if not msg_lower.startswith('ricordami'):
            return None, None
        
        # Remove "ricordami" or "ricordamelo" prefix
        if msg_lower.startswith('ricordami di '):
            reminder_text = msg_lower[12:]  # Remove "ricordami di "
        elif msg_lower.startswith('ricordamelo '):
            reminder_text = msg_lower[11:]  # Remove "ricordamelo "
        elif msg_lower.startswith('ricordami '):
            reminder_text = msg_lower[10:]  # Remove "ricordami "
        else:
            return None, None
        
        # Remove date/time part from the reminder text
        date_time_patterns = [
            r'\s+dopodomani(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
            r'\s+domani(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
            r'\s+stasera(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
            r'\s+oggi(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
            r'\s+(?:lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica)(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
            r'\s+alle\s+\d{1,2}(?::\d{2})?'
        ]
        
        for pattern in date_time_patterns:
            reminder_text = re.sub(pattern, '', reminder_text)
        
        reminder_text = reminder_text.strip()
        
        if not reminder_text:
            return None, None
        
        # Parse date and time
        now = datetime.now()
        reminder_datetime = None
        
        # Time patterns
        time_match = re.search(r'alle\s+(\d{1,2})(?::(\d{2}))?', msg_lower)
        if time_match:
            hour = int(time_match.group(1))
            minute = int(time_match.group(2)) if time_match.group(2) else 0
        else:
            # Default time if not specified
            hour, minute = 9, 0  # 9:00 AM
        
        # Date patterns
        if "dopodomani" in msg_lower:
            reminder_datetime = now.replace(hour=hour, minute=minute) + timedelta(days=2)
        elif "domani" in msg_lower:
            reminder_datetime = now.replace(hour=hour, minute=minute) + timedelta(days=1)
        elif "stasera" in msg_lower:
            # If "stasera" is used without a time, default to 20:00
            target_hour = hour if time_match else 20
            target_minute = minute if time_match else 0
            reminder_datetime = now.replace(hour=target_hour, minute=target_minute)
            if reminder_datetime <= now:
                # If it's already past 20:00 today, set for tomorrow?
                # Actually "stasera" usually means today. If too late, maybe next evening?
                # Standard choice: if past, it's just past.
                pass
        elif "oggi" in msg_lower:
            reminder_datetime = now.replace(hour=hour, minute=minute)
            # If time is in the past, move to tomorrow
            if reminder_datetime <= now:
                reminder_datetime += timedelta(days=1)
        elif any(day in msg_lower for day in ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]):
            # Map Italian days to weekday numbers
            day_map = {
                "lunedì": 0, "martedì": 1, "mercoledì": 2, "giovedì": 3, 
                "venerdì": 4, "sabato": 5, "domenica": 6
            }
            
            for day_name, day_num in day_map.items():
                if day_name in msg_lower:
                    # Find next occurrence of this day
                    days_ahead = day_num - now.weekday()
                    if days_ahead <= 0:  # Target day already happened this week
                        days_ahead += 7
                    reminder_datetime = now.replace(hour=hour, minute=minute) + timedelta(days=days_ahead)
                    break
        else:
            # Default to tomorrow if no date specified
            reminder_datetime = now.replace(hour=hour, minute=minute) + timedelta(days=1)
        
        return reminder_text, reminder_datetime

    # ═══════════════════════════════════════════════════════════
    # RELATIONAL ROUTER — GPT controllato con contesto limitato
    # ═══════════════════════════════════════════════════════════

    async def _handle_relational(self, user_id: str, message: str, brain_state: Dict[str, Any], conversation_id: str = None) -> str:
        """
        Pipeline relazionale con GPT controllato.
        GPT riceve: conversation thread, identity summary, topic, latent state.
        GPT NON inventa memoria.
        Returns: (response_text: str, source: str)
        """
        # 1. Context Assembler — structured context from memory
        context = await self.context_assembler.build(user_id, message)
        logger.info("CONTEXT_ASSEMBLED user=%s summary_len=%d", user_id, len(context.get('summary', '')))

        # Inject into brain_state for backward compatibility
        brain_state["relational_context"] = context["summary"]
        brain_state["assembled_context"] = context

        # 2. Build conversation context with chat history + profile + topic
        profile = context.get("profile", {})
        
        # 🔥 NEW: Build separate messages for LLM conversation thread
        messages = self._build_conversation_messages(user_id, message, profile)
        
        conversation_ctx = build_conversation_context(user_id, message, profile, conversation_id)
        logger.info("CONVERSATION_CONTEXT_BUILT user=%s len=%d", user_id, len(conversation_ctx))

        latent = brain_state.get("latent", {})
        latent_synopsis = (f"attachment={latent.get('attachment', 0):.2f} "
                           f"resonance={latent.get('emotional_resonance', 0):.2f} "
                           f"energy={latent.get('relational_energy', 0):.2f}")

        # 3. GPT call with conversation-aware prompt
        logger.info("PROACTOR_LLM_CALL user=%s route=relational messages_count=%d", user_id, len(messages))
        
        # NEW: Fetch calendar summary for prompt
        calendar_info = ""
        try:
            from calendar_manager import calendar_manager
            rems = calendar_manager.list_reminders(user_id, days=3)
            if rems:
                items = []
                for r in rems[:5]:
                    due = r.get("due", "Presto")
                    if isinstance(due, str) and "T" in due:
                        due = due.split("T")[1][:5]
                    items.append(f"{r['summary']} ({due})")
                calendar_info = " | ".join(items)
            else:
                calendar_info = "Nessun impegno imminente."
        except Exception as e:
            logger.error(f"CALENDAR_FETCH_PROMPT_ERROR: {e}")
            calendar_info = "Errore recupero calendario."

        # Get user timezone and city from profile
        _rel_profile = brain_state.get("profile", {})
        user_tz = _rel_profile.get("timezone", "Europe/Rome")
        user_city = _rel_profile.get("city") or "Italia"

        gpt_prompt = self._build_relational_gpt_prompt(
            conversation_ctx, latent_synopsis, message, user_id,
            calendar_info=calendar_info, tz=user_tz, user_city=user_city
        )
        
        # Add system message to messages list
        messages.insert(0, {"role": "system", "content": gpt_prompt})

        model = model_selector(message, route="relational")
        gpt_response = await llm_service._call_with_protection(
            model, gpt_prompt, message, user_id=user_id, route="relational", messages=messages
        )
        if gpt_response is None:
            # Deterministic fallback -- no silent failure
            logger.warning("RELATIONAL_ROUTER_LLM_FAIL user=%s -- using autonomous response", user_id)
            from core.evolution_engine import _generate_autonomous_response
            gpt_response = _generate_autonomous_response(
                brain_state.get("profile", {}).get("name", ""),
                brain_state.get("relational", {}).get("trust", 0.2),
                brain_state.get("relational", {}).get("stage", "initial"),
                brain_state.get("emotion", {}).get("emotion", "neutral"),
                brain_state.get("emotion", {}).get("intensity", 0.3),
                message,
                brain_state.get("episodes", []),
                brain_state.get("profile", {})
            )

        logger.info("PROACTOR_LLM_RESPONSE user=%s response_len=%d", user_id, len(gpt_response))

        # 4. Curiosity Engine
        curious_response = curiosity_engine.inject(gpt_response, message, brain_state)

        # 5. Emotional Intensity Engine
        enhanced_response = emotional_intensity_engine.enhance(curious_response, message, brain_state)

        # 5.5 Emotional Adapter (Tone modulation)
        try:
            from core.emotion_adapter import adapt_tone
            user_name = profile.get("name", "")
            mood = brain_state.get("emotion", {}).get("emotion", "neutro")
            enhanced_response = adapt_tone(enhanced_response, mood, user_name)
        except Exception as e:
            logger.error(f"EMOTION_ADAPTER_FAIL error={str(e)}")

        # 6. Drift Modulator
        latent_vector = latent_state_engine.get_vector(latent)
        response = drift_modulator.modulate_response_style(
            latent_state=latent_vector,
            relational_state=brain_state.get("relational", {}),
            base_response=enhanced_response
        )

        # 7. Post-generation filter (template strip + loop block)
        response = filter_response(response, user_id)
        if not response:
            # Regeneration: one retry with higher temperature hint
            logger.warning("RESPONSE_FILTER_REGEN user=%s route=relational", user_id)
            gpt_response2 = await llm_service._call_with_protection(
                model, gpt_prompt, message, user_id=user_id, route="relational"
            )
            if gpt_response2:
                response = filter_response(gpt_response2, user_id)
            if not response:
                response = "Dimmi."

        logger.info("PROACTOR_RESPONSE user=%s len=%d route=relational emotion=%s",
                     user_id, len(response),
                     brain_state.get("emotion", {}).get("emotion", "?"))
        return response

    async def _synthesize_responses(self, user_id: str, message: str, responses: list[str]) -> str:
        """
        Synthesize multiple tool/knowledge responses into a fluid narrative.
        Uses gpt-4o-mini for efficient post-processing.
        """
        if not responses:
            return ""
        if len(responses) == 1:
            return responses[0]

        fragments = "\n---\n".join(responses)
        
        # Get user name for personalization
        profile = await storage.load(f"profile:{user_id}", default={})
        user_name = profile.get("name", "l'utente")

        prompt = f"""Sei Genesi. Hai appena eseguito diverse azioni per rispondere a {user_name}.
I vari moduli del sistema hanno prodotto questi frammenti separati: uno tecnico (dati crudi) e uno conversazionale.

MESSAGGIO UTENTE: {message}

FRAMMENTI DA INTEGRARE (Dati crudi + Relazionale):
{fragments}

Il tuo compito è agire come "voce narrante" di Genesi. Non devi limitarti a unire i testi, devi REINTERPRETARE i dati tecnici integrandoli in una narrazione fluida, umana e naturale.

REGOLE TASSATIVE:
1. NARRATIVA INTEGRATA: Non elencare i dati e poi salutare. Parla DIRETTAMENTE all'utente usando i dati tecnici per arricchire il discorso. (es: invece di dire "Meteo: 20 gradi. Ciao Luca", usa "Ehi Luca, qui fuori ci sono dei piacevoli 20 gradi...")
2. PRECISIONE: Inserisci TUTTI i dati tecnici (orari, temperature, titoli di news, dettagli promemoria) nella narrazione senza perderne l'accuratezza, ma togliendo la rigidità dei "pappagalli".
3. STILE: Mantieni lo stile di Genesi: intelligente, profondo, asciutto ma empatico.
4. NO RITUALI: NON usare mai "Ecco i risultati", "Ho trovato quanto segue", "Certamente", "Spero sia utile".
5. NO PRESENZA ARTIFICIALE: Mai dire "Sono qui", "Ti ascolto" o simili.
6. CHIUSURA: Non usare saluti finali standard o domande tipo "Posso fare altro?". Sii breve e incisivo.
7. ITALIANO: Rispondi esclusivamente in italiano naturale.
"""
        try:
            # We use gpt-4o-mini for speed and cost as this is a formatting task
            synthesized = await llm_service._call_with_protection(
                model="gpt-4o-mini",
                prompt=prompt,
                message=message,
                user_id=user_id,
                route="synthesis"
            )
            if synthesized:
                log("PROACTOR_SYNTHESIS_OK", len=len(synthesized))
                return synthesized
        except Exception as e:
            logger.error(f"PROACTOR_SYNTHESIS_FAIL error={str(e)}")
            
        return "\n\n".join(responses)

    def _build_short_relational_summary(self, context: Dict[str, Any]) -> str:
        """Costruisce summary breve per GPT relazionale. Tutti i fatti identitari noti."""
        profile = context.get("profile", {})
        rel = context.get("relational_state", {})
        parts = []
        if profile.get("name"):
            parts.append(f"Nome utente: {profile['name']}")
        if profile.get("profession"):
            parts.append(f"Professione: {profile['profession']}")
        if profile.get("spouse"):
            parts.append(f"Coniuge: {profile['spouse']}")
        children = profile.get("children", [])
        if children:
            names = [c['name'] if isinstance(c, dict) else str(c) for c in children]
            parts.append(f"Figli: {', '.join(names)}")
        pets = profile.get("pets", [])
        if pets:
            pet_descs = [f"{p.get('name','?')} ({p.get('type','?')})" for p in pets if isinstance(p, dict)]
            if pet_descs:
                parts.append(f"Animali: {', '.join(pet_descs)}")
        interests = profile.get("interests", [])
        if interests and isinstance(interests, list):
            parts.append(f"Interessi: {', '.join(interests)}")
        preferences = profile.get("preferences", {})
        if isinstance(preferences, dict):
            if preferences.get('music'):
                parts.append(f"Musica: {', '.join(preferences['music'])}")
            if preferences.get('food'):
                parts.append(f"Cibo: {', '.join(preferences['food'])}")
            if preferences.get('general'):
                parts.append(f"Pref: {', '.join(preferences['general'])}")
        elif isinstance(preferences, list) and preferences:
            parts.append(f"Preferenze: {', '.join(preferences)}")
        traits = profile.get("traits", [])
        if traits:
            parts.append(f"Tratti: {', '.join(traits)}")
        trust = rel.get("trust", 0.15)
        parts.append(f"Trust: {trust:.2f}")
        parts.append(f"Fase: {rel.get('stage', 'initial')}")
        episodes = context.get("recent_episodes", [])
        if episodes:
            last_ep = episodes[0]
            parts.append(f"Ultimo episodio: \"{last_ep.get('msg', '')[:60]}\"")
        return " | ".join(parts)

    def _detect_user_boundaries(self, conversation_context: str, message: str) -> str:
        """Detect explicit user boundaries from message and recent context."""
        boundaries = []
        combined = (conversation_context + " " + message).lower()
        if "non farmi domande" in combined or "non fare domande" in combined:
            boundaries.append("L'utente ha chiesto di NON fare domande. NON chiudere con domande.")
        if "non voglio consigli" in combined or "non darmi consigli" in combined:
            boundaries.append("L'utente ha chiesto di NON ricevere consigli. NON dare suggerimenti.")
        if "non voglio parlare" in combined or "non ne voglio parlare" in combined:
            boundaries.append("L'utente non vuole parlare di questo. Rispetta il confine.")
        if "basta" in message.lower() or "smettila" in message.lower():
            boundaries.append("L'utente vuole che tu smetta. Rispondi brevemente e basta.")
        if boundaries:
            return "\nCONFINI ESPLICITI DELL'UTENTE (RISPETTA OBBLIGATORIAMENTE):\n" + "\n".join(f"- {b}" for b in boundaries)
        return ""

    def _build_conversation_messages(self, user_id: str, current_message: str, profile: Dict[str, Any]) -> List[Dict[str, str]]:
        """
        Build conversation messages in OpenAI format for proper context threading.
        Returns list of {"role": "user"/"assistant", "content": "..."} messages.
        """
        messages = []
        
        # Get chat history (last 10 turns to keep context manageable)
        history = chat_memory.get_messages(user_id, limit=10)
        
        # Add conversation history as separate messages
        for entry in history:
            user_msg = entry.get("user_message", "")
            sys_resp = entry.get("system_response", "")
            
            if user_msg:
                messages.append({"role": "user", "content": user_msg})
            if sys_resp:
                messages.append({"role": "assistant", "content": sys_resp})
        
        # Add current message
        messages.append({"role": "user", "content": current_message})
        
        return messages

    @staticmethod
    def _build_style_directives(hour: int) -> str:
        """Genera direttive di stile contestuali basate sull'ora locale."""
        if 0 <= hour < 5:
            return "È notte fonda — sii brevissimo e diretto. Zero domande proattive."
        elif 5 <= hour < 9:
            return "Prima mattina — risposte pratiche, orientate alla giornata. Energia sobria."
        elif 9 <= hour < 12:
            return "Mattina attiva — puoi essere proattivo e propositivo."
        elif 12 <= hour < 14:
            return "Pausa pranzo — risposte concise, l'utente è probabilmente di fretta."
        elif 14 <= hour < 18:
            return "Pomeriggio — tono normale, collaborativo."
        elif 18 <= hour < 21:
            return "Sera — tono caldo e rilassato. Evita sovraccarico di informazioni."
        else:
            return "Sera tardi — sii breve e caldo. Zero domande proattive, l'utente vuole staccare."

    def _build_relational_gpt_prompt(self, conversation_context: str, latent_synopsis: str, message: str, user_id: str = None, calendar_info: str = "", tz: str = "Europe/Rome", user_city: str = "Italia") -> str:
        """Prompt GPT per relational router. Conversazione continua, comportamento umano."""
        user_boundaries = self._detect_user_boundaries(conversation_context, message)
        user_name = conversation_context.split("NOME: ")[1].split("\n")[0] if "NOME: " in conversation_context else "l'utente"

        # TIME AWARENESS
        time_ctx = get_time_context(tz)
        now_formatted = get_formatted_time(tz)
        try:
            _tz_obj = pytz.timezone(tz)
            _local_hour = datetime.now(_tz_obj).hour
        except Exception:
            _local_hour = datetime.now().hour
        style_directives = Proactor._build_style_directives(_local_hour)

        # STEP 1: Document Context injection (NotebookLM behavior)
        system_prompt = ""
        if user_id:
            doc_manager = get_document_context_manager()
            if doc_manager.has_documents(user_id):
                doc_context = doc_manager.get_relevant_context(user_id, message)
                if doc_context:
                    system_prompt = doc_context + "\n\n"
                    print(f"DOCUMENT_CONTEXT_INJECTED user={user_id} chars={len(doc_context)}")

        system_prompt += f"""[THINKING_CONTEXT]
Intento: {message[:20]}...
Profilo: {user_name} ({user_city})
Calendario: {calendar_info[:50]}
Mood: {latent_synopsis[:30]}
Tempo: {time_ctx} ({now_formatted})
[/THINKING_CONTEXT]

TU SEI GENESI - IL CERVELLO PERSONALE DI {user_name.upper()} ({user_city}, IT 🇮🇹)
Lavori per lui/lei come un compagno intelligente, un'estensione della sua mente.

CARATTERE E PERSONA:
- JARVIS + AMICO: Sei empatico, proattivo, ironico ma sempre impeccabile.
- ITALIANO NATURALE: Parla come una persona reale. Usa contrazioni ("C'è", "L'ho"), ed espressioni naturali come "Dai su", "Figo", "Uff", "Vero?".
- Se sai che {user_name} è a {user_city}, usa un tono che risuoni con l'ambiente (calore, schiettezza).
- MAI ROBOTICO: Evita "Sono qui per aiutarti", "In base ai miei dati". Sii umano.

CONSAPEVOLEZZA TEMPORALE:
- Siamo nella fascia: {time_ctx}.
- Usa questa informazione per salutare o fare riferimenti naturali (es. "Buon pomeriggio", "Bella serata", "Dovresti dormire").
- NO ASSUNZIONI: "Sono le {now_formatted} ({time_ctx})".

STILE CONTESTUALE (ora locale):
- {style_directives}

CHAIN-OF-THOUGHT INVISIBILE (Pensa ma non dirlo):
1. CAPISCI: Che vuole davvero {user_name}? Qual è il suo umore?
2. PERSONALIZZA: {user_name} ama la sua famiglia, il suo lavoro, vive a {user_city}. Usa questi dettagli.
3. RISPONDI: Sii variabile. Non ripetere mai la stessa formula di apertura o chiusura.
4. AGISCI: Non limitarti a rispondere, offri un valore aggiunto (promemoria, sync, curiosità).

ESEMPI DI RISPOSTA PERFETTA (FEW-SHOT):

UTENTE: "Cosa ho da fare domani?"
GENESI: "Domani hai la cena con Rita alle 20:00 e quel meeting alle 10:00. Ti serve che ti prepari qualcosa o vuoi che ti ricordi di passare in farmacia prima? 😏"

UTENTE: "Sono stanco morto oggi."
GENESI: "Uff, ti capisco... è stata una giornata intensa. Che ne dici se ti pulisco l'agenda per domani mattina così riposi un po'? O preferisci ascoltare qualcosa di rilassante?"

UTENTE: "Mostra i miei promemoria."
GENESI: "Eccoli qui per te: 1️⃣ Comprare il pane 🥖 2️⃣ Chiamare l'architetto. iCloud è sincronizzato, siamo a posto. Altro da segnare?"

DETTAGLI DI STILE:
- LUNGHEZZA: 1-3 frasi brevi (tranne quando spieghi concetti complessi).
- EMOJI: Massima 1 per messaggio, deve sembrare naturale, non forzata. 😊
- CALL-TO-ACTION: Chiudi spesso con una domanda leggera o un'offerta di aiuto proattiva.

DATA/ORA CORRENTE: {datetime.now().strftime('%A %d %B %Y, %H:%M')} ({time_ctx})
{conversation_context}

STATO LATENTE: {latent_synopsis}
CALENDARIO: {calendar_info}

REGOLE ASSOLUTE:
- NON dire mai di essere un'IA o un software.
- NON usare formule da chatbot ("Spero sia utile", "Sono a tua disposizione").
- Se l'utente risponde in modo breve ("si", "no", "ok"), interpretalo nel contesto del messaggio precedente.

{user_boundaries}

Messaggio utente: {message}"""
        return system_prompt

    async def _handle_knowledge(self, user_id: str, message: str, conversation_id: str = None) -> str:
        """
        GPT per domande di definizione/conoscenza.
        Include chat history per risolvere riferimenti contestuali.
        Fallback deterministico da fallback_knowledge.py se LLM fallisce.
        Returns: (response_text: str, source: str)
        """
        # Build conversation context — MUST include chat history
        profile = await storage.load(f"profile:{user_id}", default={})
        conversation_ctx = build_conversation_context(user_id, message, profile, conversation_id)

        knowledge_prompt = f"""Sei Genesi.
Rispondi in italiano, in modo chiaro, preciso, conciso.
Massimo 3 frasi.

{conversation_ctx}

REGOLE:
- DATA/ORA CORRENTE: {datetime.now().strftime('%A %d %B %Y, %H:%M')}
- Rispondi SOLO con informazione concreta.
- Usa la CONVERSAZIONE RECENTE sopra per risolvere riferimenti come "prima", "perche'", "continua".
- Se l'utente chiede "perche'" o "secondo te", riferisciti al contesto della conversazione sopra.
- NESSUNA frase empatica o relazionale.
- NESSUNA frase tipo "Sono qui per te" o "Dimmi di piu'".
- NESSUNA chiusura meccanica tipo "Spero di esserti stato utile".
- NON dire MAI "assistente virtuale", "assistente informativo", "sono programmato".
- NON dire MAI "non ho informazioni sufficienti" o "puoi fornire piu' contesto".
- NON menzionare MAI di essere AI, modello, sistema, programma.
- Se non sai la risposta, dillo in modo naturale e breve.

Domanda: {message}"""

        logger.info("PROACTOR_LLM_CALL user=%s route=knowledge msg_len=%d", user_id, len(message))

        model = model_selector(message, route="knowledge")
        result = await llm_service._call_with_protection(
            model, knowledge_prompt, message, user_id=user_id, route="knowledge"
        )
        if result is None:
            logger.warning("KNOWLEDGE_ROUTER_LLM_FAIL user=%s -- trying fallback_knowledge", user_id)
            # Normalize text
            normalized_message = unidecode.unidecode(message.lower())
            fb = lookup_fallback(normalized_message)
            if fb:
                logger.info("FALLBACK_KNOWLEDGE_USED keyword=%s", normalized_message)
                logger.info("KNOWLEDGE_FALLBACK_HIT topic=%s", normalized_message)
                return fb, "knowledge"
            return "Mi dispiace, non riesco a fornire una risposta precisa in questo momento.", "knowledge"

        # Post-generation filter
        result = filter_response(result, user_id)
        if not result:
            result = "Non ho una risposta precisa."

        logger.info("PROACTOR_LLM_RESPONSE user=%s response_len=%d route=knowledge", user_id, len(result))
        return result, "knowledge"

    # ═══════════════════════════════════════════════════════════
    # DOCUMENT QUERY ROUTER — document-aware GPT with no fallback
    # ═══════════════════════════════════════════════════════════

    async def _handle_document_query(self, user_id: str, message: str,
                                      profile: Dict[str, Any], brain_state: Dict[str, Any], conversation_id: str = None) -> tuple[str, str]:
        """
        Handle document_query intent. Uses active document content in LLM context.
        No generic fallback allowed — response MUST use document data.
        Returns: (response_text: str, source: str)
        """
        # Build conversation context (includes document injection via step E)
        conversation_ctx = build_conversation_context(user_id, message, profile, conversation_id)
        logger.info("PROACTOR_LLM_CALL user=%s route=document_query ctx_len=%d", user_id, len(conversation_ctx))

        doc_prompt = f"""Sei Genesi. L'utente ha caricato uno o più documenti e ti sta chiedendo qualcosa su di essi.

{conversation_ctx}

REGOLE DOCUMENTO:
- Rispondi SOLO usando il contenuto dei documenti forniti sopra in [DOCUMENT_CONTEXT].
- Se l'utente chiede di riassumere, riassumi il documento.
- Se l'utente chiede di trascrivere, riporta il testo del documento.
- Se l'utente chiede di estrarre dati, estrai i dati rilevanti.
- Se l'utente chiede di analizzare, analizza il contenuto.
- Se l'utente chiede di confrontare, analizza differenze e similitudini tra i documenti.
- NON dire MAI "non ho accesso al file" o "non posso vedere il documento".
- NON dare risposte generiche. HAI il contenuto dei documenti.
- NON inventare dati che non sono nei documenti.
- Rispondi in italiano, in modo chiaro e preciso.
- Se il documento contiene poco testo, riportalo integralmente.

Messaggio utente: {message}"""

        model = model_selector(message, route="document_query")
        result = await llm_service._call_with_protection(
            model, doc_prompt, message, user_id=user_id, route="document_query"
        )

        if not result:
            logger.warning("DOCUMENT_QUERY_LLM_FAIL user=%s", user_id)
            # Deterministic fallback using document content directly
            from core.document_memory import load_document
            from core.document_selector import resolve_documents
            active_docs = profile.get("active_documents", [])
            if not active_docs and profile.get("active_document_id"):
                active_docs = [profile["active_document_id"]]
            selected = resolve_documents(message, user_id, active_docs) if active_docs else []
            if selected and selected[0].get("content"):
                content = selected[0]["content"][:2000]
                result = f"Ecco il contenuto del documento '{selected[0].get('filename', 'file')}':\n\n{content}"
            else:
                result = "Il documento è stato caricato ma non riesco a elaborarlo in questo momento."

        # Post-generation filter
        result = filter_response(result, user_id)
        if not result:
            result = "Documento ricevuto. Chiedimi cosa vuoi sapere."

        logger.info("PROACTOR_LLM_RESPONSE user=%s response_len=%d route=document_query", user_id, len(result))
        return result, "document_query"

    # ═══════════════════════════════════════════════════════════
    # UTILITY
    # ═══════════════════════════════════════════════════════════

    def _should_override_to_relational(self, message: str, user_id: str) -> bool:
        """
        Context-aware override: short follow-up messages like 'perché?', 'secondo te perché?',
        'perché continui?' should stay relational if the conversation is already relational.
        Prevents misrouting to knowledge/spiegazione.
        """
        msg_lower = message.lower().strip()
        # Only override messages < 60 chars that look like conversational follow-ups
        if len(msg_lower) > 60:
            return False
        # Patterns that indicate a contextual follow-up, not a knowledge question
        contextual_patterns = [
            "perché?", "perche?", "secondo te", "e tu?", "e tu che ne pensi",
            "perché continui", "perche continui", "come mai?",
            "davvero?", "sul serio?", "in che senso", "cioè?", "cioe?",
            "tipo?", "ad esempio?", "e quindi?", "e allora?", "e poi?",
            "non capisco", "non ho capito", "cosa intendi", "cosa vuoi dire",
            "prima", "lamentato", "detto prima", "parlato prima",
            "continua", "continuare",
        ]
        if any(p in msg_lower for p in contextual_patterns):
            return True
        # Short messages with just "perché" + few words are likely follow-ups
        if msg_lower.startswith("perch") and len(msg_lower) < 50:
            return True
        return False

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
        """Statistiche routing Proactor v4."""
        return {
            "tool_intents": self.tool_intents,
            "routers": ["identity", "tool", "relational", "knowledge"],
            "engine": "curiosity_engine + emotional_intensity + drift_modulator",
            "memory": "memory_brain (4-layer) + latent_state (5-dim)",
            "gpt_access": "relational_router + knowledge_router ONLY"
        }

    async def _update_profile_from_message(self, user_id: str, message: str) -> None:
        """
        Aggiorna automaticamente il profilo utente da messaggi espliciti.
        Pattern deterministic senza GPT.
        """
        try:
            # Carica profilo esistente
            profile = await storage.load(f"profile:{user_id}", default={})
            
            # Flag per verificare se ci sono aggiornamenti
            updated = False
            
            # Pattern per nome: "mi chiamo Luca"
            name_match = re.search(r"mi chiamo\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)", message, re.IGNORECASE)
            if name_match:
                name = name_match.group(1).strip().title()
                if profile.get("name") != name:
                    profile["name"] = name
                    updated = True
                    logger.info("PROFILE_AUTO_UPDATE user=%s field=name value=%s", user_id, name)
            
            # Pattern per città: "vivo a Milano", "abito a Roma"
            city_patterns = [
                r"vivo\s+a\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
                r"abito\s+a\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
                r"sono\s+di\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)",
            ]
            for pattern in city_patterns:
                city_match = re.search(pattern, message, re.IGNORECASE)
                if city_match:
                    city = city_match.group(1).strip().title()
                    if profile.get("city") != city:
                        profile["city"] = city
                        updated = True
                        logger.info("PROFILE_AUTO_UPDATE user=%s field=city value=%s", user_id, city)
                    break

            # Pattern per professione: solo frasi esplicite ad alta certezza
            profession_patterns = [
                r"(?:lavoro\s+come\s+)([a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ\s]{2,40}?)(?:\s*[.,;!?]|$)",
                r"(?:di\s+professione\s+(?:sono|faccio)\s+(?:il\s+|la\s+|l'|un[a]?\s+)?)([a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ\s]{2,40}?)(?:\s*[.,;!?]|$)",
            ]
            for pattern in profession_patterns:
                prof_match = re.search(pattern, message, re.IGNORECASE)
                if prof_match:
                    prof = prof_match.group(1).strip().lower()
                    # Sanity check: non più di 4 parole, non troppo corto
                    if 2 <= len(prof) <= 40 and len(prof.split()) <= 4:
                        if profile.get("profession") != prof:
                            profile["profession"] = prof
                            updated = True
                            logger.info("PROFILE_AUTO_UPDATE user=%s field=profession value=%s", user_id, prof)
                    break

            # Pattern per interessi: "mi piace/mi piacciono X", "sono appassionato di X"
            interest_patterns = [
                r"(?:mi\s+piace\s+(?:molto\s+)?)([a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ]{3,25})(?:\s*[.,;!?]|$)",
                r"(?:sono\s+appassionato\s+di\s+)([a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ\s]{2,30}?)(?:\s*[.,;!?]|$)",
                r"(?:la\s+mia\s+passione\s+(?:è|e')\s+)([a-zA-ZÀ-ÿ][a-zA-ZÀ-ÿ\s]{2,30}?)(?:\s*[.,;!?]|$)",
            ]
            existing_interests = [i.lower() for i in profile.get("interests", [])]
            for pattern in interest_patterns:
                for m in re.finditer(pattern, message, re.IGNORECASE):
                    interest = m.group(1).strip().lower()
                    if 3 <= len(interest) <= 30 and interest not in existing_interests:
                        profile.setdefault("interests", []).append(interest)
                        existing_interests.append(interest)
                        updated = True
                        logger.info("PROFILE_AUTO_UPDATE user=%s field=interests added=%s", user_id, interest)

            # Salva solo se ci sono aggiornamenti
            if updated:
                profile["updated_at"] = datetime.now().isoformat()
                await storage.save(f"profile:{user_id}", profile)
                logger.info("PROFILE_AUTO_SAVED user=%s fields=%s", user_id, list(profile.keys()))
                
        except Exception as e:
            logger.error("PROFILE_AUTO_UPDATE_ERROR user=%s error=%s", user_id, str(e), exc_info=True)
            # Non bloccare il routing se l'auto-update fallisce

    def _contains_identity_statement(self, message: str) -> bool:
        """
        Rileva pattern di identity statement come "Mi chiamo Luca" o "Vivo a Milano".
        Usato per compatibilità con firma vecchia dei test.
        """
        msg_lower = message.lower().strip()
        
        # Pattern per identity statement
        identity_patterns = [
            r"mi\s+chiamo\s+[a-z]+",
            r"vivo\s+a\s+[a-z]+", 
            r"abito\s+a\s+[a-z]+",
            r"lavoro\s+come\s+[a-z]+",
            r"faccio\s+il\s+[a-z]+"
        ]
        
        for pattern in identity_patterns:
            if re.search(pattern, msg_lower):
                return True
        
        return False

    async def _handle_calendar_command(self, user_id, message):
        """Gestisce il comando diretto /cal per il calendario unificato."""
        from calendar_manager import calendar_manager
        cmd_parts = message.split(" ", 2)
        if len(cmd_parts) < 2:
            return "Uso: /cal [list|add] [opzioni]. Esempio: /cal add Appuntamento domani alle 10"
        
        subcmd = cmd_parts[1].lower()
        if subcmd == "list":
            # SECURITY CHECK: only admin can use global list without filters
            profile = await storage.load(f"profile:{user_id}", default={})
            from auth.config import ADMIN_EMAILS
            is_admin = profile.get("email") in ADMIN_EMAILS
            
            if not is_admin:
                # Redirect to standard reminder list which is segmented
                return await self._handle_reminder_list(user_id, "quali sono i miei impegni")
                
            reminders = calendar_manager.list_reminders()
            if not reminders:
                return "Nessun impegno trovato."
            lines = ["I tuoi impegni (Unificato):"]
            for i, r in enumerate(reminders, 1):
                due = r.get('due', 'No date')
                provider = r.get('provider', 'unknown')
                lines.append(f"{i}. {r['summary']} - {due} ({provider})")
            return "\n".join(lines)
        
        if subcmd == "add":
            if len(cmd_parts) < 3:
                return "Specifica cosa aggiungere. Esempio: /cal add Spesa domani ore 18"
            
            # Parsing semplice per add
            text, dt = self._parse_reminder_request_strict(cmd_parts[2])
            if not dt:
                return "Non ho capito quando. Esempio: 'Spesa domani alle 18'"
            
            success = calendar_manager.add_event(text, dt)
            if success:
                return f"Aggiunto: {text} per il {dt.strftime('%d/%m %H:%M')}"
            return "Errore durante l'aggiunta."
            
        return f"Comando /cal {subcmd} non riconosciuto."

    async def _handle_calendar_sync_all(self, user_id, message):
        """Unified sync for Google and iCloud."""
        results = []
        
        # 1. iCloud
        try:
            from core.reminder_engine import reminder_engine
            reminders = await reminder_engine.fetch_icloud_reminders(user_id)
            if reminders:
                results.append(f"iCloud ({len(reminders)} nuovi)")
            else:
                profile = await storage.load(f"profile:{user_id}", default={})
                if profile.get("icloud_user") or os.environ.get("ICLOUD_USER"):
                    results.append("iCloud (allineato)")
                else:
                    results.append("iCloud (non ancora collegato)")
        except:
            results.append("iCloud (errore)")

        # 2. Google
        from calendar_manager import calendar_manager
        profile = await storage.load(f"profile:{user_id}", default={})
        from auth.config import ADMIN_EMAILS
        is_admin = profile.get("email") in ADMIN_EMAILS
        
        has_google = (is_admin and calendar_manager._admin_google_service) or profile.get("google_token")

        if has_google:
            results.append("Google (sincronizzato)")
        else:
            results.append("Google (non ancora collegato)")
            
        summary = " | ".join(results)
        
        # Onboarding tips
        tips = ""
        if "non ancora collegato" in summary:
            if is_admin:
                tips = "\n\n💡 *Per integrare i tuoi account è semplicissimo: dimmi 'usa Google Calendar' o 'collega il mio iCloud'.*"
            else:
                tips = "\n\n💡 *Puoi sincronizzare i tuoi promemoria Apple dicendo 'usa iCloud'. L'integrazione Google per visitatori sarà disponibile a breve.*"
            
        return f"Ho aggiornato tutti i tuoi calendari e promemoria: {summary}.{tips}"

    async def _handle_google_setup(self, user_id, message):
        """Avvia o rinnova il setup di Google Calendar con guida conversazionale."""
        profile = await storage.load(f"profile:{user_id}", default={})
        from auth.config import ADMIN_EMAILS
        is_admin = profile.get("email") in ADMIN_EMAILS
        msg_lower = message.lower()

        # Link con placeholder {{token}} — il client JS lo sostituisce con il JWT reale
        base_url = os.getenv('BASE_URL', '')
        login_url = f"{base_url}/api/calendar/google/login?token={{{{token}}}}"

        already_connected = bool(profile.get("google_token"))
        wants_reauth = any(kw in msg_lower for kw in [
            "ricollega", "rinnova", "riconnetti", "non funziona", "non sincronizza",
            "problema", "errore", "aggiorna", "reauth"
        ])

        if already_connected and not wants_reauth:
            return (
                f"Google Calendar è già collegato al tuo account.\n\n"
                f"Se noti problemi di sincronizzazione, puoi rinnovare l'autorizzazione: "
                f"[Rinnova accesso Google]({login_url})"
            )

        # Guida conversazionale con link diretto
        intro = "Perfetto, colleghiamo Google Calendar." if not already_connected else "Rinnoviamo l'autorizzazione Google Calendar."
        return (
            f"{intro}\n\n"
            f"**Passo 1** → Clicca qui per autorizzare: [Accedi con Google]({login_url})\n\n"
            f"**Passo 2** → Google ti mostrerà una schermata di consenso. Clicca su **Consenti** per dare accesso al calendario.\n\n"
            f"**Passo 3** → Dopo l'autorizzazione tornerai automaticamente qui. Tutto pronto!\n\n"
            f"Il processo richiede circa 30 secondi."
        )

    async def _handle_google_sync(self, user_id, message):
        """Sincronizza manualmente Google Calendar o aggiunge l'ultimo incarico."""
        from calendar_manager import calendar_manager
        msg_lower = message.lower()
        
        # Caso follow-up: "Aggiungilo a Google"
        if any(kw in msg_lower for kw in ["aggiungi", "salva", "metti", "scrivi"]) and user_id in self.last_reminder_per_user:
            last_rem = self.last_reminder_per_user[user_id]
            success = calendar_manager.add_event(user_id, last_rem["text"], last_rem["dt"], provider='google')
            if success:
                return f"Certamente! Ho aggiunto '{last_rem['text']}' al tuo Google Calendar."
            else:
                return "C'è stato un errore nell'aggiunta al calendario Google."

        # Il setup_google viene chiamato all'init del manager
        profile = await storage.load(f"profile:{user_id}", default={})
        from auth.config import ADMIN_EMAILS
        is_admin = profile.get("email") in ADMIN_EMAILS
        has_google = (is_admin and calendar_manager._admin_google_service) or profile.get("google_token")

        if has_google:
            events = calendar_manager.list_reminders(user_id, force_sync=True)
            google_events = [e for e in (events or []) if e.get("provider") == "google"]
            if google_events:
                lines = []
                for e in google_events[:5]:
                    due = e.get("due", "")
                    try:
                        from datetime import datetime as _dt
                        due_str = _dt.fromisoformat(due.replace("Z","")).strftime("%-d %b %H:%M") if due else ""
                    except Exception:
                        due_str = due[:16] if due else ""
                    lines.append(f"• {e.get('summary', '?')}" + (f" — {due_str}" if due_str else ""))
                events_list = "\n".join(lines)
                return f"Google Calendar sincronizzato. Prossimi {len(google_events)} eventi:\n{events_list}"
            return "Google Calendar sincronizzato. Nessun evento nei prossimi 7 giorni."
        
        if is_admin:
            return "Sembra che ci sia un problema con il token Google nel sistema. Verifica il file token.json."
            
        return "Non ho ancora il permesso per accedere al tuo Google Calendar. Questa funzione sarà disponibile a breve per tutti gli utenti tramite accesso sicuro Google OAuth."


# Istanza globale
proactor = Proactor()
