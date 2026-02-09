"""
MOTORI DI GENERAZIONE - Separazione netta delle responsabilità
Ogni motore ha UN SOLO compito specifico
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, Any
import asyncio

class BaseEngine(ABC):
    """Base class per tutti i motori"""
    
    @abstractmethod
    async def generate(self, message: str, params: Dict[str, Any], context: Optional[Dict] = None) -> str:
        """Genera risposta - metodo obbligatorio"""
        pass
    
    @abstractmethod
    def can_handle(self, intent_type: str) -> bool:
        """Verifica se può gestire l'intent"""
        pass

class GPTFullEngine(BaseEngine):
    """
    GPT-FULL - Solo per fatti verificabili
    Usato per: meteo, news, spiegazioni tecniche, definizioni, psicologico
    """
    
    def __init__(self):
        from core.llm import generate_response as llm_generate
        self.llm_generate = llm_generate
    
    async def generate(self, message: str, params: Dict[str, Any], context: Optional[Dict] = None) -> str:
        """
        Genera risposta con GPT-full - testo pulito, niente teatralità
        """
        print(f"[GPT_FULL] Generating factual response", flush=True)
        
        try:
            # Prompt per GPT-full - solo fatti
            prompt = self._build_factual_prompt(message, params.get("intent_type", ""))
            
            response = await self.llm_generate(
                prompt=prompt,
                temperature=params.get("temperature", 0.3),
                max_tokens=params.get("max_tokens", 150)
            )
            
            return response.strip()
            
        except Exception as e:
            print(f"[GPT_FULL] Error: {e}", flush=True)
            return "Non posso fornire questa informazione in questo momento."
    
    def can_handle(self, intent_type: str) -> bool:
        """GPT-full gestisce intent fattuali"""
        return intent_type in [
            "medical_info", "historical_info", "definition", 
            "technical", "identity", "other"
        ]
    
    def _build_factual_prompt(self, message: str, intent_type: str) -> str:
        """
        Costruisce prompt per GPT-full - solo fatti
        """
        base_prompt = """Rispondi in modo fattuale e conciso.

REGOLE ASSOLUTE:
- SOLO informazioni verificabili
- Niente opinioni personali
- Niente teatralità o emoji
- Niente conversazione personale
- Massimo 2-3 frasi

"""
        
        if intent_type == "medical_info":
            base_prompt += "Fornisci informazioni mediche generali. Aggiungi sempre: 'Per problemi specifici consulta un medico'."
        elif intent_type == "historical_info":
            base_prompt += "Fornisci informazioni storiche accurate e concise."
        elif intent_type == "definition":
            base_prompt += "Spiega il concetto in modo semplice e tecnico."
        elif intent_type == "identity":
            base_prompt += "Rispondi in modo amichevole ma conciso."
        else:
            base_prompt += "Rispondi in modo informativo e diretto."
        
        return f"{base_prompt}\n\nDomanda: {message}\nRisposta:"

class PersonalplexEngine(BaseEngine):
    """
    PERSONALPLEX - Solo per chat libera
    Usato per: dialogo naturale, relazione, presenza
    """
    
    def __init__(self):
        from core.local_llm import LocalLLM
        self.local_llm = LocalLLM()
    
    async def generate(self, message: str, params: Dict[str, Any], context: Optional[Dict] = None) -> str:
        """
        Genera risposta con PersonalPlex - solo per chat libera
        """
        print(f"[PERSONALPLEX] Generating conversational response", flush=True)
        
        try:
            # Prompt per PersonalPlex - solo conversazione
            prompt = self._build_conversational_prompt(message, context)
            
            response = self.local_llm.generate(
                prompt=prompt,
                max_tokens=params.get("max_tokens", 80),
                temperature=params.get("temperature", 0.7)
            )
            
            return response.strip()
            
        except Exception as e:
            print(f"[PERSONALPLEX] Error: {e}", flush=True)
            return "Mi dispiace, non riesco a rispondere ora."
    
    def can_handle(self, intent_type: str) -> bool:
        """Personalplex gestisce solo chat libera"""
        return intent_type == "chat_free"
    
    def _build_conversational_prompt(self, message: str, context: Optional[Dict] = None) -> str:
        """
        Costruisce prompt per PersonalPlex - solo conversazione
        """
        base_prompt = """Sei Genesi. Rispondi in modo naturale e conversazionale.

REGOLE:
- Sii amichevole e naturale
- Massimo 1-2 frasi
- Niente fatti tecnici
- Niente teatralità o emoji

"""
        
        return f"{base_prompt}\nUtente: {message}\nGenesi:"

