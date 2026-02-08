"""
Local LLM Module - PersonalPlex 7B Integration
Modulo per analisi cognitiva primaria con modello locale NVIDIA
"""

import logging
import requests
import json
import time
from typing import Dict, Any

logger = logging.getLogger(__name__)

class LocalLLM:
    """Interfaccia per PersonalPlex 7B via backend locale NVIDIA"""
    
    def __init__(self, backend_url: str = "http://localhost:8001/analyze", timeout: int = 15, max_retries: int = 1):
        self.backend_url = backend_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.health_url = "http://localhost:8001/health"
    
    def analyze(self, text: str) -> Dict[str, Any]:
        """
        Analizza testo con PersonalPlex 7B
        
        Args:
            text: Testo da analizzare (output STT)
            
        Returns:
            Dict con:
            - intent: string (tipo di intento rilevato)
            - confidence: float (0.0-1.0)
            - response: string (risposta generata)
            - latency_ms: float (latenza chiamata)
            - technical_error: bool (errore tecnico)
        """
        start_time = time.time()
        
        # Health check prima di procedere
        if not self._health_check():
            logger.error("[PERSONALPLEX] Service down - cannot analyze")
            return {
                "intent": "error",
                "confidence": 0.0,
                "response": "",
                "latency_ms": 0.0,
                "technical_error": True
            }
        
        # Retry logic
        for attempt in range(self.max_retries + 1):
            try:
                logger.info(f"[PERSONALPLEX] called=true attempt={attempt+1} text='{text[:50]}...'")
                
                payload = {"text": text}
                
                response = requests.post(
                    self.backend_url,
                    json=payload,
                    timeout=self.timeout,
                    headers={"Content-Type": "application/json"}
                )
                
                latency = (time.time() - start_time) * 1000
                
                if response.status_code == 200:
                    result = response.json()
                    
                    # Estrai dati dalla risposta PersonalPlex
                    intent = result.get("intent", "conversation")
                    confidence = result.get("confidence", 0.5)
                    response_text = result.get("response", "")
                    
                    logger.info(f"[PERSONALPLEX] success=true latency={latency:.1f}ms confidence={confidence:.2f}")
                    
                    return {
                        "intent": intent,
                        "confidence": confidence,
                        "response": response_text,
                        "latency_ms": latency,
                        "technical_error": False
                    }
                else:
                    logger.error(f"[PERSONALPLEX] HTTP error: {response.status_code}")
                    if attempt == self.max_retries:
                        break
                    
            except requests.exceptions.Timeout:
                logger.error(f"[PERSONALPLEX] timeout attempt={attempt+1}")
                if attempt == self.max_retries:
                    break
                    
            except requests.exceptions.ConnectionError:
                logger.error(f"[PERSONALPLEX] connection error attempt={attempt+1}")
                if attempt == self.max_retries:
                    break
                    
            except Exception as e:
                logger.error(f"[PERSONALPLEX] unexpected error attempt={attempt+1}: {e}")
                if attempt == self.max_retries:
                    break
        
        # Tutti i tentativi falliti
        latency = (time.time() - start_time) * 1000
        logger.error(f"[PERSONALPLEX] failed=true latency={latency:.1f}ms attempts={self.max_retries+1}")
        
        return {
            "intent": "error",
            "confidence": 0.0,
            "response": "",
            "latency_ms": latency,
            "technical_error": True
        }
    
    def _health_check(self) -> bool:
        """Verifica che PersonalPlex sia attivo"""
        try:
            response = requests.get(
                self.health_url,
                timeout=5,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                health_data = response.json()
                if health_data.get("status") == "ok":
                    logger.info(f"[PERSONALPLEX] health_check=true model={health_data.get('model','unknown')}")
                    return True
                else:
                    logger.warning(f"[PERSONALPLEX] health_check=false status={health_data.get('status')}")
                    return False
            else:
                logger.warning(f"[PERSONALPLEX] health_check=false http={response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"[PERSONALPLEX] health_check=false error={e}")
            return False

# Istanza globale
local_llm = LocalLLM()
