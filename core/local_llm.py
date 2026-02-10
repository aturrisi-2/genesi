"""
Local LLM Module - Qwen2.5-7B-Instruct Integration
Modulo per dialogo minimale e instruction-following rigoroso
"""

import logging
import requests
import json
import time
from typing import Dict, Any

logger = logging.getLogger(__name__)

class LocalLLM:
    """Interfaccia per Qwen2.5-7B-Instruct via backend locale"""
    
    def __init__(self, backend_url: str = "http://127.0.0.1:8080/completion", timeout: int = 25, max_retries: int = 2):
        self.backend_url = backend_url
        self.timeout = timeout
        self.max_retries = max_retries
        # Qwen2.5-7B-Instruct - modello affidabile per dialogo minimale
        self.model_path = "/opt/models/qwen2.5-7b-instruct.Q4_K_M.gguf"
        self.ctx_size = 2048
        self.max_tokens = 80  # Breve e diretto
        self.temperature = 0.35  # Basso per stabilità
        self.top_p = 0.85  # Controllo output
    
    def is_available(self) -> bool:
        """
        VERIFICA CONFIGURAZIONE SENZA CHIAMATE LLM
        REGOLA D'ORO: MAI testare con chiamate reali
        """
        return bool(self.backend_url and self.backend_url.startswith("http"))
    
    def generate(self, prompt: str, max_tokens: int = None, temperature: float = None, mode: str = "normal") -> str:
        """
        Genera testo con retry e backoff per chat_free stabile
        """
        start_time = time.time()
        
        # Usa parametri di configurazione
        if max_tokens is None:
            max_tokens = self.max_tokens
        if temperature is None:
            temperature = self.temperature
        
        # Retry con backoff esponenziale
        for attempt in range(self.max_retries + 1):
            try:
                if attempt > 0:
                    # Backoff esponenziale: 5s, 10s
                    backoff_time = 5 * (2 ** (attempt - 1))
                    print(f"[LOCAL_LLM] Retry {attempt}/{self.max_retries} after {backoff_time}s backoff", flush=True)
                    time.sleep(backoff_time)
                
                # LOG OBBLIGATORI
                system_prompt = ""  # NESSUN system prompt - usa direttamente prompt
                
                # Usa direttamente il prompt SENZA wrapping
                full_prompt = prompt  # Prompt già formattato con [INST]...[/INST]
                print(f"[DEBUG] PROMPT: {full_prompt}", flush=True)
                
                # Payload ESATTO per /completion
                payload = {
                    "prompt": full_prompt,
                    "n_predict": max_tokens,
                    "temperature": temperature,
                    "top_p": self.top_p,
                    "stop": ["</s>", "<|endoftext|>", "<|im_end|>"]
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
                    data = response.json()
                    content = data.get("content", "").strip()
                    
                    if content:
                        tokens = len(content.split())
                        logger.info(f"latency_ms={latency:.0f}, tokens_generated={tokens}, model=qwen2.5-7b-instruct")
                        return content
                    else:
                        print(f"[LOCAL_LLM] Empty content on attempt {attempt + 1}", flush=True)
                        continue
                else:
                    raise Exception(f"HTTP {response.status_code}: {response.text}")
                    
            except requests.exceptions.Timeout:
                latency = (time.time() - start_time) * 1000
                print(f"[LOCAL_LLM] Timeout on attempt {attempt + 1}/{self.max_retries + 1}", flush=True)
                if attempt == self.max_retries:
                    logger.warning(f"latency_ms={latency:.0f}, tokens_generated=0, model=mistral-7b-instruct, error=timeout_after_retries")
                    return ""  # Solo dopo tutti i retry
                continue
                
            except Exception as e:
                latency = (time.time() - start_time) * 1000
                print(f"[LOCAL_LLM] Error on attempt {attempt + 1}/{self.max_retries + 1}: {e}", flush=True)
                if attempt == self.max_retries:
                    logger.error(f"latency_ms={latency:.0f}, tokens_generated=0, model=mistral-7b-instruct, error={e}")
                    return ""  # Solo dopo tutti i retry
                continue
        
        return ""
    
    def generate_chat_response(self, prompt_text: str) -> str:
        """
        Genera risposta chat con Qwen2.5-7B-Instruct
        Formato richiesto: <|im_start|>user\n{message}<|im_end|>\n<|im_start|>assistant\n
        
        Args:
            prompt_text: Testo del prompt lineare
            
        Returns:
            Stringa generata dal modello o None se errore
        """
        start_time = time.time()
        
        try:
            # Prompt lineare per Qwen2.5-7B-Instruct come richiesto
            prompt = f"<|im_start|>user\n{prompt_text}<|im_end|>\n<|im_start|>assistant\n"
            
            # Payload per llama.cpp con parametri bloccati
            payload = {
                "prompt": prompt,
                "n_predict": 80,
                "temperature": 0.35,
                "top_p": 0.85,
                "stop": ["<|im_start|>", "</s>"]
            }
            
            response = requests.post(
                self.backend_url,
                json=payload,
                timeout=self.timeout,
                headers={"Content-Type": "application/json"}
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Parsing difensivo per entrambi i formati
                if "content" in data:
                    content = data["content"]
                elif "choices" in data and len(data["choices"]) > 0:
                    content = data["choices"][0].get("text", "")
                else:
                    content = ""
                
                # Restituisci solo se non vuoto
                if content and content.strip():
                    return content.strip()
                else:
                    logger.error(f"Empty response from llama-server")
                    return None
            else:
                raise Exception(f"HTTP {response.status_code}: {response.text}")
                
        except Exception as e:
            logger.error(f"Chat generation error: {e}")
            return None
    
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
            # LOG OBBLIGATORI
            system_prompt = "Rispondi SEMPRE e SOLO in italiano. Non usare mai l'inglese, nemmeno singole parole, espressioni o frasi. Se l'utente scrive in italiano, rispondi esclusivamente in italiano. Tu sei Genesi. Riassumi le informazioni in modo strutturato e conciso."
            
            # Costruisci prompt LLaMA puro
            prompt = f"<s>[INST] {system_prompt}\n\nCONTESTO: {memory_context}\n\nRIASSUNTO: [/INST]"
            print(f"[DEBUG] MEMORY PROMPT: {prompt}", flush=True)
            
            # Payload ESATTO per /completion
            payload = {
                "prompt": prompt,
                "n_predict": 256,
                "temperature": 0.3
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
                
                # Parsing RISPOSTA: SOLO response["content"]
                if "content" in result:
                    content = result["content"].strip()
                    
                    # SE HTTP 200 e content non vuoto → RISPOSTA SEMPRE VALIDA
                    if not content:
                        raise Exception("Memory content vuoto da llama-server")
                    
                    tokens_count = len(content.split())
                    
                    print(f"[DEBUG] MEMORY CONTENT_LENGTH: {len(content)} tokens: {tokens_count}", flush=True)
                    print(f"[DEBUG] MEMORY RISPOSTA ACCETTATA: '{content}'", flush=True)
                    
                    # Log INFO per risposte accettate anche se lente
                    if latency > 2000:  # Se più di 2 secondi
                        logger.info(f"MEMORY RISPOSTA LENTA MA ACCETTATA: latency_ms={latency:.0f}, tokens_generated={tokens_count}, model=mistral-7b-instruct, decision=memory")
                    else:
                        logger.info(f"latency_ms={latency:.0f}, tokens_generated={tokens_count}, model=mistral-7b-instruct, decision=memory")
                    
                    return content
                else:
                    raise Exception("Memory response senza 'content' da llama-server")
            else:
                raise Exception(f"Memory HTTP {response.status_code}: {response.text}")
                
        except requests.exceptions.Timeout:
            latency = (time.time() - start_time) * 1000
            logger.warning(f"latency_ms={latency:.0f}, tokens_generated=0, model=mistral-7b-instruct, error=timeout")
            return ""  # NESSUN fallback - solo llama.cpp
        except Exception as e:
            latency = (time.time() - start_time) * 1000
            logger.error(f"latency_ms={latency:.0f}, tokens_generated=0, model=mistral-7b-instruct, error={e}")
            return ""  # NESSUN fallback - solo llama.cpp

# Istanza globale
local_llm = LocalLLM()
