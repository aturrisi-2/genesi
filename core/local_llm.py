"""
Local LLM Module - PersonalPlex 7B Integration
Modulo per analisi cognitiva secondaria con modello locale NVIDIA
"""

import logging
import requests
import json
from typing import Dict, Any

logger = logging.getLogger(__name__)

class LocalLLM:
    """Interfaccia per PersonalPlex 7B via backend locale NVIDIA"""
    
    def __init__(self, backend_url: str = "http://localhost:8001/analyze"):
        self.backend_url = backend_url
        self.timeout = 10
    
    def analyze(self, text: str) -> Dict[str, Any]:
        """
        Analizza testo con PersonalPlex 7B
        
        Args:
            text: Testo da analizzare (output STT)
            
        Returns:
            Dict con:
            - intent: string (tipo di intento rilevato)
            - confidence: float (0.0-1.0)
            - clean_text: string (testo pulito)
            - is_noise: bool (se è rumore/nonsense)
            - should_escalate: bool (se passare a ChatGPT)
        """
        try:
            payload = {
                "text": text,
                "model": "personalplex_7b",
                "task": "noise_detection_and_intent"
            }
            
            response = requests.post(
                self.backend_url,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                result = response.json()
                
                # Validazione output obbligatorio
                required_keys = ["intent", "confidence", "clean_text", "is_noise", "should_escalate"]
                for key in required_keys:
                    if key not in result:
                        logger.error(f"[LOCAL_LLM] Missing required key: {key}")
                        return self._fallback_analysis(text)
                
                logger.info(f"[LOCAL_LLM] intent={result['intent']} confidence={result['confidence']:.2f} noise={result['is_noise']} escalate={result['should_escalate']}")
                return result
                
            else:
                logger.error(f"[LOCAL_LLM] Backend error: {response.status_code}")
                return self._fallback_analysis(text)
                
        except Exception as e:
            logger.error(f"[LOCAL_LLM] Analysis failed: {e}")
            return self._fallback_analysis(text)
    
    def _fallback_analysis(self, text: str) -> Dict[str, Any]:
        """
        Fallback se backend non disponibile
        Analisi euristica base
        """
        text_clean = text.strip().lower()
        
        # Euristiche base per rumore/nonsense
        noise_indicators = [
            len(text_clean) < 3,  # troppo corto
            text_clean.count(' ') > len(text_clean) / 3,  # troppe parole ripetute
            all(c in 'aeiou' for c in text_clean),  # solo vocali
            text_clean.replace(' ', '').isalpha() and len(set(text_clean.replace(' ', ''))) < 3  # caratteri ripetuti
        ]
        
        is_noise = any(noise_indicators)
        confidence = 0.3 if is_noise else 0.6
        should_escalate = not is_noise and len(text_clean) > 5
        
        result = {
            "intent": "noise" if is_noise else "unknown",
            "confidence": confidence,
            "clean_text": text_clean,
            "is_noise": is_noise,
            "should_escalate": should_escalate
        }
        
        logger.info(f"[LOCAL_LLM] FALLBACK intent={result['intent']} confidence={result['confidence']:.2f} noise={result['is_noise']} escalate={result['should_escalate']}")
        return result

# Istanza globale
local_llm = LocalLLM()
