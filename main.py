"""
MAIN ENTRY POINT - Genesi Core v2
Architettura: Chat libera (Qwen) vs Tecnica (GPT) con Proactor
1 intent → 1 funzione con orchestratore centrale
"""

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import uvicorn

# Import base
from api.user import router as user_router
from api.chat import router as chat_router
from api.memory import router as memory_router
from api.proactor_api import router as proactor_router
from core.log import log

# ===============================
# Applicazione FastAPI
# ===============================

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Genesi Core v2 - Proactor Architecture")

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_index():
    return FileResponse(BASE_DIR / "static" / "index.html")

# API routes
app.include_router(user_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(memory_router, prefix="/api")
app.include_router(proactor_router, prefix="/api")

# ===============================
# Health check
# ===============================

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "v2", "architecture": "proactor", "storage": "in-memory"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
