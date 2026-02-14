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
from typing import Dict, Any, Optional
from core.log import log
from core.memory_brain import memory_brain
from core.latent_state import latent_state_engine
from core.drift_modulator import drift_modulator
from core.curiosity_engine import curiosity_engine
from core.emotional_intensity_engine import emotional_intensity_engine
from core.tool_services import tool_service
from core.storage import storage
from core.context_assembler import ContextAssembler, build_conversation_context
from core.llm_service import llm_service, model_selector, LLM_DEFAULT_MODEL
from core.fallback_knowledge import lookup_fallback
from core.identity_service import handle_identity_question
from core.response_filter import filter_response
from core.tool_context import (save_tool_context, resolve_elliptical_city,
                               is_elliptical_weather_followup,
                               is_elliptical_news_followup, resolve_elliptical_news)
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

    async def handle(self, user_id: str, message: str, intent: str = None) -> str:
        """
        Orchestrazione centrale v4.
        Ordine di routing:
            1. Identity Router  (deterministico)
            2. Tool Router      (deterministico)
            3. Strict Knowledge (skip relational)
            4. Knowledge Router (GPT pulito)
            5. Relational Router (GPT controllato)
            6. Default Relational (chat libera)
        """
        try:
            # STEP 0: SANITY CHECK
            if not user_id:
                raise ValueError("Proactor received empty user_id")
            msg_lower = message.lower().strip()

            logger.info("PROACTOR_HANDLE_ENTRY user=%s intent=%s", user_id, intent)

            # STEP 1: IDENTITY ROUTE PRIORITY
            identity_response = await handle_identity_question(user_id, message)
            if identity_response:
                logger.info("IDENTITY_ROUTE_EXECUTION_ORDER_OK user=%s", user_id)
                return identity_response

            # STEP 2: MEMORY UPDATE
            brain_state = await memory_brain.update_brain(user_id, message)
            if brain_state is None:
                brain_state = {"profile": {}, "latent": {}, "relational": {}}
            logger.info("PROACTOR_MEMORY_UPDATED user=%s profile_name=%s trust=%.3f episodes=%d",
                        user_id,
                        brain_state.get('profile', {}).get('name', 'unknown'),
                        brain_state.get('relational', {}).get('trust', 0),
                        len(brain_state.get('episodes', [])))

            # Load the profile from persistent storage
            profile = await storage.load(f"profile:{user_id}", default={})
            logger.info("PROFILE_LOADED user_id=%s", user_id)

            # Use the profile in the context assembly
            context = await self.context_assembler.build(user_id, message)
            context['profile'] = profile

            # STEP 2.5: ELLIPTICAL TOOL FOLLOW-UP (e.g. "e domani?" after weather)
            if is_elliptical_weather_followup(msg_lower):
                resolved_city = resolve_elliptical_city(user_id, msg_lower)
                if resolved_city:
                    logger.info("ELLIPTICAL_WEATHER_FOLLOWUP user=%s city=%s", user_id, resolved_city)
                    enriched_msg = f"che tempo fa a {resolved_city} {message.strip('?').strip()}"
                    return await self._handle_tool("weather", enriched_msg, user_id)

            # STEP 2.6: ELLIPTICAL NEWS FOLLOW-UP (e.g. "e di politica?" after news)
            if is_elliptical_news_followup(msg_lower):
                resolved_topic = resolve_elliptical_news(user_id, msg_lower)
                if resolved_topic:
                    logger.info("ELLIPTICAL_NEWS_FOLLOWUP user=%s topic=%s", user_id, resolved_topic)
                    enriched_msg = f"notizie {resolved_topic}"
                    return await self._handle_tool("news", enriched_msg, user_id)

            # STEP 3: INTENT CLASSIFICATION
            if intent is None:
                intent = await intent_classifier.classify(message)

            # STEP 4: TOOL ROUTES
            if intent in self.tool_intents:
                logger.info("PROACTOR_ROUTE route=tool intent=%s user=%s", intent, user_id)
                return await self._handle_tool(intent, message, user_id)

            # STEP 5: KNOWLEDGE STRICT — but override short contextual follow-ups
            if intent in SKIP_RELATIONAL_INTENTS:
                # Context-aware override: short messages with "perché"/"come mai"
                # in a relational conversation should stay relational
                if self._should_override_to_relational(message, user_id):
                    logger.info("PROACTOR_INTENT_OVERRIDE user=%s intent=%s->relational reason=short_contextual", user_id, intent)
                    return await self._handle_relational(user_id, message, brain_state)
                logger.info("PROACTOR_ROUTE route=knowledge_strict user=%s intent=%s", user_id, intent)
                return await self._handle_knowledge(user_id, message)

            # STEP 6: RELATIONAL / GENERAL
            if is_relational_message(message):
                logger.info("PROACTOR_ROUTE route=relational user=%s", user_id)
                return await self._handle_relational(user_id, message, brain_state)

            # STEP 7: DEFAULT — relational pipeline (chat libera)
            logger.info("PROACTOR_ROUTE route=default_relational user=%s intent=%s", user_id, intent)
            return await self._handle_relational(user_id, message, brain_state)

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
            return f"{prefix}Mi dispiace, ho avuto un problema. Riprova tra poco."

    # ═══════════════════════════════════════════════════════════════
    # IDENTITY ROUTER — 100% deterministico, zero GPT
    # ═══════════════════════════════════════════════════════════════

    async def _handle_identity(self, user_id: str, message: str, brain_state: Dict[str, Any]) -> str:
        """
        Risponde a domande sull'identita' dell'utente usando SOLO long_term_profile.
        Zero GPT. Zero emotional engine. Zero relational pipeline.
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
                return f"Lavori come {profession.strip().lower()}."
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
            return self._build_identity_summary(profile)

        # Fallback identity
        return self._build_identity_summary(profile)

    def _build_identity_summary(self, profile: Dict[str, Any]) -> str:
        """Costruisce riepilogo identita' da profilo. Zero GPT."""
        facts = []
        if profile.get("name"):
            facts.append(f"ti chiami {profile['name'].strip().title()}")
        if profile.get("age"):
            facts.append(f"hai {profile['age']} anni")
        if profile.get("city"):
            facts.append(f"vivi a {profile['city'].strip().title()}")
        if profile.get("profession"):
            facts.append(f"lavori come {profile['profession'].strip().lower()}")
        entities = profile.get("entities", {})
        for role, data in entities.items():
            name = data.get("name")
            if name:
                role_labels = {"moglie": "tua moglie", "marito": "tuo marito",
                               "figlio": "tuo figlio", "figlia": "tua figlia",
                               "amico": "il tuo amico", "amica": "la tua amica",
                               "madre": "tua madre", "padre": "tuo padre"}
                label = role_labels.get(role, role)
                facts.append(f"{label} si chiama {name}")

        if facts:
            return f"Ecco cosa so di te: {', '.join(facts)}."
        return "Non so ancora molto di te. Raccontami qualcosa."

    # ═══════════════════════════════════════════════════════════════
    # TOOL ROUTER — 100% deterministico, zero GPT su errore
    # ═══════════════════════════════════════════════════════════════

    async def _handle_tool(self, intent: str, message: str, user_id: str) -> str:
        """
        Tool routing deterministico.
        Errori gestiti con messaggi deterministici, MAI GPT.
        """
        try:
            if intent == "weather":
                result = await tool_service.get_weather(message)
                # Save tool context for follow-up
                city = tool_service._extract_city(message) or "Roma"
                save_tool_context(user_id, "weather", city=city)
                logger.info("TOOL_ROUTER_OK intent=weather user=%s city=%s", user_id, city)
                return result
            elif intent == "news":
                result = await tool_service.get_news(message)
                save_tool_context(user_id, "news")
                logger.info("TOOL_ROUTER_OK intent=news user=%s", user_id)
                return result
            elif intent == "time":
                return await tool_service.get_time()
            elif intent == "date":
                return await tool_service.get_date()
            else:
                return "Tool non disponibile."
        except Exception as e:
            logger.error("PROACTOR_TOOL_ERROR intent=%s user=%s error=%s", intent, user_id, str(e), exc_info=True)
            if intent == "weather":
                return "Il servizio meteo non è disponibile al momento."
            elif intent == "news":
                return "Il servizio notizie non è configurato correttamente."
            return f"Errore nel servizio {intent}."

    # ═══════════════════════════════════════════════════════════
    # RELATIONAL ROUTER — GPT controllato con contesto limitato
    # ═══════════════════════════════════════════════════════════

    async def _handle_relational(self, user_id: str, message: str, brain_state: Dict[str, Any]) -> str:
        """
        Pipeline relazionale con GPT controllato.
        GPT riceve: conversation thread, identity summary, topic, latent state.
        GPT NON inventa memoria.
        """
        # 1. Context Assembler — structured context from memory
        context = await self.context_assembler.build(user_id, message)
        logger.info("CONTEXT_ASSEMBLED user=%s summary_len=%d", user_id, len(context.get('summary', '')))

        # Inject into brain_state for backward compatibility
        brain_state["relational_context"] = context["summary"]
        brain_state["assembled_context"] = context

        # 2. Build conversation context with chat history + profile + topic
        profile = context.get("profile", {})
        conversation_ctx = build_conversation_context(user_id, message, profile)
        logger.info("CONVERSATION_CONTEXT_BUILT user=%s len=%d", user_id, len(conversation_ctx))

        latent = brain_state.get("latent", {})
        latent_synopsis = (f"attachment={latent.get('attachment', 0):.2f} "
                           f"resonance={latent.get('emotional_resonance', 0):.2f} "
                           f"energy={latent.get('relational_energy', 0):.2f}")

        # 3. GPT call with conversation-aware prompt
        logger.info("PROACTOR_LLM_CALL user=%s route=relational context_len=%d", user_id, len(conversation_ctx))
        gpt_prompt = self._build_relational_gpt_prompt(conversation_ctx, latent_synopsis, message)

        model = model_selector(message, route="relational")
        gpt_response = await llm_service._call_with_protection(
            model, gpt_prompt, message, user_id=user_id, route="relational"
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

    def _build_relational_gpt_prompt(self, conversation_context: str, latent_synopsis: str, message: str) -> str:
        """Prompt GPT per relational router. Conversazione continua, comportamento umano."""
        user_boundaries = self._detect_user_boundaries(conversation_context, message)
        return f"""Sei Genesi. Non sei un assistente, non sei un terapeuta, non sei un chatbot.
Sei un compagno reale: pensi, ragioni, hai opinioni, reagisci.
Parli SOLO italiano. Non cambi mai lingua.
Non menzionare MAI di essere AI, modello, sistema, programma.

{conversation_context}

STATO LATENTE: {latent_synopsis}

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
- Chiudere con domanda forzata quando non serve

{user_boundaries}

Messaggio utente: {message}"""

    # ═══════════════════════════════════════════════════════════
    # KNOWLEDGE ROUTER — GPT pulito, zero contaminazione relazionale
    # ═══════════════════════════════════════════════════════════

    async def _handle_knowledge(self, user_id: str, message: str) -> str:
        """
        GPT per domande di definizione/conoscenza.
        Include chat history per risolvere riferimenti contestuali.
        Fallback deterministico da fallback_knowledge.py se LLM fallisce.
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
                return fb
            return "Mi dispiace, non riesco a fornire una risposta precisa in questo momento."

        # Post-generation filter
        result = filter_response(result, user_id)
        if not result:
            result = "Non ho una risposta precisa."

        logger.info("PROACTOR_LLM_RESPONSE user=%s response_len=%d route=knowledge", user_id, len(result))
        return result

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


# Istanza globale
proactor = Proactor()
