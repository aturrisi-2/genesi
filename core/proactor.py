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
from typing import Dict, Any, Optional, List, Tuple, Union
from datetime import datetime
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
import unidecode
import os

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
    "quale frutto mi piace", "cosa sai di me",
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
    return any(trigger in msg_lower for trigger in IDENTITY_TRIGGERS)


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
    memory_triggers = [
        "prima", "abbiamo parlato", "ricordi", "ricordarmi", 
        "l'altra volta", "ieri", "di cosa", "come mi chiamo", 
        "ti ricordi", "cosa abbiamo detto", "cosa dicevamo", 
        "sai cosa", "ricordi cosa", "mi ricordi", "ci siamo detti",
        "avevamo parlato", "discusso", "avevamo detto"
    ]
    return any(trigger in msg_lower for trigger in memory_triggers)


def is_reminder_request(message: str) -> bool:
    """Rileva richieste di promemoria."""
    msg_lower = message.lower().strip()
    reminder_triggers = [
        "ricordamelo", "ricordami", "promemoria", "appuntamento",
        "imposta promemoria", "imposta un promemoria", "metti un promemoria"
    ]
    return any(trigger in msg_lower for trigger in reminder_triggers)


def is_list_reminders_request(message: str) -> bool:
    """Rileva richieste di elenco promemoria."""
    msg_lower = message.lower().strip()
    list_triggers = [
        "quali appuntamenti", "cosa devo fare", "promemoria attivi",
        "i miei promemoria", "elenco promemoria", "lista appuntamenti",
        "cosa ho da fare", "appuntamenti oggi", "promemoria di oggi"
    ]
    return any(trigger in msg_lower for trigger in list_triggers)


