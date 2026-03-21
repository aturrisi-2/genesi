import os
import asyncio
import logging
import json
import contextvars
import re
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional

from openai import AsyncOpenAI, RateLimitError, APIError, APIConnectionError
from core.log import log
from auth.database import async_session
from auth.models import UsageLog

logger = logging.getLogger("genesi")

# ── SSE Streaming support ────────────────────────────────────────────────────
# Set this ContextVar to an asyncio.Queue before calling any LLM method.
# _call_model() will put text chunks into the queue for streaming routes.
# Sentinel: None → stream finished; dict with 'error' key → error.
_STREAM_QUEUE: contextvars.ContextVar = contextvars.ContextVar('genesi_stream_q', default=None)

# Routes whose final LLM response is streamed (not tool/JSON routes)
_STREAMING_ROUTES = frozenset({
    'relational', 'knowledge', 'general', 'general_llm',
    'tecnica', 'spiegazione', 'emotional', 'debug', 'synthesis',
})

MAX_LLM_INPUT_CHARS = int(os.environ.get("LLM_MAX_INPUT_CHARS", "45000"))
MAX_LLM_SYSTEM_CHARS = int(os.environ.get("LLM_MAX_SYSTEM_CHARS", "12000"))
MAX_LLM_MESSAGE_CHARS = int(os.environ.get("LLM_MAX_MESSAGE_CHARS", "4000"))
MAX_LLM_HISTORY_MESSAGES = int(os.environ.get("LLM_MAX_HISTORY_MESSAGES", "12"))

# ═══════════════════════════════════════════════════════════
# LLM CONFIGURATION
# ═══════════════════════════════════════════════════════════

# Modelli OpenRouter (vengono mappati automaticamente su OpenAI se necessario)
LLM_DEFAULT_MODEL = "openai/gpt-4o-mini"
LLM_FALLBACK_MODEL = "openai/gpt-4o-mini"
LLM_STRONG_MODEL = "openai/gpt-4o"
LLM_DEEP_MODEL = "anthropic/claude-opus-4"

# Frasi esplicite che richiedono un'analisi esistenziale/psicologica profonda → Opus
DEEP_ANALYSIS_TRIGGERS = [
    "analisi profonda",
    "senso della mia vita",
    "perché esisto",
    "chi sono veramente",
    "riflessione esistenziale",
    "scava a fondo",
    "psicoanalisi",
    "non so più cosa fare della mia vita",
    "mi sento perso nella vita",
    "qual è il senso di tutto",
]

# Route che richiedono qualità superiore (gpt-4o, non mini)
_STRONG_ROUTES = frozenset({"knowledge", "tecnica", "spiegazione", "debug", "document_query"})

