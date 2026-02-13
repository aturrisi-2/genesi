"""
LLM SERVICE - Genesi Core v2
Servizio LLM per risposte tecniche con contesto utente
"""

import os
import logging
from typing import Optional
from openai import AsyncOpenAI
from core.log import log

logger = logging.getLogger(__name__)

# GPT-4o per risposte tecniche, gpt-4o-mini come fallback
LLM_SERVICE_MODEL = "gpt-4o"
LLM_SERVICE_FALLBACK = "gpt-4o-mini"

class LLMService:
    """
    LLM Service - Gestione risposte tecniche con contesto
    Engine: GPT-4o (no QWEN fallback)
    """
    
    def __init__(self):
        self.client = AsyncOpenAI()
        self.model = LLM_SERVICE_MODEL
        self.fallback_model = LLM_SERVICE_FALLBACK
        _api_key = os.environ.get("OPENAI_API_KEY", "")
        if not _api_key or _api_key.startswith("sk-test"):
            logger.warning("LLM_SERVICE: OPENAI_API_KEY missing or test-only")
        log("LLM_SERVICE_ACTIVE")
        logger.info("LLM_ENGINE=%s fallback=%s", self.model, self.fallback_model)
    
    async def generate_response(self, message: str) -> str:
        """
        Genera risposta LLM per contenuti tecnici.
        Chain: gpt-4o -> gpt-4o-mini fallback.
        """
        technical_prompt = f"""
Sei Genesi, assistente tecnico esperto.
Rispondi in modo chiaro, tecnico, preciso.
Focus su: programmazione, architettura, debugging, spiegazioni tecniche.
Usa esempi pratici quando possibile.

Domanda: {message}
"""
        # Primary
        result = await self._call_model(self.model, technical_prompt, message, is_primary=True)
        if result:
            return result

        # Fallback
        logger.warning("LLM_SERVICE_PRIMARY_FAIL — switching to %s", self.fallback_model)
        result = await self._call_model(self.fallback_model, technical_prompt, message, is_primary=False)
        if result:
            return result

        logger.error("LLM_SERVICE_FALLBACK_FAIL — both models failed")
        return "Mi dispiace, ho avuto un problema tecnico. Riprova più tardi."
    
    async def generate_response_with_context(self, message: str, user_profile: dict, user_id: str) -> str:
        """
        Genera risposta LLM con contesto utente.
        Chain: gpt-4o -> gpt-4o-mini fallback.
        """
        if not user_id:
            raise ValueError("LLM service received empty user_id")

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
        # Primary
        result = await self._call_model(self.model, technical_prompt, message, is_primary=True, user_id=user_id)
        if result:
            return result

        # Fallback
        logger.warning("LLM_SERVICE_PRIMARY_FAIL user=%s — switching to %s", user_id, self.fallback_model)
        result = await self._call_model(self.fallback_model, technical_prompt, message, is_primary=False, user_id=user_id)
        if result:
            return result

        logger.error("LLM_SERVICE_FALLBACK_FAIL user=%s — both models failed", user_id)
        return "Mi dispiace, ho avuto un problema tecnico. Riprova più tardi."

    async def generate_with_context(self, context: dict, user_id: str = "") -> str:
        """
        Genera risposta LLM con contesto strutturato dalla memoria.
        Il context deve contenere 'summary' e 'current_message' (da ContextAssembler).
        Chain: gpt-4o -> gpt-4o-mini fallback.

        Raises:
            RuntimeError se context['summary'] e' vuoto.
        """
        summary = context.get("summary", "")
        if not summary or not summary.strip():
            raise RuntimeError(f"LLM_CONTEXT_EMPTY user={user_id} — generate_with_context received empty summary")

        message = context.get("current_message", "")
        if not message:
            raise ValueError("LLM_NO_MESSAGE — generate_with_context received empty current_message")

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

        logger.info("LLM_GENERATE_WITH_CONTEXT user=%s summary_len=%d msg_len=%d",
                     user_id, len(summary), len(message))

        # Primary
        result = await self._call_model(self.model, system_prompt, message, is_primary=True, user_id=user_id)
        if result:
            return result

        # Fallback
        logger.warning("LLM_SERVICE_PRIMARY_FAIL user=%s — switching to %s", user_id, self.fallback_model)
        result = await self._call_model(self.fallback_model, system_prompt, message, is_primary=False, user_id=user_id)
        if result:
            return result

        logger.error("LLM_SERVICE_FALLBACK_FAIL user=%s — both models failed", user_id)
        return "Mi dispiace, ho avuto un problema. Riprova tra poco."

    async def _call_model(self, model: str, prompt: str, message: str,
                          is_primary: bool, user_id: str = "") -> Optional[str]:
        """Chiama un singolo modello con logging completo."""
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
        except Exception as e:
            logger.error("%s_ERROR model=%s error=%s", tag, model, str(e))
            return None
    
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
            context_parts.append(f"Città: {user_profile['city']}")
        
        if user_profile.get("age"):
            context_parts.append(f"Età: {user_profile['age']}")
        
        if user_profile.get("traits"):
            context_parts.append(f"Caratteristiche: {', '.join(user_profile['traits'])}")
        
        return "\n".join(context_parts) if context_parts else "Nessun contesto utente disponibile."

# Istanza globale
llm_service = LLMService()
