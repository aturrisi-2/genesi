#!/bin/bash
# SETUP PERSONALPLEX 7B SU VPS UBUNTU
# Installazione llama.cpp + modello GGUF + server HTTP

set -e

echo "🎯 SETUP PERSONALPLEX 7B VPS UBUNTU"
echo "=================================="

# FASE 1: INSTALLAZIONE DIPENDENZE
echo "📦 FASE 1: Installazione dipendenze..."

sudo apt update
sudo apt install -y build-essential wget git python3 python3-pip

# Installazione Python per llama.cpp
pip3 install --upgrade pip
pip3 install numpy

# FASE 2: COMPILAZIONE LLAMA.CPP
echo "🔨 FASE 2: Compilazione llama.cpp..."

if [ ! -d "llama.cpp" ]; then
    git clone https://github.com/ggerganov/llama.cpp.git
fi

cd llama.cpp

# Compilazione ottimizzata CPU
make clean
LLAMA_METAL=0 make -j$(nproc)

echo "✅ llama.cpp compilato"

# FASE 3: DOWNLOAD MODELLO GGUF 7B
echo "📥 FASE 3: Download modello GGUF 7B..."

MODEL_DIR="../models"
mkdir -p "$MODEL_DIR"

# Scarica Mistral 7B Instruct GGUF (versione Q4_K_M per buon equilibrio qualità/dimensione)
MODEL_URL="https://huggingface.co/TheBloke/Mistral-7B-Instruct-v0.2-GGUF/resolve/main/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
MODEL_FILE="$MODEL_DIR/mistral-7b-instruct-v0.2.Q4_K_M.gguf"

if [ ! -f "$MODEL_FILE" ]; then
    echo "⬇️ Download modello Mistral 7B Instruct GGUF..."
    wget -O "$MODEL_FILE" "$MODEL_URL"
else
    echo "✅ Modello già presente"
fi

echo "✅ Modello scaricato: $(du -h "$MODEL_FILE" | cut -f1)"

cd ..

# FASE 4: CREAZIONE SERVER PERSONALPLEX
echo "🌐 FASE 4: Creazione server PersonalPlex..."

cat > personalplex_server.py << 'EOF'
#!/usr/bin/env python3
"""
PersonalPlex 7B Server - Wrapper FastAPI per llama.cpp
Servizio HTTP per modello locale GGUF su VPS Ubuntu
"""

import os
import sys
import json
import time
import subprocess
import logging
import requests
from typing import Dict, Any, Optional
from datetime import datetime

# FastAPI
try:
    from fastapi import FastAPI, HTTPException
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import uvicorn
except ImportError:
    print("ERRORE: Installare FastAPI: pip3 install fastapi uvicorn pydantic")
    sys.exit(1)

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Modelli Pydantic
class AnalyzeRequest(BaseModel):
    text: str

class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 200
    temperature: float = 0.7

class HealthResponse(BaseModel):
    status: str
    model: str
    backend: str

class AnalyzeResponse(BaseModel):
    intent: str
    confidence: float
    response: str
    latency_ms: float

class GenerateResponse(BaseModel):
    response: str
    latency_ms: float

# App FastAPI
app = FastAPI(title="PersonalPlex 7B Server", version="1.0.0")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configurazione llama.cpp
LLAMA_CPP_PATH = "./llama.cpp/main"
MODEL_PATH = "./models/mistral-7b-instruct-v0.2.Q4_K_M.gguf"
LLAMA_SERVER_HOST = "127.0.0.1"
LLAMA_SERVER_PORT = 8080  # Porta interna per llama.cpp

# Processo llama.cpp
llama_process = None