def model_selector(message: str, route: str = "general") -> str:
    """
    Seleziona il modello LLM in base al contenuto del messaggio.
    Default: openai/gpt-4o-mini (economico, adeguato per la maggior parte dei task)
    Strong: openai/gpt-4o (route tecnico-cognitive che richiedono ragionamento)
    Deep:   anthropic/claude-opus-4 (solo analisi esistenziale/psicologica profonda)
    """
    msg_lower = message.lower()

    # Opus SOLO per trigger esistenziali espliciti — frasi complete, non parole singole
    if any(trigger in msg_lower for trigger in DEEP_ANALYSIS_TRIGGERS):
        logger.info("LLM_MODEL_SELECTED=%s reason=deep_analysis_trigger", LLM_DEEP_MODEL)
        return LLM_DEEP_MODEL

    # Route tecnico-cognitive → gpt-4o per qualità ragionamento
    if route in _STRONG_ROUTES:
        logger.info("LLM_MODEL_SELECTED=%s reason=strong_route_%s", LLM_STRONG_MODEL, route)
        return LLM_STRONG_MODEL

    # Tutto il resto (relational, emotional, general, memory, reminder…) → gpt-4o-mini
    logger.info("LLM_MODEL_SELECTED=%s reason=default_mini route=%s", LLM_DEFAULT_MODEL, route)
    return LLM_DEFAULT_MODEL


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
        """Carica il prompt adattivo da lab/global_prompt.json + regole da lab_cycle_state."""
        p = ""
        try:
            prompt_file = Path("lab/global_prompt.json")
            if prompt_file.exists():
                with open(prompt_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    p = data.get("system_prompt", "") or data.get("prompt", "")
        except Exception as e:
            logger.error("LLM_SERVICE: Error loading prompt: %s", str(e))

        # Inietta sempre le regole lab da lab_cycle_state.json (source of truth)
        # Questo è robusto anche se AdaptivePromptBuilder sovrascrive global_prompt.json
        _MARKER = "\n\n[REGOLE APPRESE DALL'ESPERIENZA]\n"
        try:
            state_file = Path("memory/admin/lab_cycle_state.json")
            if state_file.exists():
                with open(state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                rules = state.get("rules", [])
                if rules:
                    # Rimuovi eventuale blocco regole già presente nel prompt
                    if _MARKER in p:
                        p = p.split(_MARKER)[0]
                    p += _MARKER + "\n".join(f"- {r}" for r in rules)
        except Exception:
            pass

        if p:
            logger.info("LLM_ADAPTIVE_PROMPT_LOADED len=%d", len(p))
        return p

    async def generate_response(self, prompt: str, message: str, user_id: str = None, route: str = "general", messages: Optional[List[Dict[str, str]]] = None) -> str:
        """Genera una risposta usando il modello selezionato con fallback deterministico."""
        model = model_selector(message, route)
        return await self._call_with_protection(model, prompt, message, user_id, route, messages)

    async def _call_with_protection(self, model: str, prompt: str, message: str, user_id: str = None, route: str = "general", messages: Optional[List[Dict[str, str]]] = None) -> str:
        """Metodo di interfaccia protetto (compatibile con Proactor)."""
        final_prompt = prompt
        
        # Applica l'adaptive prompt SOLO alle route conversazionali,
        # per evitare di rompere i prompt JSON (classificazione, estrazione).
        if route in ["relational", "general", "general_llm", "emotional"]:
            adaptive_prompt = self._load_adaptive_prompt()
            if adaptive_prompt:
                final_prompt = prompt + "\n\n[ADAPTIVE PERSONA]\n" + adaptive_prompt
                # Se proactor ha passato i messaggi, inietta lì l'adaptive prompt
                if messages and len(messages) > 0 and messages[0].get("role") == "system":
                    messages[0]["content"] += "\n\n[ADAPTIVE PERSONA]\n" + adaptive_prompt

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
        
        msg_list = self._prepare_message_payload(messages, prompt, message, tag)
        extra_headers = {"HTTP-Referer": "https://genesi.app", "X-Title": "Genesi"} if "openrouter" in str(current_client.base_url) else None

        async def make_request(client, model_name):
            return await client.chat.completions.create(
                model=model_name,
                messages=msg_list,
                temperature=0.7,
                extra_headers=extra_headers,
                timeout=15.0
            )

        # ── SSE streaming path ───────────────────────────────────────────────
        stream_queue = _STREAM_QUEUE.get()
        if stream_queue is not None and route in _STREAMING_ROUTES:
            try:
                logger.info("%s_STREAM_REQUEST model=%s route=%s", tag, model, route)
                api_stream = await current_client.chat.completions.create(
                    model=clean_model,
                    messages=msg_list,
                    temperature=0.7,
                    stream=True,
                    extra_headers=extra_headers,
                    timeout=15.0
                )
                llm_response = ""
                async for chunk in api_stream:
                    delta = chunk.choices[0].delta.content if chunk.choices else None
                    if delta:
                        llm_response += delta
                        await stream_queue.put({"chunk": delta})
                logger.info("%s_STREAM_OK model=%s len=%d", tag, model, len(llm_response))
                return llm_response if llm_response else None
            except Exception as se:
                logger.warning("%s_STREAM_ERROR: %s — falling back to normal", tag, se)
                # Fall through to normal (non-streaming) path below

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
            
            # Se 404 su Opus e siamo su OR, fallback a gpt-4o (non Sonnet — troppo costoso)
            if "404" in str(e) and "claude-opus" in model and self.base_url:
                logger.info("%s_RETRY_ALTERNATIVE trying gpt-4o as opus fallback", tag)
                try:
                    response = await make_request(current_client, "openai/gpt-4o")
                    return response.choices[0].message.content.strip()
                except: pass

            return None

    @staticmethod
    def _truncate_text(value: Any, limit: int) -> str:
        text = str(value or "")
        if len(text) <= limit:
            return text
        return text[: max(0, limit)] + "\n[...troncato automaticamente per limite contesto...]"

    @staticmethod
    def _scrub_sensitive_payload(text: str) -> str:
        if not text:
            return text
        scrubbed = text
        patterns = [
            r"(?i)(access_token\s*[:=]\s*)[A-Za-z0-9\-\._~\+/=]+",
            r"(?i)(refresh_token\s*[:=]\s*)[A-Za-z0-9\-\._~\+/=]+",
            r"(?i)(client_secret\s*[:=]\s*)[A-Za-z0-9\-\._~\+/=]+",
            r"(?i)(authorization\s*[:=]\s*bearer\s+)[A-Za-z0-9\-\._~\+/=]+",
        ]
        for pattern in patterns:
            scrubbed = re.sub(pattern, r"\1[REDACTED]", scrubbed)
        return scrubbed

    def _prepare_message_payload(
        self,
        messages: Optional[List[Dict[str, str]]],
        prompt: str,
        message: str,
        tag: str,
    ) -> List[Dict[str, str]]:
        if not messages:
            safe_prompt = self._truncate_text(self._scrub_sensitive_payload(prompt), MAX_LLM_SYSTEM_CHARS)
            safe_message = self._truncate_text(self._scrub_sensitive_payload(message), MAX_LLM_MESSAGE_CHARS)
            return [{"role": "system", "content": safe_prompt}, {"role": "user", "content": safe_message}]

        normalized: List[Dict[str, str]] = []
        for item in messages:
            if not isinstance(item, dict):
                continue
            role = (item.get("role") or "user").strip() or "user"
            content = self._scrub_sensitive_payload(str(item.get("content") or ""))
            per_msg_limit = MAX_LLM_SYSTEM_CHARS if role == "system" else MAX_LLM_MESSAGE_CHARS
            normalized.append({"role": role, "content": self._truncate_text(content, per_msg_limit)})

        if len(normalized) > MAX_LLM_HISTORY_MESSAGES:
            system_head = [m for m in normalized[:1] if m.get("role") == "system"]
            tail = normalized[-(MAX_LLM_HISTORY_MESSAGES - len(system_head)):]
            normalized = system_head + tail

        total_chars = sum(len(m.get("content", "")) for m in normalized)
        if total_chars <= MAX_LLM_INPUT_CHARS:
            return normalized

        system_msgs = [m for m in normalized if m.get("role") == "system"][:1]
        other_msgs = [m for m in normalized if m.get("role") != "system"]
        kept_tail: List[Dict[str, str]] = []
        current_chars = sum(len(m.get("content", "")) for m in system_msgs)
        for item in reversed(other_msgs):
            item_len = len(item.get("content", ""))
            if current_chars + item_len <= MAX_LLM_INPUT_CHARS or not kept_tail:
                kept_tail.append(item)
                current_chars += item_len
            else:
                break

        trimmed = system_msgs + list(reversed(kept_tail))
        logger.warning(
            "%s_CONTEXT_TRIMMED original_chars=%d final_chars=%d messages=%d->%d",
            tag,
            total_chars,
            sum(len(m.get("content", "")) for m in trimmed),
            len(normalized),
            len(trimmed),
        )
        return trimmed

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
