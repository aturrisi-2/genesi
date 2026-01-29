from fastapi import APIRouter, HTTPException, UploadFile, File, status, Request
import os
import uuid
import logging
from pathlib import Path
from core.file_analyzer import analyze_file
from core.decision_engine import decide_response_strategy
from core.response_router import route_response

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload")

UPLOAD_DIR = "/tmp/genesi_uploads"

@router.post("/")
async def upload_file(file: UploadFile = File(...), user_id: str = "", http_request: Request = None):
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
        
        # ===============================
        # GESTIONE IMMAGINI CON OCR
        # ===============================
        document_context = None
        file_ext = Path(file.filename).suffix.lower()
        
        if file_ext in ['.jpg', '.jpeg', '.png'] and analysis.get("kind") == "image":
            try:
                from core.ocr.ocr_engine import extract_text_with_ocr
                
                logger.info(f"OCR applied to image {file.filename}")
                ocr_text = extract_text_with_ocr(file_path)
                text_length = len(ocr_text.strip())
                
                logger.info(f"OCR text length = {text_length}")
                
                # Soglia minima per considerare testo rilevante
                if text_length >= 30:
                    document_context = {
                        "content": ocr_text.strip(),
                        "source": "image_ocr",
                        "filename": file.filename,
                        "timestamp": str(uuid.uuid4())
                    }
                    
                    # Imposta active_document per il chat context
                    if http_request:
                        http_request.state.active_document = {
                            "user_id": user_id,
                            "content": ocr_text.strip(),
                            "source": "image_ocr",
                            "timestamp": str(uuid.uuid4())
                        }
                    
                    logger.info(f"OCR accepted as document_context")
                    
                    # Aggiorna analysis per riflettere il testo trovato
                    analysis["has_text"] = True
                    analysis["text"] = ocr_text.strip()
                    analysis["ocr_used"] = True
                else:
                    logger.info(f"OCR text too short, ignoring")
                    
            except Exception as e:
                logger.error(f"OCR processing failed for {file.filename}: {e}")
        
        # Decisione strategia
        decision = decide_response_strategy(analysis)
        
        # Generazione risposta
        response_text = await route_response(analysis, file_path, {"user_id": user_id})
        
        result = {
            "file_id": file_id,
            "filename": file.filename,
            "content_type": file.content_type or "application/octet-stream",
            "analysis": analysis,
            "decision": decision,
            "response": response_text
        }
        
        # Aggiungi document context se presente
        if document_context:
            result["document_context"] = document_context
        
        return result
    
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")