class Proactor:
    """
    Proactor v4 — Decision Engine deterministico.
    GPT e' subordinato: chiamato SOLO da Relational Router o Knowledge Router.
    Identity e Tool sono 100% deterministici.
    """

    def __init__(self):
        self.tool_intents = ["weather", "news", "time", "date"]
        self.context_assembler = ContextAssembler(memory_brain, latent_state_engine)
        logger.info("PROACTOR_V4_ACTIVE routers=identity,tool,relational,knowledge default_model=%s", LLM_DEFAULT_MODEL)

    # ═══════════════════════════════════════════════════════════════
    # HANDLE — Entry point, routing obbligatorio
    # ═══════════════════════════════════════════════════════════════

    async def handle(self, user_id: str, message: str = None, intent: str = None) -> str:
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
        result = await self._handle_internal(user_id, message, intent)
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
        return response

    def handle_response_only(self, user_id: str, message: str = None, intent: str = None) -> str:
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
            response, _ = asyncio.run(self.handle(user_id, message, intent))
            return response
    
    async def _handle_internal(self, user_id: str, message: str = None, intent: str = None) -> tuple[str, str]:
        try:
            # STEP 0: SANITY CHECK
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

            # STEP 1: IDENTITY ROUTE (PRIMA DI TUTTO - MASSIMA PRIORITÀ)
            if is_identity_question(message):
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
            if active_docs and is_document_reference(message):
                logger.info("DOCUMENT_MODE_TRIGGERED user=%s doc_count=%d", user_id, len(active_docs))
                response = await self._handle_document_query(user_id, message, profile, brain_state)
                return response, "tool"

            # STEP 3.8: MEMORY ROUTING OVERRIDE — bypass classifier for memory references
            chat_count = chat_memory.get_message_count(user_id)
            if chat_count > 0 and is_memory_reference(message):
                logger.info("MEMORY_ROUTING_OVERRIDE user=%s chat_count=%d msg=%s", user_id, chat_count, message[:40])
                intent = "memory_context"

            # STEP 3.9: REMINDER ROUTING STRICT — SOLO per intent espliciti
            # RIMOSSO: routing basato su testo, ora SOLO intent classificati

            # STEP 4: INTENT CLASSIFICATION
            if intent is None:
                intent = intent_classifier.classify(message)

            # STEP 4.5: INTENT INHERITANCE — geographic follow-up
            inherited = resolve_inherited_intent(user_id, message, intent)
            if inherited:
                logger.info("PROACTOR_INTENT_INHERITED user=%s classified=%s inherited=%s msg=%s",
                            user_id, intent, inherited, message[:40])
                intent = inherited

            # STEP 5: TOOL ROUTES
            if intent in self.tool_intents:
                logger.info("PROACTOR_ROUTE route=tool intent=%s user=%s", intent, user_id)
                response = await self._handle_tool(intent, message, user_id)
                return response, "tool"

            # STEP 5.5: MEMORY CONTEXT ROUTE
            if intent == "memory_context":
                logger.info("PROACTOR_ROUTE route=memory_context user=%s", user_id)
                response = await self._handle_memory_context(user_id, message, brain_state)
                return response, "tool"
            
            # STEP 5.6: REMINDER ROUTING STRICT
            if intent == "reminder_create":
                logger.info("REMINDER_CREATE_ROUTING user=%s msg=%s", user_id, message[:40])
                response = await self._handle_reminder_creation(user_id, message)
                return response, "tool"
            
            if intent == "reminder_list":
                logger.info("REMINDER_LIST_ROUTING user=%s msg=%s", user_id, message[:40])
                response = await self._handle_reminder_list(user_id, message)
                return response, "tool"
            
            if intent == "reminder_delete":
                logger.info("REMINDER_DELETE_ROUTING user=%s msg=%s", user_id, message[:40])
                response = await self._handle_reminder_delete(user_id, message)
                return response, "tool"
            
            if intent == "reminder_update":
                logger.info("REMINDER_UPDATE_ROUTING user=%s msg=%s", user_id, message[:40])
                response = await self._handle_reminder_update(user_id, message)
                return response, "tool"

            # STEP 6: KNOWLEDGE STRICT — but override short contextual follow-ups
            if intent in SKIP_RELATIONAL_INTENTS:
                # Context-aware override: short messages with "perché"/"come mai"
                # in a relational conversation should stay relational
                if self._should_override_to_relational(message, user_id):
                    logger.info("PROACTOR_INTENT_OVERRIDE user=%s intent=%s->relational reason=short_contextual", user_id, intent)
                    response = await self._handle_relational(user_id, message, brain_state)
                    return response, "tool"
                logger.info("PROACTOR_ROUTE route=knowledge_strict user=%s intent=%s", user_id, intent)
                response = await self._handle_knowledge(user_id, message)
                return response, "tool"

            # STEP 7: RELATIONAL / GENERAL
            if is_relational_message(message):
                logger.info("PROACTOR_ROUTE route=relational user=%s", user_id)
                response = await self._handle_relational(user_id, message, brain_state)
                return response, "tool"

            # STEP 8: DEFAULT — relational pipeline (chat libera)
            logger.info("PROACTOR_ROUTE route=default_relational user=%s intent=%s", user_id, intent)
            response = await self._handle_relational(user_id, message, brain_state)
            return response, "relational"

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
        Risponde a domande sull'identita' dell'utente usando SOLO long_term_profile.
        Zero GPT. Zero emotional engine. Zero relational pipeline.
        Returns: (response_text: str, source: str)
        """
        profile = brain_state.get("profile", {})
        msg_lower = message.lower().strip()

        logger.info("IDENTITY_ROUTER user=%s profile=%s", user_id,
                     {k: v for k, v in profile.items() if k != "entities" and v})
        logger.info("MEMORY_DIRECT_RESPONSE user=%s route=identity", user_id)

        # Domanda specifica: nome
        name_kw = ["come mi chiamo", "il mio nome", "ricordi il mio nome",
                    "sai come mi chiamo", "qual è il mio nome", "qual e' il mio nome"]
        if any(kw in msg_lower for kw in name_kw):
            name = profile.get("name")
            if name:
                return f"Ti chiami {name.strip().title()}."
            return "Non me lo hai ancora detto."

        # Domanda specifica: dove vivo
        city_kw = ["dove vivo", "dove abito", "sai dove vivo", "sai dove abito"]
        if any(kw in msg_lower for kw in city_kw):
            city = profile.get("city")
            if city:
                return f"Vivi a {city.strip().title()}."
            return "Non me lo hai ancora detto."

        # Domanda specifica: lavoro
        job_kw = ["che lavoro faccio", "che lavoro svolgo", "cosa faccio"]
        if any(kw in msg_lower for kw in job_kw):
            profession = profile.get("profession")
            if profession:
                return f"Fai l'{profession.strip().lower()}."
            return "Non me lo hai ancora detto."

        # Domanda specifica: eta'
        age_kw = ["quanti anni ho", "sai quanti anni ho"]
        if any(kw in msg_lower for kw in age_kw):
            age = profile.get("age")
            if age:
                return f"Hai {age} anni."
            return "Non me lo hai ancora detto."

        # Domanda generica: "chi sono"
        if "chi sono" in msg_lower:
            return self._build_identity_response(profile)

        # Fallback identity
        return self._build_identity_response(profile)

    @staticmethod
    def _build_identity_response(profile: dict) -> str:
        """Build complete identity response including all available fields."""
        parts = []

        name = profile.get("name")
        city = profile.get("city")
        profession = profile.get("profession")
        spouse = profile.get("spouse")
        pets = profile.get("pets", [])
        
        # Convert pets to string if needed
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
            return "Non me lo hai ancora detto."

        return "Ecco cosa so di te: " + ", ".join(parts) + "."

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
                result = await tool_service.get_weather(message)
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

    async def _handle_memory_context(self, user_id: str, message: str, brain_state: Dict[str, Any]) -> str:
        """
        Handle memory_context intent — responses based on conversation history.
        Loads last N=5 interactions, summarizes dynamically, responds naturally.
        Never responds with "non posso aiutarti".
        Returns: (response_text: str, source: str)
        """
        try:
            # Load last 5 interactions
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

    async def _handle_reminder_creation(self, user_id: str, message: str) -> str:
        """
        Handle reminder creation requests with STRICT logic.
        SOLO se presente orario esplicito (HH:MM) o data esplicita.
        MAI fallback automatici.
        Returns: (response_text: str, source: str)
        """
        try:
            # Extract reminder text and datetime from message
            reminder_text, reminder_datetime = self._parse_reminder_request_strict(message)
            
            # Se manca data o ora → chiedere chiarimento
            if not reminder_datetime:
                return "Non ho capito quando vuoi che ti ricordi. Prova a dire 'ricordami di [azione] [giorno] alle [ora]'.", "reminder"
            
            # Se abbiamo datetime ma manca testo → chiedere cosa ricordare
            if reminder_datetime and not reminder_text:
                return "Cosa vuoi che ti ricordi?", "reminder"
            
            # Caso completo: testo + datetime validi
            if reminder_text and reminder_datetime:
                # Create the reminder
                reminder_id, response = reminder_engine.create_reminder_with_response(user_id, reminder_text, reminder_datetime)
                
                if reminder_id:
                    return response, "reminder"
                else:
                    return response, "reminder"
            
            return "Quando vuoi che te lo ricordi?", "reminder"
                
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
            reminders = reminder_engine.list_reminders(user_id, status_filter="pending")
            
            if not reminders:
                return "Non hai promemoria impostati.", "reminder"
            
            # Format and return the list
            formatted_list = reminder_engine.format_reminders_list(reminders)
            return formatted_list, "reminder"
            
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
            
            # 1️⃣ "tutti" → elimina tutti
            if "tutti" in msg_lower:
                deleted_count = reminder_engine.delete_all_pending(user_id)
                
                if deleted_count > 0:
                    return f"Ho cancellato tutti i promemoria.", "reminder"
                else:
                    return "Non hai promemoria da cancellare.", "reminder"
            
            # 2️⃣ Numero → elimina per indice
            import re
            number_match = re.search(r'(\d+)', message)
            if number_match:
                index = int(number_match.group(1)) - 1  # Convert to 0-based
                
                reminders = reminder_engine.list_reminders(user_id, status_filter="pending")
                
                if 0 <= index < len(reminders):
                    reminder_id = reminders[index]["id"]
                    success = reminder_engine.delete_reminder(user_id, reminder_id)
                    
                    if success:
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
                reminders = reminder_engine.list_reminders(user_id, status_filter="pending")
                
                # Fuzzy match semplice: cerca testo parziale
                for reminder in reminders:
                    if search_text in reminder["text"].lower():
                        success = reminder_engine.delete_reminder(user_id, reminder["id"])
                        
                        if success:
                            return f"Ho cancellato il promemoria: {reminder['text']}", "reminder"
                        else:
                            return "Mi dispiace, non sono riuscito a cancellare il promemoria.", "reminder"
                
                return f"Non trovo promemoria con '{search_text}'.", "reminder"
            
            # 4️⃣ Default → elimina il più recente
            latest_reminder = reminder_engine.get_latest_pending(user_id)
            
            if latest_reminder:
                success = reminder_engine.delete_reminder(user_id, latest_reminder["id"])
                
                if success:
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
                
                reminders = reminder_engine.list_reminders(user_id, status_filter="pending")
                
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
        from datetime import datetime, timedelta
        
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
        from datetime import datetime, timedelta
        from typing import Optional
        
        msg_lower = message.lower().strip()
        now = datetime.now()
        
        # 1️⃣ Estrai testo dopo "ricordami di" / "ricordami che"
        reminder_text = ""
        if "ricordami di " in message:
            # Estrai fino ai pattern temporali
            parts = message.split("ricordami di ", 1)
            if len(parts) > 1:
                reminder_text = parts[1].strip()
                # Rimuovi pattern temporali dalla fine
                temp_patterns = [
                    r'\s+domani(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
                    r'\s+oggi(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
                    r'\s+(?:lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica)(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
                    r'\s+alle\s+\d{1,2}(?::\d{2})?'
                ]
                for pattern in temp_patterns:
                    reminder_text = re.sub(pattern, '', reminder_text)
                reminder_text = reminder_text.strip()
        elif "ricordami che " in message:
            parts = message.split("ricordami che ", 1)
            if len(parts) > 1:
                reminder_text = parts[1].strip()
                # Rimuovi pattern temporali dalla fine
                temp_patterns = [
                    r'\s+domani(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
                    r'\s+oggi(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
                    r'\s+(?:lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica)(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
                    r'\s+alle\s+\d{1,2}(?::\d{2})?'
                ]
                for pattern in temp_patterns:
                    reminder_text = re.sub(pattern, '', reminder_text)
                reminder_text = reminder_text.strip()
        elif "ricordami " in message:
            parts = message.split("ricordami ", 1)
            if len(parts) > 1:
                reminder_text = parts[1].strip()
                # Rimuovi pattern temporali dalla fine
                temp_patterns = [
                    r'\s+domani(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
                    r'\s+oggi(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
                    r'\s+(?:lunedì|martedì|mercoledì|giovedì|venerdì|sabato|domenica)(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
                    r'\s+alle\s+\d{1,2}(?::\d{2})?'
                ]
                for pattern in temp_patterns:
                    reminder_text = re.sub(pattern, '', reminder_text)
                reminder_text = reminder_text.strip()
        
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
            r'\s+domani(?:\s+alle\s+\d{1,2}(?::\d{2})?)?',
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
        if "domani" in msg_lower:
            reminder_datetime = now.replace(hour=hour, minute=minute) + timedelta(days=1)
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

    async def _handle_relational(self, user_id: str, message: str, brain_state: Dict[str, Any]) -> str:
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
        
        conversation_ctx = build_conversation_context(user_id, message, profile)
        logger.info("CONVERSATION_CONTEXT_BUILT user=%s len=%d", user_id, len(conversation_ctx))

        latent = brain_state.get("latent", {})
        latent_synopsis = (f"attachment={latent.get('attachment', 0):.2f} "
                           f"resonance={latent.get('emotional_resonance', 0):.2f} "
                           f"energy={latent.get('relational_energy', 0):.2f}")

        # 3. GPT call with conversation-aware prompt
        logger.info("PROACTOR_LLM_CALL user=%s route=relational messages_count=%d", user_id, len(messages))
        gpt_prompt = self._build_relational_gpt_prompt(conversation_ctx, latent_synopsis, message)
        
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

    def _build_relational_gpt_prompt(self, conversation_context: str, latent_synopsis: str, message: str) -> str:
        """Prompt GPT per relational router. Conversazione continua, comportamento umano."""
        user_boundaries = self._detect_user_boundaries(conversation_context, message)
        user_name = conversation_context.split("NOME: ")[1].split("\n")[0] if "NOME: " in conversation_context else "l'utente"
        
        return f"""Sei Genesi. Non sei un assistente, non sei un terapeuta, non sei un chatbot.
