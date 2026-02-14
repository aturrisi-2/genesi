"""
LLM SERVICE - Genesi Core v3 (cost_optimized_v1)
Servizio LLM con model_selector(), rate limit protection, auto-downgrade.

Default: gpt-4o (cost-optimized)
Claude Opus: SOLO per deep analysis esplicito, narrativa lunga, analisi psicologica complessa.
Rate limit: retry con backoff esponenziale, downgrade automatico, fallback deterministico.
"""

import os
import asyncio
import logging
from typing import Optional
from openai import AsyncOpenAI, RateLimitError, APIError, APIConnectionError
from core.log import log

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# MODEL CONFIGURATION — cost-optimized defaults
# ═══════════════════════════════════════════════════════════════

LLM_DEFAULT_MODEL = "gpt-4o"
LLM_FALLBACK_MODEL = "gpt-4o-mini"
LLM_DEEP_MODEL = "claude-opus"

# Trigger per upgrade a Claude Opus (deep analysis)
DEEP_ANALYSIS_TRIGGERS = [
    "analisi profonda",
    "deep psychological analysis"
]


def model_selector(message: str, route: str = "general") -> str:
    """
    Selects the appropriate model based on message content and route.
    """
    # Default to primary model
    selected_model = LLM_DEFAULT_MODEL
    reason = "default"

    # Use Claude Opus for deep analysis triggers
    if any(trigger in message.lower() for trigger in DEEP_ANALYSIS_TRIGGERS):
        selected_model = LLM_DEEP_MODEL
        reason = "deep analysis trigger"

    logger.info("LLM_MODEL_SELECTED=%s reason=%s", selected_model, reason)
    return selected_model


