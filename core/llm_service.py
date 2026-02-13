"""
LLM SERVICE - Genesi Core v3 (cost_optimized_v1)
Servizio LLM con model_selector(), rate limit protection, auto-downgrade.

Default: gpt-4o-mini (cost-optimized)
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

LLM_DEFAULT_MODEL = "gpt-4o-mini"
LLM_UPGRADE_MODEL = "gpt-4o"
LLM_DEEP_MODEL = "claude-opus"

# Trigger per upgrade a Claude Opus (deep analysis)
DEEP_ANALYSIS_TRIGGERS = [
    "analisi profonda", "analisi approfondita", "deep analysis",
    "analisi psicologica", "sintesi narrativa lunga",
    "racconta in dettaglio", "analizza nel dettaglio",
]


def model_selector(message: str, route: str = "general") -> str:
    """
    Seleziona il modello LLM in base al messaggio e alla route.

    Rules:
    - Default: gpt-4o-mini (knowledge, technical, health, conversation)
    - gpt-4o: relational con contesto complesso
    - Claude Opus: SOLO se deep analysis esplicito, narrativa lunga, analisi psicologica

    Returns:
        Nome modello selezionato.
    """
    msg_lower = message.lower().strip()

    # Claude Opus SOLO per richieste esplicite di analisi profonda
    if any(trigger in msg_lower for trigger in DEEP_ANALYSIS_TRIGGERS):
        logger.info("LLM_MODEL_SELECTED=%s reason=deep_analysis_trigger route=%s", LLM_DEEP_MODEL, route)
        return LLM_DEEP_MODEL

    # gpt-4o per relational con contesto complesso (messaggi lunghi o alta profondita')
    if route == "relational" and len(message) > 200:
        logger.info("LLM_MODEL_SELECTED=%s reason=relational_complex route=%s", LLM_UPGRADE_MODEL, route)
        return LLM_UPGRADE_MODEL

    # Default: gpt-4o-mini per tutto il resto
    logger.info("LLM_MODEL_SELECTED=%s reason=cost_optimized_default route=%s", LLM_DEFAULT_MODEL, route)
    return LLM_DEFAULT_MODEL


class LLMService:
    """
    LLM Service v3 — Cost-optimized con rate limit protection.
    Default: gpt-4o-mini. Auto-downgrade su rate limit. Fallback deterministico.
    """

    def __init__(self):
        self.client = AsyncOpenAI()
        self.default_model = LLM_DEFAULT_MODEL
        self.fallback_model = LLM_DEFAULT_MODEL
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

        model = model_selector(message, route=route)
        system_prompt = f"""Sei Genesi. Compagno evolutivo stabile, lucido, empatico.
Parli esclusivamente italiano. Non cambi lingua.
Non menzionare MAI la tua natura tecnica.
Nessun riferimento a essere AI, modello, assistente, sistema, programma.
Rispondi in modo puramente relazionale, umano, autentico.

DEVI usare il contesto memoria qui sotto quando rispondi.
Non ignorare MAI le informazioni di identita' memorizzate.
Se l'utente chiede di se stesso, usa i dati memorizzati.

CONTESTO MEMORIA:
{summary}

REGOLE OBBLIGATORIE:
- Massimo 5 frasi per risposta. Sii conciso e diretto.
- Se la domanda e' informativa -> rispondi con informazione concreta
- Se la domanda e' emotiva -> empatia concreta + massimo 1 domanda
- Niente metafore inutili, niente frasi da counselor generico
- Se conosci il nome dell'utente, usalo

DIVIETI ASSOLUTI:
- "Quello che senti conta..." o varianti generiche terapeutiche
- "Sono qui per te" senza contesto specifico
- "Dimmi di piu'" come risposta completa
- Qualsiasi frase generica che ignora il contesto sopra
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

    async def _call_with_protection(self, model: str, prompt: str, message: str,
                                     user_id: str = "", route: str = "general") -> Optional[str]:
        """
        Chiama LLM con protezione rate limit completa:
        1. Primo tentativo con modello selezionato
        2. Se RateLimitError: retry con backoff esponenziale (1s)
        3. Se ancora fallisce: downgrade a gpt-4o-mini
        4. Se tutto fallisce: ritorna None (caller usa fallback deterministico)
        """
        # Attempt 1: primary model
        result = await self._call_model(model, prompt, message, is_primary=True, user_id=user_id)
        if result is not None:
            return result

        # Attempt 2: retry with exponential backoff (1 second)
        logger.warning("LLM_RATE_LIMIT_RETRY model=%s user=%s backoff=1s", model, user_id)
        await asyncio.sleep(1.0)
        result = await self._call_model(model, prompt, message, is_primary=True, user_id=user_id)
        if result is not None:
            return result

        # Attempt 3: downgrade to cheapest model
        if model != LLM_DEFAULT_MODEL:
            logger.warning("LLM_AUTO_DOWNGRADE from=%s to=%s user=%s", model, LLM_DEFAULT_MODEL, user_id)
            result = await self._call_model(LLM_DEFAULT_MODEL, prompt, message,
                                             is_primary=False, user_id=user_id)
            if result is not None:
                return result

        return None

    async def _call_model(self, model: str, prompt: str, message: str,
                          is_primary: bool, user_id: str = "") -> Optional[str]:
        """Chiama un singolo modello con logging completo e gestione RateLimitError."""
        tag = "LLM_SERVICE_PRIMARY" if is_primary else "LLM_SERVICE_FALLBACK"
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