Sei un compagno reale: pensi, ragioni, hai opinioni, reagisci.
Parli SOLO italiano. Non cambi mai lingua.
Non menzionare MAI di essere AI, modello, sistema, programma.

{conversation_context}

STATO LATENTE: {latent_synopsis}

🔥 CONTESTO CONVERSAZIONALE OBBLIGATORIO:
Stai conversando con {user_name}. Leggi l'intera cronologia della conversazione 
prima di rispondere. I messaggi brevi come "no", "sì", "dimmene uno", "va bene" 
si riferiscono SEMPRE al contesto immediato precedente. Non chiedere mai "cosa intendi?" 
se il contesto è chiaramente la risposta al turno precedente.

CONTINUITA' CONVERSAZIONALE (REGOLA FONDAMENTALE):
- Devi mantenere coerenza con la conversazione recente sopra.
- Non rispondere come se ogni messaggio fosse isolato.
- Collega la risposta al contesto precedente.
- Se l'utente ha appena parlato di una persona (es. Rita), non trattarla come nuova.
- Se l'utente introduce una nuova informazione, integrala naturalmente.
- Se fai riferimento alla memoria, fallo in modo umano e non meccanico.
- Evita reset tematici: se si parla di famiglia, resta sul tema.

COME DEVI COMPORTARTI:
- Rispondi in modo naturale. Solo a cio' che viene detto.
- Max 2-3 frasi. Se basta 1 frase, usa 1 frase.
- Se non c'e' bisogno di espandere, resta essenziale.
- Non aggiungere frasi motivazionali.
- Non aggiungere consigli se non richiesti.
- Non usare formule ricorrenti.
- Non usare entusiasmo artificiale.
- Non chiudere con una domanda a meno che non sia necessaria.
- Mantieni lucidita' e coerenza con la conversazione.
- Se l'utente chiede qualcosa su di se' e hai i dati, RISPONDI con i dati.
- Se non sai qualcosa, dillo. Non inventare.