class LLMService:
    """
    LLM Service v3 — Cost-optimized con rate limit protection.
    Default: gpt-4o. Auto-downgrade su rate limit. Fallback deterministico.
    """

    def __init__(self):
        self.client = AsyncOpenAI()
        self.default_model = LLM_DEFAULT_MODEL
        self.fallback_model = LLM_FALLBACK_MODEL
        _api_key = os.environ.get("OPENAI_API_KEY", "")
        if not _api_key or _api_key.startswith("sk-test"):
            logger.warning("LLM_SERVICE: OPENAI_API_KEY missing or test-only")
        log("LLM_SERVICE_ACTIVE")
        logger.info("LLM_ENGINE_DEFAULT=%s ARCHITECTURE_MODE=cost_optimized_v1", self.default_model)

    async def generate_response(self, message: str, route: str = "general") -> str:
        """
        Genera risposta LLM con model_selector e rate limit protection.
        Chain: selected_model -> retry backoff -> downgrade -> deterministic fallback.
        """
        model = model_selector(message, route)
        technical_prompt = f"""
Sei Genesi, assistente tecnico esperto.
Rispondi in modo chiaro, tecnico, preciso.
Focus su: programmazione, architettura, debugging, spiegazioni tecniche.
Usa esempi pratici quando possibile.

Domanda: {message}
"""
        result = await self._call_with_protection(model, technical_prompt, message, route=route)
        if result:
            return result

        logger.error("LLM_SERVICE_ALL_FAIL route=%s — activating deterministic fallback", route)
        return self._deterministic_fallback(message, route)

    async def generate_response_with_context(self, message: str, user_profile: dict, user_id: str) -> str:
        """
        Genera risposta LLM con contesto utente e rate limit protection.
        """
        if not user_id:
            raise ValueError("LLM service received empty user_id")

        model = model_selector(message, route="technical")
        context = self._build_user_context(user_profile)
        technical_prompt = f"""
Sei Genesi, assistente tecnico esperto.
Rispondi in modo chiaro, tecnico, preciso.
Focus su: programmazione, architettura, debugging, spiegazioni tecniche.
Usa esempi pratici quando possibile.

CONTESTO UTENTE:
{context}

Domanda: {message}
"""
        result = await self._call_with_protection(model, technical_prompt, message,
                                                   user_id=user_id, route="technical")
        if result:
            return result

        logger.error("LLM_SERVICE_ALL_FAIL user=%s — activating deterministic fallback", user_id)
        return self._deterministic_fallback(message, "technical")

    async def generate_with_context(self, context: dict, user_id: str = "",
                                     route: str = "relational") -> str:
        """
        Genera risposta LLM con contesto strutturato dalla memoria.
        Il context deve contenere 'summary' e 'current_message' (da ContextAssembler).
        Rate limit protection con auto-downgrade.

        Raises:
            RuntimeError se context['summary'] e' vuoto.
        """
        summary = context.get("summary", "")
        if not summary or not summary.strip():
            raise RuntimeError(f"LLM_CONTEXT_EMPTY user={user_id} — generate_with_context received empty summary")

        message = context.get("current_message", "")
        if not message:
            raise ValueError("LLM_NO_MESSAGE — generate_with_context received empty current_message")

        # Build conversation context with chat history if user_id available
        from core.context_assembler import build_conversation_context
        profile = context.get("profile", {})
        if user_id:
            conversation_ctx = build_conversation_context(user_id, message, profile)
        else:
            conversation_ctx = f"INFORMAZIONI STABILI SULL'UTENTE:\n{summary}"

        model = model_selector(message, route=route)
        system_prompt = f"""Sei Genesi. Non sei un assistente, non sei un terapeuta, non sei un chatbot.
Sei un compagno reale: pensi, ragioni, hai opinioni, reagisci.
Parli SOLO italiano. Non cambi mai lingua.
Non menzionare MAI di essere AI, modello, sistema, programma.

{conversation_ctx}

CONTINUITA' CONVERSAZIONALE (REGOLA FONDAMENTALE):
- Devi mantenere coerenza con la conversazione recente sopra.
- Non rispondere come se ogni messaggio fosse isolato.
- Collega la risposta al contesto precedente.
- Se l'utente ha appena parlato di una persona, non trattarla come nuova.
- Se l'utente introduce una nuova informazione, integrala naturalmente.
- Evita reset tematici: se si parla di famiglia, resta sul tema.

COME DEVI COMPORTARTI:
- Rispondi in modo naturale. Solo a cio' che viene detto.
- Se non c'e' bisogno di espandere, resta essenziale.
- Non aggiungere frasi motivazionali.
- Non aggiungere consigli se non richiesti.
- Non usare formule ricorrenti.
- Non usare entusiasmo artificiale.
- Non chiudere sempre con una domanda.
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
"""

        logger.info("LLM_GENERATE_WITH_CONTEXT user=%s summary_len=%d msg_len=%d model=%s",
                     user_id, len(summary), len(message), model)

        result = await self._call_with_protection(model, system_prompt, message,
                                                   user_id=user_id, route=route)
        if result:
            return result

        logger.error("LLM_SERVICE_ALL_FAIL user=%s — activating deterministic fallback", user_id)
        return self._deterministic_fallback(message, route)

    # ═══════════════════════════════════════════════════════════
    # RATE LIMIT PROTECTION — retry, downgrade, fallback
    # ═══════════════════════════════════════════════════════════

    async def _call_with_protection(self, model: str, prompt: str, message: str, user_id: str, route: str) -> Optional[str]:
        """
        Call LLM with rate limit protection, retry, downgrade, and deterministic fallback.
        """
        try:
            # Primary attempt
            logger.info("LLM_SERVICE_PRIMARY_REQUEST model=%s user=%s", model, user_id)
            result = await self._call_model(model, prompt, message, user_id=user_id, route=route)
            if result is not None:
                return result

            # Retry with exponential backoff
            logger.warning("LLM_SERVICE_PRIMARY_API_ERROR model=%s user=%s", model, user_id)
            logger.info("LLM_RATE_LIMIT_RETRY model=%s user=%s", model, user_id)
            await asyncio.sleep(1.0)  # 1s backoff
            result = await self._call_model(model, prompt, message, user_id=user_id, route=route)
            if result is not None:
                return result

            # Downgrade to gpt-4o-mini if not already using fallback model
            if model != LLM_FALLBACK_MODEL:
                logger.warning("LLM_AUTO_DOWNGRADE from=%s to=%s user=%s", model, LLM_FALLBACK_MODEL, user_id)
                result = await self._call_model(LLM_FALLBACK_MODEL, prompt, message, user_id=user_id, route=route)
                if result is not None:
                    return result

            # Return None if all attempts fail
            logger.error("LLM_SERVICE_ALL_FAIL user=%s", user_id)
            return None

        except (RateLimitError, APIError, APIConnectionError) as e:
            logger.error("LLM_SERVICE_EXCEPTION user=%s error=%s", user_id, str(e))
            return None

    async def _call_model(self, model: str, prompt: str, message: str, user_id: str, route: str) -> Optional[str]:
        """Chiama un singolo modello con logging completo e gestione RateLimitError."""
        tag = "LLM_SERVICE_PRIMARY" if model == self.default_model else "LLM_SERVICE_FALLBACK"
        try:
            logger.info("%s_REQUEST model=%s msg=%s", tag, model, message[:50])
            response = await self.client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": prompt}],
                temperature=0.3
            )
            llm_response = response.choices[0].message.content.strip()
            if not llm_response:
                logger.warning("%s_EMPTY model=%s", tag, model)
                return None
            logger.info("%s_OK model=%s len=%d", tag, model, len(llm_response))
            return llm_response
        except RateLimitError as e:
            logger.warning("%s_RATE_LIMITED model=%s user=%s error=%s", tag, model, user_id, str(e))
            return None
        except (APIError, APIConnectionError) as e:
            logger.warning("%s_API_ERROR model=%s user=%s error=%s", tag, model, user_id, type(e).__name__)
            return None
        except Exception as e:
            logger.error("%s_ERROR model=%s error=%s", tag, model, str(e))
            return None

    # ═══════════════════════════════════════════════════════════
    # DETERMINISTIC FALLBACK — never return "non riesco a rispondere"
    # ═══════════════════════════════════════════════════════════

    @staticmethod
    def _deterministic_fallback(message: str, route: str) -> str:
        """
        Fallback deterministico quando tutti i modelli LLM falliscono.
        Mai restituire 'Non riesco a rispondere'. Sempre una risposta utile.
        """
        msg_lower = message.lower().strip()

        if route == "knowledge":
            # Try fallback_knowledge dictionary
            from core.fallback_knowledge import lookup_fallback
            fb = lookup_fallback(message)
            if fb:
                return fb
            return "Al momento non ho accesso alle informazioni richieste. Riprova tra qualche minuto."

        if route == "relational":
            return "Capisco. Dimmi qualcosa in piu' su quello che stai vivendo."

        if route == "technical":
            return "Il servizio tecnico e' temporaneamente sovraccarico. Riprova tra qualche minuto."

        # General fallback
        return "Scusa, sto avendo qualche difficolta'. Riproviamo tra un momento."

    @staticmethod
    def _build_user_context(user_profile: dict) -> str:
        """
        Costruisci contesto utente per LLM
        
        Args:
            user_profile: Profilo utente
            
        Returns:
            Contesto formattato
        """
        context_parts = []
        
        if user_profile.get("name"):
            context_parts.append(f"Nome: {user_profile['name']}")
        
        if user_profile.get("profession"):
            context_parts.append(f"Professione: {user_profile['profession']}")
        
        if user_profile.get("city"):
            context_parts.append(f"Citta': {user_profile['city']}")
        
        if user_profile.get("age"):
            context_parts.append(f"Eta': {user_profile['age']}")
        
        if user_profile.get("traits"):
            context_parts.append(f"Caratteristiche: {', '.join(user_profile['traits'])}")
        
        return "\n".join(context_parts) if context_parts else "Nessun contesto utente disponibile."

# Istanza globale
llm_service = LLMService()
