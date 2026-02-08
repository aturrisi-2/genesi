#!/usr/bin/env python3
"""
PersonalPlex 7B Server - LLM Locale per Genesi
Servizio HTTP per modello locale NVIDIA
"""

import os
import sys
import json
import time
import logging
import asyncio
from typing import Dict, Any
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# FastAPI per server HTTP
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    print("ERRORE: Installare dipendenze con: pip install fastapi uvicorn pydantic")
    sys.exit(1)

# PyTorch e Transformers
try:
    import torch
    from transformers import AutoTokenizer, AutoModelForCausalLM, pipeline
    logger.info("[PERSONALPLEX] PyTorch available: " + str(torch.__version__))
    logger.info("[PERSONALPLEX] CUDA available: " + str(torch.cuda.is_available()))
    if torch.cuda.is_available():
        logger.info("[PERSONALPLEX] GPU device: " + torch.cuda.get_device_name(0))
except ImportError:
    print("ERRORE: Installare PyTorch con: pip install torch transformers")
    sys.exit(1)

# Modelli Pydantic per API
class AnalyzeRequest(BaseModel):
    text: str

class GenerateRequest(BaseModel):
    prompt: str
    max_length: int = 200
    temperature: float = 0.7

class AnalyzeResponse(BaseModel):
    intent: str
    confidence: float
    response: str

class GenerateResponse(BaseModel):
    response: str
    latency_ms: float

class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    device: str

# App FastAPI
app = FastAPI(title="PersonalPlex 7B Server", version="1.0.0")

# CORS per permettere chiamate da Genesi
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Variabili globali per modello
model = None
tokenizer = None
generator = None
MODEL_NAME = "microsoft/DialoGPT-medium"  # Modello leggero per test
# MODEL_NAME = "mistralai/Mistral-7B-Instruct-v0.2"  # Per produzione

def load_model():
    """Carica modello PersonalPlex 7B"""
    global model, tokenizer, generator
    
    try:
        logger.info("[PERSONALPLEX] Loading model: " + MODEL_NAME)
        
        # Device selection
        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info(f"[PERSONALPLEX] Using device: {device}")
        
        # Carica tokenizer e modello
        tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        
        model = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            device_map="auto" if device == "cuda" else None,
            low_cpu_mem_usage=True
        )
        
        # Crea pipeline per generazione
        generator = pipeline(
            "text-generation",
            model=model,
            tokenizer=tokenizer,
            device=0 if device == "cuda" else -1,
            torch_dtype=torch.float16 if device == "cuda" else torch.float32
        )
        
        logger.info("[PERSONALPLEX] Model loaded successfully")
        logger.info(f"[PERSONALPLEX] Model parameters: {model.num_parameters():,}")
        
        return True
        
    except Exception as e:
        logger.error(f"[PERSONALPLEX] Error loading model: {e}")
        return False

def classify_intent(text: str) -> tuple[str, float]:
    """Classifica intent e confidence dal testo"""
    
    # Classificazione semplice basata su parole chiave
    text_lower = text.lower().strip()
    
    # Pattern di intent comuni
    intent_patterns = {
        "greeting": ["ciao", "salve", "buongiorno", "buonasera", "hey"],
        "question": ["come", "cosa", "dove", "quando", "perché", "quale"],
        "request": ["puoi", "potresti", "vorrei", "mi dici", "raccontami"],
        "help": ["aiuto", "help", "problema", "difficoltà"],
        "farewell": ["arrivederci", "ciao", "a dopo", "buonanotte"],
        "complaint": ["male", "dolore", "fastidio", "problema", "non funziona"],
        "conversation": []  # default
    }
    
    # Calcola confidence per ogni intent
    best_intent = "conversation"
    best_confidence = 0.3  # base confidence
    
    for intent, keywords in intent_patterns.items():
        if not keywords:
            continue
            
        matches = sum(1 for keyword in keywords if keyword in text_lower)
        confidence = matches / len(keywords) if keywords else 0
        
        if confidence > best_confidence:
            best_intent = intent
            best_confidence = confidence
    
    # Confidence minima 0.1, massima 0.9
    best_confidence = max(0.1, min(0.9, best_confidence + 0.2))
    
    return best_intent, best_confidence

def generate_response(text: str, max_length: int = 200, temperature: float = 0.7) -> str:
    """Genera risposta con PersonalPlex 7B"""
    
    try:
        if not generator:
            raise Exception("Model not loaded")
        
        # Prepara prompt
        prompt = f"User: {text}\nAssistant:"
        
        # Genera risposta
        start_time = time.time()
        
        outputs = generator(
            prompt,
            max_new_tokens=max_length,
            temperature=temperature,
            do_sample=True,
            pad_token_id=tokenizer.eos_token_id,
            num_return_sequences=1
        )
        
        latency = (time.time() - start_time) * 1000
        
        # Estrai risposta
        generated_text = outputs[0]["generated_text"]
        
        # Rimuovi prompt originale
        if prompt in generated_text:
            response = generated_text.replace(prompt, "").strip()
        else:
            response = generated_text.strip()
        
        # Pulizia finale
        response = response.split("\n")[0].strip()  # Prima linea solo
        if not response:
            response = "Non ho una risposta per questo."
        
        logger.info(f"[PERSONALPLEX] Generated response in {latency:.1f}ms")
        return response
        
    except Exception as e:
        logger.error(f"[PERSONALPLEX] Error generating response: {e}")
        return "Mi dispiace, ho avuto un problema nel generare una risposta."

# API Endpoints
@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check endpoint"""
    
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model_loaded = model is not None
    
    return HealthResponse(
        status="ok",
        model_loaded=model_loaded,
        device=device
    )

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """Analizza testo e classifica intent"""
    
    start_time = time.time()
    
    try:
        # Classifica intent
        intent, confidence = classify_intent(request.text)
        
        # Genera risposta
        response = generate_response(request.text)
        
        latency = (time.time() - start_time) * 1000
        
        logger.info(f"[PERSONALPLEX] called=true latency={latency:.1f}ms confidence={confidence:.2f}")
        
        return AnalyzeResponse(
            intent=intent,
            confidence=confidence,
            response=response
        )
        
    except Exception as e:
        logger.error(f"[PERSONALPLEX] Error in analyze: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest):
    """Genera testo da prompt"""
    
    start_time = time.time()
    
    try:
        response = generate_response(
            request.prompt,
            max_length=request.max_length,
            temperature=request.temperature
        )
        
        latency = (time.time() - start_time) * 1000
        
        logger.info(f"[PERSONALPLEX] generate=true latency={latency:.1f}ms")
        
        return GenerateResponse(
            response=response,
            latency_ms=latency
        )
        
    except Exception as e:
        logger.error(f"[PERSONALPLEX] Error in generate: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "PersonalPlex 7B Server",
        "status": "running",
        "model": MODEL_NAME,
        "version": "1.0.0"
    }

# Main
if __name__ == "__main__":
    logger.info("[PERSONALPLEX] Starting PersonalPlex 7B Server...")
    
    # Carica modello
    if not load_model():
        logger.error("[PERSONALPLEX] Failed to load model - exiting")
        sys.exit(1)
    
    logger.info("[PERSONALPLEX] Model loaded successfully")
    logger.info("[PERSONALPLEX] Starting HTTP server on :8001")
    
    # Avvia server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        log_level="info",
        access_log=True
    )
