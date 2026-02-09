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
    
    def __init__(self, backend_url: str = "http://localhost:8080/completion", timeout: int = 1.2, max_retries: int = 0):
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
            # Formato LLaMA 2 OBBLIGATORIO
            system_prompt = "Tu sei Genesi. Rispondi in modo naturale e conversazionale."
            formatted_prompt = f"<s>[INST] <<SYS>>\n{system_prompt}\n<</SYS>>\n\n{prompt}\n[/INST]"
            
            # Payload llama.cpp ultra-ottimizzato
            payload = {
                "prompt": formatted_prompt,
                "model": self.model_path,
                "n_predict": min(max_tokens, 25),  # Max 25 token
                "temperature": temperature,
                "top_p": self.top_p,
                "ctx_size": self.ctx_size,
                "n_threads": 4,
                "stop": ["</s>", "[INST]", "[/INST]", "\n", ":", "•", "-"],  # Stop extra
                "seed": -1,
                "repeat_penalty": 1.1,
                "tfs_z": 1.0,  # Token frequency sampling
                "typical_p": 1.0,  # Typical sampling
                "mirostat": 2,  # Mirostat per qualità
                "mirostat_tau": 3.0,  # Target entropy
                "mirostat_eta": 0.1  # Learning rate
            }
            
            response = requests.post(
                self.backend_url,
                json=payload,
                timeout=self.timeout,  # 1.2s hard timeout
                headers={"Content-Type": "application/json"}
            )
            
            latency = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                result = response.json()
                
                # Estrai contenuto da llama.cpp
                if "content" in result:
                    content = result["content"].strip()
                    tokens_count = len(content.split())
                    
                    # Log UNA riga con decisione finale
                    logger.info(f"latency_ms={latency:.0f}, tokens_generated={tokens_count}, model=llama-2-7b-chat, decision=local")
                    
                    return content
                else:
                    logger.error(f"latency_ms={latency:.0f}, tokens_generated=0, model=llama-2-7b-chat, decision=local, error=invalid_response")
                    return ""
            else:
                logger.error(f"latency_ms={latency:.0f}, tokens_generated=0, model=llama-2-7b-chat, decision=local, error=http_{response.status_code}")
                return ""
                
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
            # Formato LLaMA 2 OBBLIGATORIO
            system_prompt = "Tu sei Genesi. Rispondi in modo naturale e conversazionale."
            formatted_prompt = f"<s>[INST] <<SYS>>\n{system_prompt}\n<</SYS>>\n\n{user_message}\n[/INST]"
            
            # Payload ottimizzato per chat
            payload = {
                "prompt": formatted_prompt,
                "model": self.model_path,
                "n_predict": min(self.max_tokens, 25),
                "temperature": 0.7,  # Più creativo per chat
                "top_p": self.top_p,
                "ctx_size": self.ctx_size,
                "n_threads": 4,
                "stop": ["</s>", "[INST]", "[/INST]", "\n", ":", "•", "-"],
                "seed": -1,
                "repeat_penalty": 1.1
            }
            
            response = requests.post(
                self.backend_url,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            
            latency = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                result = response.json()
                if "content" in result:
                    content = result["content"].strip()
                    tokens_count = len(content.split())
                    logger.info(f"latency_ms={latency:.0f}, tokens_generated={tokens_count}, model=llama-2-7b-chat, decision=chat")
                    return content
                else:
                    logger.error(f"latency_ms={latency:.0f}, tokens_generated=0, model=llama-2-7b-chat, decision=chat, error=invalid_response")
                    return ""
            else:
                logger.error(f"latency_ms={latency:.0f}, tokens_generated=0, model=llama-2-7b-chat, decision=chat, error=http_{response.status_code}")
                return ""
                
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
            # Formato LLaMA 2 OBBLIGATORIO
            system_prompt = "Tu sei Genesi. Riassumi le informazioni in modo strutturato e conciso."
            formatted_prompt = f"<s>[INST] <<SYS>>\n{system_prompt}\n<</SYS>>\n\nCONTESTO: {memory_context}\n\nRIASSUNTO:\n[/INST]"
            
            # Payload ottimizzato per memoria
            payload = {
                "prompt": formatted_prompt,
                "model": self.model_path,
                "n_predict": min(self.max_tokens, 50),  # Più token per memoria
                "temperature": 0.3,  # Più preciso per memoria
                "top_p": 0.8,
                "ctx_size": self.ctx_size,
                "n_threads": 4,
                "stop": ["</s>", "[INST]", "[/INST]"],
                "seed": -1,
                "repeat_penalty": 1.1
            }
            
            response = requests.post(
                self.backend_url,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            
            latency = (time.time() - start_time) * 1000
            
            if response.status_code == 200:
                result = response.json()
                if "content" in result:
                    content = result["content"].strip()
                    tokens_count = len(content.split())
                    logger.info(f"latency_ms={latency:.0f}, tokens_generated={tokens_count}, model=llama-2-7b-chat, decision=memory")
                    return content
                else:
                    logger.error(f"latency_ms={latency:.0f}, tokens_generated=0, model=llama-2-7b-chat, decision=memory, error=invalid_response")
                    return ""
            else:
                logger.error(f"latency_ms={latency:.0f}, tokens_generated=0, model=llama-2-7b-chat, decision=memory, error=http_{response.status_code}")
                return ""
                
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
