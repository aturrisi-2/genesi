from fastapi import APIRouter, HTTPException, UploadFile, File, status
import os
import uuid
import logging
from core.file_analyzer import analyze_file
from core.decision_engine import decide_response_strategy
from core.response_router import route_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload")

UPLOAD_DIR = "/tmp/genesi_uploads"

@router.post("/")
async def upload_file(file: UploadFile = File(...), user_id: str = ""):
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="File required")
    
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    
    file_id = str(uuid.uuid4())
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{file.filename}")
    
    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        
        # Analisi file
        analysis = analyze_file(file_path, file.filename, file.content_type or "")
        
        # Decisione strategia
        decision = decide_response_strategy(analysis)
        
        # Generazione risposta
        response_text = await route_response(analysis, file_path, {"user_id": user_id})
        
        return {
            "file_id": file_id,
            "filename": file.filename,
            "content_type": file.content_type or "application/octet-stream",
            "analysis": analysis,
            "decision": decision,
            "response": response_text
        }
    
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")
