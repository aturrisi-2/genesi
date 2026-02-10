"""
PROACTOR - Genesi Core v2
Orchestratore centrale per smistamento modelli
Chat libera → Qwen2.5-7B-Instruct
Tecnica → GPT/GPT-Mini
Fallback → GPT
"""

from typing import Optional, Dict, Any
from core.local_llm import LocalLLM
from core.log import log

class Proactor:
    """
    Proactor - Cervello di smistamento
    Decide IL modello in base a intent e complessità
    """
    
    def __init__(self):
        self.qwen = LocalLLM()
        self.gpt_available = False  # TODO: implementare GPT client
        
        # Intent per Qwen2.5-7B-Instruct (chat libera)
        self.qwen_intents = [
            "chat_free",
            "greeting", 
            "how_are_you",
            "identity",
            "goodbye",
            "help"
        ]
        
        # Intent per GPT (tecnica)
        self.gpt_intents = [
            "tecnica",
            "debug",
            "spiegazione",
            "architettura",
            "istruzioni_complesse"
        ]
    
    def decide_engine(self, intent: str, message: str = "") -> str:
        """
        Decide IL modello - logica MINIMA
        
        Args:
            intent: Intent classificato
            message: Messaggio originale (per fallback)
            
        Returns:
            Engine: "QWEN", "GPT", o "GPT_FALLBACK"
        """
        try:
            # Logica MINIMA come richiesto
            if intent in self.qwen_intents:
                engine = "QWEN"
            elif intent in self.gpt_intents:
                engine = "GPT"
            else:
                # Default: Qwen per tutto il resto
                engine = "QWEN"
            
            log("PROACTOR_DECISION", intent=intent, engine=engine, message=message[:50])
            return engine
            
        except Exception as e:
            log("PROACTOR_ERROR", error=str(e))
            return "QWEN"  # Fallback sicuro
    
    def generate_response(self, intent: str, message: str) -> Optional[str]:
        """
        Genera risposta usando IL modello deciso
        
        Args:
            intent: Intent classificato
            message: Messaggio originale
            
        Returns:
            Risposta generata o None
        """
        engine = self.decide_engine(intent, message)
        
        try:
            if engine == "QWEN":
                return self._generate_qwen(message)
            elif engine == "GPT":
                return self._generate_gpt(message)
            elif engine == "GPT_FALLBACK":
                return self._generate_gpt_fallback(message)
            else:
                return None
                
        except Exception as e:
            log("PROACTOR_GENERATION_ERROR", engine=engine, error=str(e))
            return None
    
    def _generate_qwen(self, message: str) -> Optional[str]:
        """
        Genera con Qwen2.5-7B-Instruct
        Chat libera, saluti, relazione, presenza
        """
        try:
            # Prompt lineare per Qwen come richiesto
            prompt = f"<|im_start|>user\n{message}\n<|im_end|>\n<|im_start|>assistant\n"
            
            response = self.qwen.generate_chat_response(prompt)
            return response
            
        except Exception as e:
            log("QWEN_GENERATION_ERROR", error=str(e))
            return None
    
    def _generate_gpt(self, message: str) -> Optional[str]:
        """
        Genera con GPT
        Tecnica, spiegazioni, debugging, architettura
        """
        try:
            # TODO: Implementare client GPT
            log("GPT_NOT_IMPLEMENTED", message=message[:50])
            return "GPT non ancora implementato. Uso Qwen come fallback."
            
        except Exception as e:
            log("GPT_GENERATION_ERROR", error=str(e))
            return None
    
    def _generate_gpt_fallback(self, message: str) -> Optional[str]:
        """
        Fallback GPT in caso di errore locale
        """
        try:
            # TODO: Implementare client GPT fallback
            log("GPT_FALLBACK_NOT_IMPLEMENTED", message=message[:50])
            return "GPT fallback non ancora implementato."
            
        except Exception as e:
            log("GPT_FALLBACK_ERROR", error=str(e))
            return None
    
    def get_engine_stats(self) -> Dict[str, Any]:
        """
        Statistiche motori disponibili
        """
        return {
            "qwen_available": self.qwen.is_available(),
            "gpt_available": self.gpt_available,
            "qwen_intents": self.qwen_intents,
            "gpt_intents": self.gpt_intents
        }

# Istanza globale
proactor = Proactor()