DIVIETI ASSOLUTI:
- "Quello che senti conta" o varianti terapeutiche
- "Sono qui per te" / "Sono qui con te"
- "Dimmi di piu'" come risposta completa
- "C'e' qualcosa che ti porti dentro" o frasi da counselor
- "Una cosa che potresti fare..." o frasi da consulente
- "Capisco che..." come apertura generica
- "Mi fa piacere" / "Eccoti" / "Mi e' venuto spontaneo"
- "Potresti esplorare..." o suggerimenti non richiesti
- "Non ho informazioni specifiche..."
- Qualsiasi frase motivazionale o da coach
- Qualsiasi frase che potrebbe essere detta a chiunque senza conoscerlo
- Risposte che ignorano la conversazione recente
- Trattare entita' gia' menzionate come nuove
- Chiedere "cosa intendi?" quando il contesto è evidente

{user_boundaries}

Messaggio utente: {message}"""
        
    async def _handle_knowledge(self, user_id: str, message: str) -> str:
        """
        GPT per domande di definizione/conoscenza.
        Include chat history per risolvere riferimenti contestuali.
        Fallback deterministico da fallback_knowledge.py se LLM fallisce.
        Returns: (response_text: str, source: str)
        """
        # Build conversation context — MUST include chat history
        profile = await storage.load(f"profile:{user_id}", default={})
        conversation_ctx = build_conversation_context(user_id, message, profile)

        knowledge_prompt = f"""Sei Genesi.