def start_llama_server():
    """Avvia server llama.cpp in background"""
    global llama_process
    
    if not os.path.exists(LLAMA_CPP_PATH):
        logger.error(f"[PERSONALPLEX] llama.cpp non trovato: {LLAMA_CPP_PATH}")
        return False
    
    if not os.path.exists(MODEL_PATH):
        logger.error(f"[PERSONALPLEX] Modello non trovato: {MODEL_PATH}")
        return False
    
    cmd = [
        LLAMA_CPP_PATH,
        "--model", MODEL_PATH,
        "--host", LLAMA_SERVER_HOST,
        "--port", str(LLAMA_SERVER_PORT),
        "--ctx-size", "2048",
        "--n-gpu-layers", "0",  # CPU only
        "--threads", "4",
        "--temp", "0.7",
        "--repeat-penalty", "1.1"
    ]
    
    logger.info("[PERSONALPLEX] Avvio server llama.cpp...")
    logger.info(f"[PERSONALPLEX] Comando: {' '.join(cmd)}")
    
    try:
        llama_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            universal_newlines=True,
            bufsize=1
        )
        
        # Attendi che il server sia pronto
        time.sleep(5)
        
        # Verifica che il server risponda
        try:
            response = requests.get(f"http://{LLAMA_SERVER_HOST}:{LLAMA_SERVER_PORT}/health", timeout=2)
            if response.status_code == 200:
                logger.info("[PERSONALPLEX] llama.cpp server pronto")
                return True
            else:
                logger.error(f"[PERSONALPLEX] llama.cpp health failed: {response.status_code}")
                return False
        except:
            logger.error("[PERSONALPLEX] llama.cpp server non risponde")
            return False
            
    except Exception as e:
        logger.error(f"[PERSONALPLEX] Errore avvio llama.cpp: {e}")
        return False

def classify_intent(text: str) -> tuple[str, float]:
    """Classificazione intent semplice"""
    text_lower = text.lower().strip()
    
    # Pattern di intent
    intent_patterns = {
        "greeting": ["ciao", "salve", "buongiorno", "buonasera", "hey"],
        "question": ["come", "cosa", "dove", "quando", "perché", "quale"],
        "request": ["puoi", "potresti", "vorrei", "mi dici", "raccontami"],
        "help": ["aiuto", "help", "problema", "difficoltà"],
        "farewell": ["arrivederci", "ciao", "a dopo", "buonanotte"],
        "complaint": ["male", "dolore", "fastidio", "problema", "non funziona"],
        "conversation": []  # default
    }
    
    best_intent = "conversation"
    best_confidence = 0.3
    
    for intent, keywords in intent_patterns.items():
        if not keywords:
            continue
            
        matches = sum(1 for keyword in keywords if keyword in text_lower)
        confidence = matches / len(keywords) if keywords else 0
        
        if confidence > best_confidence:
            best_intent = intent
            best_confidence = confidence
    
    best_confidence = max(0.1, min(0.9, best_confidence + 0.2))
    return best_intent, best_confidence

def call_llama_generate(prompt: str, max_tokens: int = 200, temperature: float = 0.7) -> str:
    """Chiama llama.cpp per generazione"""
    
    try:
        payload = {
            "prompt": prompt,
            "n_predict": max_tokens,
            "temperature": temperature,
            "stop": ["\n", "User:", "Assistant:"]
        }
        
        response = requests.post(
            f"http://{LLAMA_SERVER_HOST}:{LLAMA_SERVER_PORT}/completion",
            json=payload,
            timeout=30
        )
        
        if response.status_code == 200:
            result = response.json()
            content = result.get("content", "").strip()
            return content
        else:
            logger.error(f"[PERSONALPLEX] llama.cpp HTTP error: {response.status_code}")
            return ""
            
    except Exception as e:
        logger.error(f"[PERSONALPLEX] llama.cpp call error: {e}")
        return ""

