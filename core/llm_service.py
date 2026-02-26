import os
import asyncio
import logging
import json
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from openai import AsyncOpenAI, RateLimitError, APIError, APIConnectionError
from core.log import log
from auth.database import async_session
from auth.models import UsageLog

logger = logging.getLogger("genesi")

# ═══════════════════════════════════════════════════════════
# LLM CONFIGURATION
# ═══════════════════════════════════════════════════════════

# Modelli OpenRouter (vengono mappati automaticamente su OpenAI se necessario)
LLM_DEFAULT_MODEL = "openai/gpt-4o"
LLM_FALLBACK_MODEL = "openai/gpt-4o-mini"
LLM_DEEP_MODEL = "anthropic/claude-opus-4"

DEEP_ANALYSIS_TRIGGERS = [
    "analisi profonda", 
    "senso della mia vita", 
    "perché esisto", 
    "chi sono veramente",
    "riflessione esistenziale",
    "scava a fondo",
    "psicoanalisi"
]

def model_selector(message: str, route: str = "general") -> str:
    """
    Seleziona il modello LLM in base al contenuto del messaggio.
    Default: openai/gpt-4o
    Deep: anthropic/claude-3-opus (per domande esistenziali/psicologiche profonde)
    """
    selected_model = LLM_DEFAULT_MODEL
    reason = "default"

    # Usa Claude Opus per trigger di analisi profonda
    if any(trigger in message.lower() for trigger in DEEP_ANALYSIS_TRIGGERS):
        selected_model = LLM_DEEP_MODEL
        reason = "deep analysis trigger"

    # Forza Opus per route relazionali con domande sul senso o sul "perché"
    if route == "relational" and ("perché" in message.lower() or "senso" in message.lower()):
        selected_model = LLM_DEEP_MODEL
        reason = "psychological depth"

    logger.info("LLM_MODEL_SELECTED=%s reason=%s", selected_model, reason)
    return selected_model


