"""
LLM SERVICE - Genesi Core v2
Servizio LLM per risposte tecniche con contesto utente
"""

from openai import AsyncOpenAI
from core.log import log

class LLMService:
    """
    LLM Service - Gestione risposte tecniche con contesto
    Tecnica, debug, spiegazione, architettura
    """
    
    def __init__(self):
        self.client = AsyncOpenAI()
        log("LLM_SERVICE_ACTIVE")
    
    async def generate_response(self, message: str) -> str:
        """
        Genera risposta LLM per contenuti tecnici
        
        Args:
            message: Messaggio utente
            
        Returns:
            Risposta tecnica da LLM
        """
        try:
            log("LLM_SERVICE_REQUEST", message=message[:50])
            
            # Prompt tecnico
            technical_prompt = f"""
Sei Genesi, assistente tecnico esperto.
Rispondi in modo chiaro, tecnico, preciso.
Focus su: programmazione, architettura, debugging, spiegazioni tecniche.
Usa esempi pratici quando possibile.

Domanda: {message}
"""
            
            response = await self.client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "system", "content": technical_prompt}],
                temperature=0.3
            )
            
            llm_response = response.choices[0].message.content.strip()
            
            log("LLM_SERVICE_RESPONSE", length=len(llm_response))
            return llm_response
            
        except Exception as e:
            log("LLM_SERVICE_ERROR", error=str(e))
            return "Mi dispiace, ho avuto un problema tecnico. Riprova più tardi."
    
    async def generate_response_with_context(self, message: str, user_profile: dict) -> str:
        """
        Genera risposta LLM con contesto utente
        
        Args:
            message: Messaggio utente
            user_profile: Profilo utente completo
            
        Returns:
            Risposta tecnica con contesto personalizzato
        """
        try:
            log("LLM_SERVICE_CONTEXT_REQUEST", message=message[:50], user_id=user_profile.get("id", "unknown"))
            
            # Costruisci contesto utente
            context = self._build_user_context(user_profile)
            
            # Prompt tecnico con contesto
            technical_prompt = f"""
Sei Genesi, assistente tecnico esperto.
Rispondi in modo chiaro, tecnico, preciso.
Focus su: programmazione, architettura, debugging, spiegazioni tecniche.
Usa esempi pratici quando possibile.

CONTESTO UTENTE:
{context}

Domanda: {message}
"""
            
            response = await self.client.chat.completions.create(
                model="gpt-4",
                messages=[{"role": "system", "content": technical_prompt}],
                temperature=0.3
            )
            
            llm_response = response.choices[0].message.content.strip()
            
            log("LLM_SERVICE_CONTEXT_RESPONSE", length=len(llm_response))
            return llm_response
            
        except Exception as e:
            log("LLM_SERVICE_CONTEXT_ERROR", error=str(e))
            return "Mi dispiace, ho avuto un problema tecnico. Riprova più tardi."
    
    def _build_user_context(self, user_profile: dict) -> str:
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