# API Endpoints
@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check"""
    
    model_status = "loaded" if os.path.exists(MODEL_PATH) else "missing"
    backend_status = "running" if llama_process and llama_process.poll() is None else "stopped"
    
    return HealthResponse(
        status="ok" if backend_status == "running" else "error",
        model="mistral-7b-instruct-v0.2.Q4_K_M.gguf",
        backend=f"llama.cpp ({backend_status})"
    )

@app.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest):
    """Analizza testo e genera risposta"""
    
    start_time = time.time()
    logger.info(f"[PERSONALPLEX] request received text='{request.text[:50]}...'")
    
    try:
        # Classifica intent
        intent, confidence = classify_intent(request.text)
        
        # Genera risposta
        prompt = f"User: {request.text}\nAssistant:"
        response = call_llama_generate(prompt, max_tokens=150, temperature=0.7)
        
        latency = (time.time() - start_time) * 1000
        
        logger.info(f"[PERSONALPLEX] response generated latency={latency:.1f}ms")
        
        return AnalyzeResponse(
            intent=intent,
            confidence=confidence,
            response=response,
            latency_ms=latency
        )
        
    except Exception as e:
        logger.error(f"[PERSONALPLEX] analyze error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest):
    """Genera testo da prompt"""
    
    start_time = time.time()
    logger.info(f"[PERSONALPLEX] generate request prompt='{request.prompt[:50]}...'")
    
    try:
        response = call_llama_generate(
            request.prompt,
            max_tokens=request.max_tokens,
            temperature=request.temperature
        )
        
        latency = (time.time() - start_time) * 1000
        
        logger.info(f"[PERSONALPLEX] generate response latency={latency:.1f}ms")
        
        return GenerateResponse(
            response=response,
            latency_ms=latency
        )
        
    except Exception as e:
        logger.error(f"[PERSONALPLEX] generate error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "PersonalPlex 7B Server",
        "status": "running",
        "model": "mistral-7b-instruct-v0.2.Q4_K_M.gguf",
        "backend": "llama.cpp",
        "version": "1.0.0"
    }

# Main
if __name__ == "__main__":
    logger.info("[PERSONALPLEX] Avvio PersonalPlex 7B Server...")
    
    # Avvia llama.cpp
    if not start_llama_server():
        logger.error("[PERSONALPLEX] Impossibile avviare llama.cpp")
        sys.exit(1)
    
    logger.info("[PERSONALPLEX] llama.cpp server attivo")
    logger.info("[PERSONALPLEX] Avvio FastAPI su :8001")
    
    # Avvia FastAPI
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8001,
        log_level="info"
    )
EOF

chmod +x personalplex_server.py

echo "✅ Server PersonalPlex creato"

# FASE 5: SERVIZIO SYSTEMD
echo "⚙️ FASE 5: Creazione servizio systemd..."

sudo tee /etc/systemd/system/personalplex.service > /dev/null << EOF
[Unit]
Description=PersonalPlex 7B Server
After=network.target

[Service]
Type=simple
User=$(whoami)
WorkingDirectory=$(pwd)
Environment=PATH=$(pwd)/venv/bin:/usr/local/bin:/usr/bin:/bin
ExecStart=$(pwd)/personalplex_server.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable personalplex

echo "✅ Servizio systemd creato"

# FASE 6: TEST CONNESSIONE
echo "🧪 FASE 6: Test connessione..."

# Avvia il servizio
sudo systemctl start personalplex

# Attendi avvio
echo "⏳ Atteso avvio PersonalPlex..."
sleep 10

# Test health
if curl -s http://localhost:8001/health | grep -q "ok"; then
    echo "✅ PersonalPlex 7B attivo e funzionante!"
    echo ""
    echo "🎯 SETUP COMPLETATO!"
    echo "==================="
    echo "Health: curl http://localhost:8001/health"
    echo "Generate: curl -X POST http://localhost:8001/generate -H 'Content-Type: application/json' -d '{\"prompt\":\"ciao\"}'"
    echo "Analyze: curl -X POST http://localhost:8001/analyze -H 'Content-Type: application/json' -d '{\"text\":\"come stai?\"}'"
    echo ""
    echo "Servizio systemd:"
    echo "  Start: sudo systemctl start personalplex"
    echo "  Stop:  sudo systemctl stop personalplex"
    echo "  Status: sudo systemctl status personalplex"
    echo "  Logs:  sudo journalctl -u personalplex -f"
else
    echo "❌ PersonalPlex non risponde - controllare log:"
    sudo journalctl -u personalplex --no-pager -n 20
fi

echo ""
echo "🎯 SETUP PERSONALPLEX 7B VPS COMPLETATO!"