class APIToolsEngine(BaseEngine):
    """
    API TOOLS - Solo per API esterne
    Usato per: meteo, news
    """
    
    async def generate(self, message: str, params: Dict[str, Any], context: Optional[Dict] = None) -> str:
        """
        Chiama API esterne per meteo/news
        """
        api_type = params.get("api_type", "")
        print(f"[API_TOOLS] Calling {api_type} API", flush=True)
        
        try:
            if api_type == "weather":
                return await self._get_weather(params.get("location", "Roma"))
            elif api_type == "news":
                return await self._get_news()
            else:
                return "Servizio non disponibile."
                
        except Exception as e:
            print(f"[API_TOOLS] Error: {e}", flush=True)
            return "Non riesco a ottenere informazioni in questo momento."
    
    def can_handle(self, intent_type: str) -> bool:
        """API tools gestiscono meteo e news"""
        return intent_type in ["weather", "news"]
    
    async def _get_weather(self, location: str) -> str:
        """Ottiene meteo da location"""
        # Simulazione - in produzione chiamerebbe API reali
        return f"A {location} ci sono 18°C con cielo sereno."
    
    async def _get_news(self) -> str:
        """Ottiene notizie"""
        # Simulazione - in produzione chiamerebbe API reali
        return "Ultime notizie: Non disponibili al momento."

class PsychologicalEngine(BaseEngine):
    """
    PSYCHOLOGICAL - Solo per supporto emotivo
    """
    
    async def generate(self, message: str, params: Dict[str, Any], context: Optional[Dict] = None) -> str:
        """
        Genera risposta di supporto emotivo
        """
        print(f"[PSYCHOLOGICAL] Generating supportive response", flush=True)
        
        try:
            from core.psychological_responder import generate_psychological_response
            
            response = await generate_psychological_response(
                user_message=message,
                detection=context.get("psy_detection", {}) if context else {},
                psy_context=context.get("psy_context", {}) if context else {},
                user_name=context.get("user_name") if context else None
            )
            
            return response
            
        except Exception as e:
            print(f"[PSYCHOLOGICAL] Error: {e}", flush=True)
            return "Sono qui per te. Non sei solo."
    
    def can_handle(self, intent_type: str) -> bool:
        """Psychological gestisce supporto emotivo"""
        return intent_type == "emotional_support"

class VerifiedKnowledgeEngine(BaseEngine):
    """
    VERIFIED KNOWLEDGE - Knowledge base verificato
    """
    
    async def generate(self, message: str, params: Dict[str, Any], context: Optional[Dict] = None) -> str:
        """
        Estrae knowledge verificato
        """
        print(f"[VERIFIED_KNOWLEDGE] Extracting verified info", flush=True)
        
        try:
            from core.verified_knowledge import verified_knowledge
            
            knowledge_type = params.get("knowledge_type", "")
            
            if knowledge_type == "historical_info":
                data = verified_knowledge.get_historical_info(message)
            else:
                data = verified_knowledge.get_general_info(message)
            
            if data.get("verified", False):
                return data.get("content", "Informazione non disponibile.")
            elif params.get("fallback_to_gpt", False):
                # Delega a GPT-full
                gpt_engine = GPTFullEngine()
                return await gpt_engine.generate(message, params, context)
            else:
                return "Informazione verificata non disponibile."
                
        except Exception as e:
            print(f"[VERIFIED_KNOWLEDGE] Error: {e}", flush=True)
            return "Non posso accedere alle informazioni verifiche."
    
    def can_handle(self, intent_type: str) -> bool:
        """Verified knowledge gestisce knowledge verificato"""
        return intent_type in ["verified_knowledge", "historical_info"]

# Registry motori
class EngineRegistry:
    """Registry centrale per tutti i motori"""
    
    def __init__(self):
        self.engines = {
            "gpt_full": GPTFullEngine(),
            "personalplex": PersonalplexEngine(),
            "api_tools": APIToolsEngine(),
            "psychological": PsychologicalEngine(),
            "verified_knowledge": VerifiedKnowledgeEngine()
        }
    
    def get_engine(self, engine_type: str) -> BaseEngine:
        """Ottiene motore per tipo"""
        return self.engines.get(engine_type, self.engines["personalplex"])
    
    async def generate_with_engine(self, engine_type: str, message: str, params: Dict[str, Any], context: Optional[Dict] = None) -> str:
        """
        Genera risposta con motore specifico
        """
        engine = self.get_engine(engine_type)
        
        if not engine.can_handle(params.get("intent_type", "")):
            print(f"[ENGINE_REGISTRY] Engine {engine_type} cannot handle intent, fallback to personalplex", flush=True)
            engine = self.get_engine("personalplex")
        
        return await engine.generate(message, params, context)

# Istanza globale
engine_registry = EngineRegistry()
