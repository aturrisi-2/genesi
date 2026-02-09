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
    
    def __init__(self, backend_url: str = "http://localhost:8080/completion", timeout: int = 8, max_retries: int = 0):
        self.backend_url = backend_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.model_path = "/opt/models/llama-2-7b-chat.Q4_K_M.gguf"
        self.ctx_size = 2048
        self.max_tokens = 256
        self.temperature = 0.7
    
        
    # HEALTH CHECK RIMOSSO - nessuna chiamata ridondante per velocità
    
    def generate(self, prompt: str, max_tokens: int = None, temperature: float = None, mode: str = "normal") -> str:
        """
        Genera testo con PersonalPlex 7B via llama.cpp diretto
        
        Args:
            prompt: Prompt per generazione
            max_tokens: Token massimi (default 256)
            temperature: Temperatura (default 0.7)
            mode: Modalità (ignorata per semplicità)
            
        Returns:
            Testo generato
        """
        start_time = time.time()
        
        # Usa parametri di configurazione
        if max_tokens is None:
            max_tokens = self.max_tokens
        if temperature is None:
            temperature = self.temperature
        
        try:
            # Prepara prompt per llama.cpp (formato chat)
            formatted_prompt = f"[INST] {prompt} [/INST]"
            
            # Payload llama.cpp diretto
            payload = {
                "prompt": formatted_prompt,
                "model": self.model_path,
                "n_predict": max_tokens,
                "temperature": temperature,
                "ctx_size": self.ctx_size,
                "n_threads": 4,  # CPU threads
                "stop": ["</s>", "[INST]", "[/INST]"],
                "seed": -1,
                "repeat_penalty": 1.1
            }
            
            response = requests.post(
                self.backend_url,
                json=payload,
                timeout=self.timeout,  # 8s hard timeout
                headers={"Content-Type": "application/json"}
            )
            
            latency = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                result = response.json()
                
                # Estrai contenuto da llama.cpp
                if "content" in result:
                    content = result["content"].strip()
                    tokens_count = len(content.split())
                    
                    # Log UNA riga come richiesto
                    logger.info(f"latency_ms={latency:.0f}, tokens_generated={tokens_count}, model=llama-2-7b-chat")
                    
                    return content
                else:
                    logger.error(f"latency_ms={latency:.0f}, tokens_generated=0, model=llama-2-7b-chat, error=invalid_response")
                    return ""
            else:
                logger.error(f"latency_ms={latency:.0f}, tokens_generated=0, model=llama-2-7b-chat, error=http_{response.status_code}")
                return ""
                
        except requests.exceptions.Timeout:
            latency = (time.time() - start_time) * 1000
            logger.warning(f"latency_ms={latency:.0f}, tokens_generated=0, model=llama-2-7b-chat, error=timeout")
            return "Scusa, ci ho messo troppo tempo. Riprova."
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            logger.error(f"latency_ms={latency:.0f}, tokens_generated=0, model=llama-2-7b-chat, error={e}")
            return "Scusa, c'è stato un problema. Riprova."

# Istanza globale
local_llm = LocalLLM()
