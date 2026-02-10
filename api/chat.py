"""
CHAT API - Genesi Core v2
1 intent → 1 funzione
Nessun orchestrazione, nessun fallback, nessun post-processing
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Optional
from core.simple_chat import simple_chat_handler
from core.log import log

router = APIRouter(prefix="/api")

class ChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = None

class ChatResponse(BaseModel):
    response: str
    status: str
    intent: Optional[str] = None

@router.post("/chat", response_model=ChatResponse)
async def chat_endpoint(request: ChatRequest):
    """
    Chat endpoint - 1 intent → 1 funzione
    
    Args:
        request: Chat request con messaggio
        
    Returns:
        Risposta diretta senza orchestrazione
    """
    try:
        # Log request
        log("API_CHAT", message=request.message[:100])
        
        # 1 intent → 1 funzione
        response = await simple_chat_handler(request.message)
        
        return ChatResponse(
            response=response,
            status="ok"
        )
        
    except Exception as e:
        log("API_CHAT_ERROR", error=str(e))
        raise HTTPException(status_code=500, detail="Chat error")

@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "version": "v2"}