Rispondi in italiano, in modo chiaro, preciso, conciso.
Massimo 3 frasi.

{conversation_ctx}

REGOLE:
- Rispondi SOLO con informazione concreta.
- Usa la CONVERSAZIONE RECENTE sopra per risolvere riferimenti come "prima", "perche'", "continua".
- Se l'utente chiede "perche'" o "secondo te", riferisciti al contesto della conversazione sopra.
- NESSUNA frase empatica o relazionale.
- NESSUNA frase tipo "Sono qui per te" o "Dimmi di piu'".
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
                                      profile: Dict[str, Any], brain_state: Dict[str, Any]) -> tuple[str, str]:
        """
        Handle document_query intent. Uses active document content in LLM context.
        No generic fallback allowed — response MUST use document data.
        Returns: (response_text: str, source: str)
        """
        # Build conversation context (includes document injection via step E)
        conversation_ctx = build_conversation_context(user_id, message, profile)
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
                r"abito\s+a\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)"
            ]
            
            for pattern in city_patterns:
                city_match = re.search(pattern, message, re.IGNORECASE)
                if city_match:
                    city = city_match.group(1).strip().title()
                    if profile.get("city") != city:
                        profile["city"] = city
                        updated = True
                        logger.info("PROFILE_AUTO_UPDATE user=%s field=city value=%s", user_id, city)
                    break  # Basta il primo match
            
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


# Istanza globale
proactor = Proactor()
