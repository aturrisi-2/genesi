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
    
    def __init__(self, backend_url: str = "http://127.0.0.1:8080/chat/completions", timeout: int = 1.2, max_retries: int = 0):
        self.backend_url = backend_url
        self.timeout = timeout
        self.max_retries = max_retries
        self.model_path = "/opt/models/llama-2-7b-chat.Q4_K_M.gguf"
        self.ctx_size = 512  # Ridotto per velocità
        self.max_tokens = 32  # Hard limit per < 1200ms
        self.temperature = 0.6  # Ridotto per risposte brevi
        self.top_p = 0.9  # Hard limit
    
        
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
            # LOG DEBUG OBBLIGATORIO
            system_prompt = "Tu sei Genesi. Rispondi in modo naturale e conversazionale."
            
            # Payload ESATTO per /chat/completions
            payload = {
                "model": "llama-2-7b-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.2,
                "max_tokens": 256
            }
            
            print(f"[DEBUG] PAYLOAD: {json.dumps(payload, indent=2)}", flush=True)
            
            response = requests.post(
                self.backend_url,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            
            latency = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                result = response.json()
                print(f"[DEBUG] RESPONSE: {json.dumps(result, indent=2)}", flush=True)
                
                # RESPONSE PARSING OBBLIGATORIO
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    
                    if not content or not content.strip():
                        raise Exception("Content vuoto da llama-server")
                    
                    content = content.strip()
                    tokens_count = len(content.split())
                    
                    print(f"[DEBUG] CONTENT_LENGTH: {len(content)} tokens: {tokens_count}", flush=True)
                    logger.info(f"latency_ms={latency:.0f}, tokens_generated={tokens_count}, model=llama-2-7b-chat, decision=local")
                    
                    return content
                else:
                    raise Exception("Response senza 'choices' da llama-server")
            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
                
        except requests.exceptions.Timeout:
            latency = (time.time() - start_time) * 1000
            logger.warning(f"latency_ms={latency:.0f}, tokens_generated=0, model=llama-2-7b-chat, error=timeout")
            return ""  # NESSUN fallback - solo llama.cpp
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            logger.error(f"latency_ms={latency:.0f}, tokens_generated=0, model=llama-2-7b-chat, error={e}")
            return ""  # NESSUN fallback - solo llama.cpp
    
    def generate_chat_response(self, user_message: str) -> str:
        """
        Genera risposta chat conversazionale naturale
        
        Args:
            user_message: Messaggio utente naturale
            
        Returns:
            Risposta conversazionale naturale (1 frase max)
        """
        start_time = time.time()
        
        try:
            # LOG DEBUG OBBLIGATORIO
            system_prompt = "Tu sei Genesi. Rispondi in modo naturale e conversazionale."
            
            # Payload ESATTO per /chat/completions
            payload = {
                "model": "llama-2-7b-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                "temperature": 0.7,
                "max_tokens": 256
            }
            
            print(f"[DEBUG] CHAT PAYLOAD: {json.dumps(payload, indent=2)}", flush=True)
            
            response = requests.post(
                self.backend_url,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            
            latency = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                result = response.json()
                print(f"[DEBUG] CHAT RESPONSE: {json.dumps(result, indent=2)}", flush=True)
                
                # RESPONSE PARSING OBBLIGATORIO
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    
                    if not content or not content.strip():
                        raise Exception("Chat content vuoto da llama-server")
                    
                    content = content.strip()
                    tokens_count = len(content.split())
                    
                    print(f"[DEBUG] CHAT CONTENT_LENGTH: {len(content)} tokens: {tokens_count}", flush=True)
                    logger.info(f"latency_ms={latency:.0f}, tokens_generated={tokens_count}, model=llama-2-7b-chat, decision=chat")
                    
                    return content
                else:
                    raise Exception("Chat response senza 'choices' da llama-server")
            else:
                raise Exception(f"Chat HTTP {response.status_code}: {response.text}")
                
        except requests.exceptions.Timeout:
            latency = (time.time() - start_time) * 1000
            logger.warning(f"latency_ms={latency:.0f}, tokens_generated=0, model=llama-2-7b-chat, error=timeout")
            return ""  # NESSUN fallback - solo llama.cpp
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            logger.error(f"latency_ms={latency:.0f}, tokens_generated=0, model=llama-2-7b-chat, error={e}")
            return ""  # NESSUN fallback - solo llama.cpp
    
    def generate_memory_summary(self, memory_context: str) -> str:
        """
        Genera riassunto memoria strutturata
        
        Args:
            memory_context: Contesto memoria da riassumere
            
        Returns:
            Riassunto strutturato della memoria
        """
        start_time = time.time()
        
        try:
            # LOG DEBUG OBBLIGATORIO
            system_prompt = "Tu sei Genesi. Riassumi le informazioni in modo strutturato e conciso."
            
            # Payload ESATTO per /chat/completions
            payload = {
                "model": "llama-2-7b-chat",
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"CONTESTO: {memory_context}\n\nRIASSUNTO:"}
                ],
                "temperature": 0.3,
                "max_tokens": 256
            }
            
            print(f"[DEBUG] MEMORY PAYLOAD: {json.dumps(payload, indent=2)}", flush=True)
            
            response = requests.post(
                self.backend_url,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            
            latency = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                result = response.json()
                print(f"[DEBUG] MEMORY RESPONSE: {json.dumps(result, indent=2)}", flush=True)
                
                # RESPONSE PARSING OBBLIGATORIO
                if "choices" in result and len(result["choices"]) > 0:
                    content = result["choices"][0]["message"]["content"]
                    
                    if not content or not content.strip():
                        raise Exception("Memory content vuoto da llama-server")
                    
                    content = content.strip()
                    tokens_count = len(content.split())
                    
                    print(f"[DEBUG] MEMORY CONTENT_LENGTH: {len(content)} tokens: {tokens_count}", flush=True)
                    logger.info(f"latency_ms={latency:.0f}, tokens_generated={tokens_count}, model=llama-2-7b-chat, decision=memory")
                    
                    return content
                else:
                    raise Exception("Memory response senza 'choices' da llama-server")
            else:
                raise Exception(f"Memory HTTP {response.status_code}: {response.text}")
                
        except requests.exceptions.Timeout:
            latency = (time.time() - start_time) * 1000
            logger.warning(f"latency_ms={latency:.0f}, tokens_generated=0, model=llama-2-7b-chat, error=timeout")
            return ""  # NESSUN fallback - solo llama.cpp
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            logger.error(f"latency_ms={latency:.0f}, tokens_generated=0, model=llama-2-7b-chat, error={e}")
            return ""  # NESSUN fallback - solo llama.cpp

# Istanza globale
local_llm = LocalLLM()
