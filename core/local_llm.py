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
    
    def __init__(self, backend_url: str = "http://localhost:8001/v1/chat/completions", timeout: int = 0.6, max_retries: int = 0):
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
    
    def generate(self, prompt: str, max_tokens: int = 50, temperature: float = 0.5, mode: str = "presence") -> str:
        """
        Genera testo con PersonalPlex 7B in modalità ultra-veloce
        
        Args:
            prompt: Prompt per generazione
            max_tokens: Token massimi da generare (default 50 per mode presence)
            temperature: Temperatura per generazione (default 0.5)
            mode: Modalità "presence" per risposte ultra-veloci
            
        Returns:
            Testo generato
        """
        start_time = time.time()
        
        try:
            # NO health check per latenza ultra-veloce
            # if not self._health_check():
            #     logger.error("[PERSONALPLEX] Service down - cannot generate")
            #     return ""
            
            # System message ottimizzato per mode presence
            if mode == "presence":
                system_msg = "Tu sei Genesi. Rispondi in 1-2 frasi max. Presenza, dialogo breve."
                max_tokens = min(max_tokens, 30)  # Forza max 30 token per presence
                temperature = 0.3  # Più basso per risposte brevi
            else:
                system_msg = "Tu sei Genesi. Un amico vero. Rispondi in italiano in modo naturale e diretto."
            
            # Prepara payload OpenAI-compatible ottimizzato
            payload = {
                "model": "mistral-7b-instruct",
                "messages": [
                    {"role": "system", "content": system_msg},
                    {"role": "user", "content": prompt}
                ],
                "max_tokens": max_tokens,
                "temperature": temperature,
                "stream": False
            }
            
            logger.info(f"[PERSONALPLEX_7B] generate=true mode={mode} prompt='{prompt[:30]}...'")
            
            response = requests.post(
                "http://localhost:8001/v1/chat/completions",
                json=payload,
                timeout=self.timeout,  # 600ms hard timeout
                headers={"Content-Type": "application/json"}
            )
            
            latency = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                result = response.json()
                
                # Estrai contenuto da formato OpenAI
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"].strip()
                    logger.info(f"[PERSONALPLEX_7B] success latency={latency:.0f}ms mode={mode} tokens={len(content.split())}")
                    return content
                else:
                    latency = (time.time() - start_time) * 1000
                    logger.error(f"[PERSONALPLEX_7B] error=invalid_response latency={latency:.0f}ms mode={mode}")
                    return ""
            else:
                latency = (time.time() - start_time) * 1000
                logger.error(f"[PERSONALPLEX_7B] error=http_{response.status_code} latency={latency:.0f}ms mode={mode}")
                return ""
                
        except requests.exceptions.Timeout:
            latency = (time.time() - start_time) * 1000
            logger.warning(f"[PERSONALPLEX_7B] timeout latency={latency:.0f}ms mode={mode}")
            return ""
        except requests.exceptions.ConnectionError:
            latency = (time.time() - start_time) * 1000
            logger.error(f"[PERSONALPLEX_7B] connection_error latency={latency:.0f}ms mode={mode}")
            return ""
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            logger.error(f"[PERSONALPLEX_7B] error={e} latency={latency:.0f}ms mode={mode}")
            return ""

# Istanza globale
local_llm = LocalLLM()
