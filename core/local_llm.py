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
    
    def __init__(self, backend_url: str = "http://localhost:8001/v1/chat/completions", timeout: int = 15, max_retries: int = 1):
        self.backend_url = backend_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.health_url = "http://localhost:8001/health"
    
        
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
    
    def generate(self, prompt: str, max_tokens: int = 200, temperature: float = 0.7) -> str:
        """
        Genera testo con PersonalPlex 7B usando endpoint OpenAI-compatible
        
        Args:
            prompt: Prompt per generazione
            max_tokens: Token massimi da generare
            temperature: Temperatura per generazione
            
        Returns:
            Testo generato
        """
        start_time = time.time()
        
        try:
            # Health check prima di procedere
            if not self._health_check():
                logger.error("[PERSONALPLEX] Service down - cannot generate")
                return ""
            
            # Prepara payload OpenAI-compatible
            payload = {
                "model": "mistral-7b-instruct",
                "messages": [
                    {"role": "system", "content": "Tu sei Genesi. Un amico vero. Rispondi in italiano in modo naturale e diretto."},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False
            }
            
            logger.info(f"[PERSONALPLEX] generate=true prompt='{prompt[:50]}...'")
            
            response = requests.post(
                "http://localhost:8001/v1/chat/completions",
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            
            latency = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                result = response.json()
                
                # Estrai contenuto da formato OpenAI
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"].strip()
                    
                    logger.info(f"[PERSONALPLEX] generate_success=true latency={latency:.1f}ms")
                    return content
                else:
                    logger.error(f"[PERSONALPLEX] generate_error=invalid_response")
                    return ""
            else:
                logger.error(f"[PERSONALPLEX] generate_error=http_{response.status_code}")
                return ""
                
        except requests.exceptions.Timeout:
            logger.error(f"[PERSONALPLEX] generate_error=timeout")
            return ""
        except requests.exceptions.ConnectionError:
            logger.error(f"[PERSONALPLEX] generate_error=connection")
            return ""
        except Exception as e:
            logger.error(f"[PERSONALPLEX] generate_error={e}")
            return ""

# Istanza globale
local_llm = LocalLLM()