class LLMService:
    """
    LLM Service v5 — Resilient Dual-Provider Engine (OpenRouter + OpenAI).
    """

    def __init__(self):
        # Carica entrambe le chiavi per massima resilienza
        self.or_api_key = os.environ.get("OPENROUTER_API_KEY")
        self.oa_api_key = os.environ.get("OPENAI_API_KEY")
        
        # Client primario (OpenRouter se disponibile, altrimenti OpenAI)
        self.api_key = self.or_api_key or self.oa_api_key or ""
        self.base_url = "https://openrouter.ai/api/v1" if self.or_api_key else None
        
        # Client principale
        self.client = AsyncOpenAI(
            api_key=self.api_key,
            base_url=self.base_url
        )
        
        # Client di backup (solo se abbiamo entrambi)
        self.backup_client = None
        if self.or_api_key and self.oa_api_key:
            self.backup_client = AsyncOpenAI(api_key=self.oa_api_key)
            logger.info("LLM_SERVICE: Dual-provider mode enabled (OR + OA)")

        self.default_model = LLM_DEFAULT_MODEL
        self.fallback_model = LLM_FALLBACK_MODEL
        
        provider_name = "OpenRouter" if self.base_url else "OpenAI"
        log("LLM_SERVICE_ACTIVE", provider=provider_name)
        logger.info("LLM_ENGINE_DEFAULT=%s PRIMARY=%s", self.default_model, provider_name)
        
        from core.relational_state_engine import RelationalStateEngine
        self.relational_engine = RelationalStateEngine()
    
    def _load_adaptive_prompt(self) -> str:
        """Carica il prompt adattivo da lab/global_prompt.json."""
        try:
            prompt_file = Path("lab/global_prompt.json")
            if prompt_file.exists():
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("prompt", "")
        except Exception as e:
            logger.error("LLM_SERVICE: Error loading prompt: %s", str(e))
        return ""

    async def generate_response(self, prompt: str, message: str, user_id: str = None, route: str = "general", messages: Optional[List[Dict[str, str]]] = None) -> str:
        """Genera una risposta usando il modello selezionato con fallback deterministico."""
        model = model_selector(message, route)
        return await self._call_with_protection(model, prompt, message, user_id, route, messages)

    async def _call_with_protection(self, model: str, prompt: str, message: str, user_id: str = None, route: str = "general", messages: Optional[List[Dict[str, str]]] = None) -> str:
        """Metodo di interfaccia protetto (compatibile con Proactor)."""
        # Sostituisce system prompt con quello adattivo se disponibile
        adaptive_prompt = self._load_adaptive_prompt()
        final_prompt = adaptive_prompt if adaptive_prompt else prompt

        try:
            # Primo tentativo
            result = await self._call_model(model, final_prompt, message, user_id=user_id, route=route, messages=messages)
            if result:
                return result

            # Retry con backoff se fallisce
            logger.warning("LLM_SERVICE_PRIMARY_API_ERROR model=%s user=%s", model, user_id)
            await asyncio.sleep(1.0)
            result = await self._call_model(model, final_prompt, message, user_id=user_id, route=route, messages=messages)
            if result:
                return result

            # Downgrade automatico al modello mini
            if model != LLM_FALLBACK_MODEL:
                logger.warning("LLM_AUTO_DOWNGRADE from=%s to=%s", model, LLM_FALLBACK_MODEL)
                result = await self._call_model(LLM_FALLBACK_MODEL, final_prompt, message, user_id=user_id, route=route, messages=messages)
                if result:
                    return result

        except Exception as e:
            logger.error("LLM_SERVICE_FATAL: %s", str(e))

        # Se siamo qui e Proactor aspetta None per fare il suo fallback autonomo, restituiamo None
        # ma per messaggi generici usiamo il deterministico
        if route == "relational": return None
        return self._deterministic_fallback(message, route, user_id)

    async def _call_model(self, model: str, prompt: str, message: str, user_id: str, route: str, messages: Optional[List[Dict[str, str]]] = None) -> Optional[str]:
        """Chiama un modello con gestione intelligente dei provider e fallback automatico."""
        tag = "LLM_SERVICE_PRIMARY" if model == self.default_model else "LLM_SERVICE_FALLBACK"
        
        # Pulizia model name per OpenAI diretto
        clean_model = model
        current_client = self.client
        
        if not self.base_url: # Siamo su OpenAI diretto
            clean_model = model.split('/')[-1] if '/' in model else model
            if "claude-3-opus" in clean_model: clean_model = "gpt-4o"
        
        async def make_request(client, model_name):
            headers = {"HTTP-Referer": "https://genesi.app", "X-Title": "Genesi"} if "openrouter" in str(client.base_url) else None
            return await client.chat.completions.create(
                model=model_name,
                messages=messages if messages else [{"role": "system", "content": prompt}, {"role": "user", "content": message}],
                temperature=0.7,
                extra_headers=headers
            )

        try:
            logger.info("%s_REQUEST model=%s", tag, model)
            response = await make_request(current_client, clean_model)
            llm_response = response.choices[0].message.content.strip()
            
            # Log usage asynchronously
            try:
                usage = response.usage
                if usage and user_id:
                    asyncio.create_task(self._log_usage(user_id, model, usage.prompt_tokens, usage.completion_tokens))
            except Exception as e:
                logger.error("LLM_USAGE_LOG_ERROR: %s", str(e))

            # Behavior Regulator
            try:
                from .behavior_regulator import BehaviorRegulator
                regulator = BehaviorRegulator()
                regulated_response = regulator.regulate(llm_response, user_id)
                if regulated_response != llm_response:
                    logger.info("BEHAVIOR_REGULATOR_APPLIED changes=true")
                    llm_response = regulated_response
            except: pass

            logger.info("%s_OK model=%s len=%d", tag, model, len(llm_response))
            
            # Se è analisi profonda, aggiungiamo un marker invisibile per il regolatore
            if model == LLM_DEEP_MODEL:
                llm_response = llm_response + "\n<!-- MODE:DEEP -->"
                
            return llm_response

        except Exception as e:
            logger.warning("%s_ERROR provider=%s model=%s error=%s", tag, "OR" if self.base_url else "OA", model, str(e))
            
            # Fallback immediato a OpenAI diretto se disponibile e siamo su OR
            if self.backup_client and self.base_url:
                logger.info("%s_BACKUP switching to direct OpenAI", tag)
                try:
                    oa_model = "gpt-4o" if "opus" in model else (model.split('/')[-1] if '/' in model else "gpt-4o")
                    response = await make_request(self.backup_client, oa_model)
                    return response.choices[0].message.content.strip()
                except Exception as b_e:
                    logger.error("%s_BACKUP_FAIL: %s", tag, str(b_e))
            
            # Se 404 su Opus e siamo su OR, tenta Sonnet 3.5
            if "404" in str(e) and "claude-3-opus" in model and self.base_url:
                logger.info("%s_RETRY_ALTERNATIVE trying Claude 3.5 Sonnet", tag)
                try:
                    response = await make_request(current_client, "anthropic/claude-3.5-sonnet")
                    return response.choices[0].message.content.strip()
                except: pass

            return None

    @staticmethod
    def _deterministic_fallback(message: str, route: str, user_id: str = None) -> str:
        """Risposta di emergenza se gli LLM sono offline."""
        if route == "relational":
            return "Capisco quello che dici. Dimmi ancora qualcosa di piu' su quello che stai provando."
        if route == "knowledge":
            return "Al momento non riesco ad accedere alle mie conoscenze. Riprova tra poco."
        return "Scusa, sto avendo difficolta' tecniche. Riproviamo tra un istante."

    @staticmethod
    def _build_user_context(user_profile: dict) -> str:
        """Costruisce contesto utente formattato."""
        parts = [f"{k.capitalize()}: {v}" for k, v in user_profile.items() if v and k in ['name', 'profession', 'city', 'age']]
        return "\n".join(parts) if parts else "Nessun contesto utente disponibile."

    async def _log_usage(self, user_id: str, model: str, prompt: int, completion: int):
        """Salva l'utilizzo dei token nel database."""
        try:
            async with async_session() as session:
                log_entry = UsageLog(
                    user_id=user_id,
                    model=model,
                    prompt_tokens=prompt,
                    completion_tokens=completion
                )
                session.add(log_entry)
                await session.commit()
        except Exception as e:
            logger.error("LLM_USAGE_DB_ERROR: %s", str(e))


_TUNING_STATE: dict = {}


def load_tuning_state() -> dict:
    """Carica i parametri di tuning dall'evolution state (data/evolution/current_state.json)."""
    try:
        state_file = Path("data/evolution/current_state.json")
        if state_file.exists():
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)
            # Restituisce i parametri piatti (supportive_intensity, ecc.)
            return state.get("parameters", state)
    except Exception as e:
        logger.error("LOAD_TUNING_STATE_ERROR: %s", str(e))
    return {}


def reload_tuning_state() -> dict:
    """Ricarica i parametri di tuning nell'istanza LLM globale. Chiamata dopo ogni evoluzione."""
    global _TUNING_STATE
    try:
        state = load_tuning_state()
        _TUNING_STATE.update(state)
        logger.info("RELOAD_TUNING_STATE: state reloaded, keys=%s", list(state.keys()))
        return state
    except Exception as e:
        logger.error("RELOAD_TUNING_STATE_ERROR: %s", str(e))
        return {}


# Istanza globale
llm_service = LLMService()
