"""
LLM SERVICE - Genesi Core v2
Servizio LLM per risposte tecniche e complesse
"""

from openai import AsyncOpenAI
from core.log import log

class LLMService:
    """
    LLM Service - Gestione risposte tecniche
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

# Istanza globale
llm_service = LLMService()
