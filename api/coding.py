"""
Coding Mode API Endpoint
Isolated endpoint for AI Engineer OS shadow integration.
No auth dependency injection - uses direct request processing.
"""

import asyncio
import logging
from fastapi import APIRouter
from fastapi import HTTPException
from fastapi import Request
from pydantic import BaseModel
from typing import Optional
import time
import uuid
import os
import json
from pathlib import Path

from core.proactor import proactor
from genesi.ai_engineer_os.shadow_orchestrator import ShadowOrchestrator
from genesi.ai_engineer_os.feature_flags import ai_engineer_os_flags
from genesi.ai_engineer_os.feature_flags import FeatureFlag
from genesi.ai_engineer_os.web_search import should_search, build_search_query, search_web, search_github, build_github_query

logger = logging.getLogger(__name__)


def _write_log_sync(log_file: Path, log_entry: dict) -> None:
    """Sync log write — chiamata via executor per non bloccare event loop."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, 'a', encoding='utf-8') as f:
        f.write(json.dumps(log_entry) + '\n')


# Pydantic models
class CodingRequest(BaseModel):
    message: str
    user_id: Optional[str] = None


class CodingResponse(BaseModel):
    response: str
    observation_id: Optional[str] = None
    processing_time: Optional[float] = None


# Create router
coding_router = APIRouter(prefix="/coding", tags=["coding"])


@coding_router.post("/", response_model=CodingResponse)
async def coding_endpoint(request: Request, body: CodingRequest):
    """
    Coding Mode endpoint with AI Engineer OS shadow integration.
    
    This endpoint activates the AI Engineer OS shadow orchestrator
    only for coding mode requests, leaving normal chat unaffected.
    
    No auth dependency injection - processes request directly.
    """
    start_time = time.time()
    observation_id = str(uuid.uuid4())
    
    try:
        # Extract user_id from request body or default
        user_id = body.user_id or "coding_user"
        
        # Extract message from request body
        message = body.message
        if not message:
            raise HTTPException(status_code=400, detail="Message is required")
        
        # Log observation start
        await _log_observation_start(observation_id, message, user_id)
        
        # Activate AI Engineer OS shadow orchestrator for this request
        if ai_engineer_os_flags.is_enabled(FeatureFlag.AI_ENGINEER_OS_ENABLED):
            # Create shadow orchestrator instance per request
            shadow_orchestrator = ShadowOrchestrator()
            await shadow_orchestrator.start()
            
            try:
                # Call proactor.handle() through shadow orchestrator
                result = await _call_proactor_with_shadow(
                    shadow_orchestrator, 
                    message, 
                    user_id,
                    observation_id
                )
            finally:
                # Ensure shutdown
                await shadow_orchestrator.stop()
        else:
            # Direct call if AI Engineer OS is disabled
            result = await proactor.handle(user_id, message, skip_document_mode=True)
        
        processing_time = time.time() - start_time
        
        # Log observation completion
        await _log_observation_complete(observation_id, result, processing_time)
        
        return CodingResponse(
            response=result,
            observation_id=observation_id,
            processing_time=processing_time
        )
        
    except Exception as e:
        processing_time = time.time() - start_time
        await _log_observation_error(observation_id, str(e), processing_time)
        
        raise HTTPException(
            status_code=500,
            detail=f"Coding mode error: {str(e)}"
        )


async def _call_proactor_with_shadow(
    shadow_orchestrator: ShadowOrchestrator,
    message: str,
    user_id: str,
    observation_id: str
) -> str:
    """
    Chiama il proactor con contesto web search iniettato se rilevante.
    La ricerca è invisibile all'utente — solo nel contesto LLM.
    """
    system_prompt = (
        "Sei un assistente tecnico senior specializzato in debugging e sviluppo software.\n"
        "Quando ricevi un problema:\n"
        "- Fai domande mirate per capire il contesto se mancano informazioni\n"
        "- Proponi sempre 2-3 soluzioni alternative con pro/contro\n"
        "- Fornisci codice completo, pronto da incollare, correttamente indentato\n"
        "- Indica esattamente DOVE incollare il codice (file, riga, funzione)\n"
        "- Se hai bisogno di vedere un file o un log, chiedilo esplicitamente\n"
        "- Usa markdown per formattare codice con syntax highlighting\n"
        "- Sii conciso nell'analisi, preciso nel codice\n\n"
        "RISPONDI IN MODO NATURALE. Puoi ispirarti a questa traccia:\n"
        "- Analisi iniziale del problema (breve)\n"
        "- Codice pronto all'uso (in blocchi ```language)\n"
        "- Istruzioni chiare su dove/come applicarlo\n"
        "Non inserire mai rigide intestazioni come 'Prima:', 'Poi:' o 'Infine:'."
    )

    enriched_message = f"{system_prompt}\n\nRichiesta utente:\n{message}"
    web_context = None
    github_context = None

    # Cerca solo se il messaggio lo richiede
    if should_search(message):
        query = build_search_query(message)
        github_query = build_github_query(message)  # query breve in inglese
        web_context = await search_web(query)
        
        import asyncio
        loop = asyncio.get_event_loop()
        github_context = await loop.run_in_executor(None, lambda: search_github(github_query))
        
        combined_contexts = []
        if web_context:
            combined_contexts.append(web_context)
        if github_context:
            combined_contexts.append(github_context)
            
        if combined_contexts:
            ctx_str = "\n\n".join(combined_contexts)
            enriched_message += f"\n\nContesto web trovato:\n{ctx_str}"
            
            # Logga che la ricerca è avvenuta
            await _log_web_search(observation_id, query, True)

    result = await proactor.handle(user_id, enriched_message, skip_document_mode=True)

    # Shadow processing in background
    await shadow_orchestrator.submit_background_task(
        _process_shadow_observation(observation_id, message, user_id, result)
    )

    return result


async def _process_shadow_observation(
    observation_id: str,
    message: str,
    user_id: str,
    result: str
) -> None:
    """
    Background task for shadow observation processing.
    
    This runs asynchronously without affecting the response.
    """
    try:
        # Log shadow processing
        await _log_shadow_processing(observation_id, message, user_id, result)
        
        # Additional shadow processing can be added here
        # For now, we just log the observation
        
    except Exception as e:
        # Shadow processing errors should not affect the main flow
        await _log_shadow_error(observation_id, str(e))


async def _log_observation_start(observation_id: str, message: str, user_id: str) -> None:
    """Log observation start to AI Engineer OS logs."""
    try:
        logs_dir = Path("genesi/ai_engineer_os/logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        
        log_entry = {
            "timestamp": time.time(),
            "observation_id": observation_id,
            "event": "coding_observation_start",
            "message": message[:200],  # Truncate for log size
            "user_id": user_id,
            "endpoint": "/coding"
        }
        
        log_file = logs_dir / f"coding_observations_{time.strftime('%Y-%m-%d')}.json"
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _write_log_sync(log_file, log_entry))
            
    except Exception:
        pass  # Silently fail to avoid affecting main flow


async def _log_observation_complete(observation_id: str, result: str, processing_time: float) -> None:
    """Log observation completion."""
    try:
        logs_dir = Path("genesi/ai_engineer_os/logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        
        log_entry = {
            "timestamp": time.time(),
            "observation_id": observation_id,
            "event": "coding_observation_complete",
            "result_length": len(result),
            "processing_time": processing_time,
            "endpoint": "/coding"
        }
        
        log_file = logs_dir / f"coding_observations_{time.strftime('%Y-%m-%d')}.json"
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _write_log_sync(log_file, log_entry))
            
    except Exception:
        pass


async def _log_observation_error(observation_id: str, error: str, processing_time: float) -> None:
    """Log observation error."""
    try:
        logs_dir = Path("genesi/ai_engineer_os/logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        
        log_entry = {
            "timestamp": time.time(),
            "observation_id": observation_id,
            "event": "coding_observation_error",
            "error": error,
            "processing_time": processing_time,
            "endpoint": "/coding"
        }
        
        log_file = logs_dir / f"coding_observations_{time.strftime('%Y-%m-%d')}.json"
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _write_log_sync(log_file, log_entry))
            
    except Exception:
        pass


async def _log_shadow_processing(observation_id: str, message: str, user_id: str, result: str) -> None:
    """Log shadow processing."""
    try:
        logs_dir = Path("genesi/ai_engineer_os/logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        
        log_entry = {
            "timestamp": time.time(),
            "observation_id": observation_id,
            "event": "shadow_processing",
            "message": message[:100],
            "user_id": user_id,
            "result_length": len(result),
            "endpoint": "/coding"
        }
        
        log_file = logs_dir / f"shadow_processing_{time.strftime('%Y-%m-%d')}.json"
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _write_log_sync(log_file, log_entry))
            
    except Exception:
        pass


async def _log_web_search(observation_id: str, query: str, success: bool) -> None:
    """Log web search event."""
    try:
        logs_dir = Path("genesi/ai_engineer_os/logs")
        log_entry = {
            "timestamp": time.time(),
            "observation_id": observation_id,
            "event": "web_search",
            "query": query,
            "success": success,
            "endpoint": "/coding"
        }
        log_file = logs_dir / f"coding_observations_{time.strftime('%Y-%m-%d')}.json"
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _write_log_sync(log_file, log_entry))
    except Exception:
        pass


async def _log_shadow_error(observation_id: str, error: str) -> None:
    """Log shadow processing error."""
    try:
        logs_dir = Path("genesi/ai_engineer_os/logs")
        logs_dir.mkdir(parents=True, exist_ok=True)
        
        log_entry = {
            "timestamp": time.time(),
            "observation_id": observation_id,
            "event": "shadow_processing_error",
            "error": error,
            "endpoint": "/coding"
        }
        
        log_file = logs_dir / f"shadow_errors_{time.strftime('%Y-%m-%d')}.json"
        
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: _write_log_sync(log_file, log_entry))
            
    except Exception:
        pass
