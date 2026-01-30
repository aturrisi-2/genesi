from fastapi import APIRouter, HTTPException, UploadFile, File, Form, status, Request
import os
import uuid
import logging
from pathlib import Path
from core.file_analyzer import analyze_file
from core.decision_engine import decide_response_strategy
from core.response_router import route_response

# ===============================
# DOCUMENT CONTEXT TEMPORANEO PER USER
# ===============================
last_document_context = {}  # {user_id: {"content": text, "timestamp": time}}

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload")

UPLOAD_DIR = "/tmp/genesi_uploads"

@router.post("/")
async def upload_file(file: UploadFile = File(...), user_id: str = Form(...), http_request: Request = None):
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="File required")
    
    # ===============================
    # LOG DIAGNOSTICO USER_ID RICEVUTO
    # ===============================
    logger.info(f"[UPLOAD] received user_id={user_id}")
    
    # ===============================
    # VALIDAZIONE USER_ID OBBLIGATORIA
    # ===============================
    if not user_id:
        logger.warning(f"[UPLOAD] missing user_id - document_context will not be saved")
        raise HTTPException(status_code=400, detail="user_id required for document context")
    
    logger.info(f"[UPLOAD] processing file for user_id={user_id}")
    
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
                
                logger.info(f"[UPLOAD][OCR] image_detected")
                ocr_text = extract_text_with_ocr(file_path)
                text_length = len(ocr_text.strip())
                
                logger.info(f"[UPLOAD][OCR] text_length={text_length}")
                
                # FASE 1: ANALISI CONTENUTO E DETERMINAZIONE MODALITÀ
                # Valuta qualità e affidabilità dell'estrazione
                ocr_reliability = "high" if text_length >= 100 else "medium" if text_length >= 50 else "low"
                has_clear_text = text_length >= 20 and any(char.isalpha() for char in ocr_text.strip())
                
                # Determina document_mode in base al contenuto
                if has_clear_text and text_length >= 50:
                    document_mode = "mixed"  # Immagine con testo significativo
                    content_description = f"Immagine mista: contenuto visivo con testo OCR (affidabilità: {ocr_reliability}). Testo estratto: {len(ocr_text.strip())} caratteri."
                    extracted_content = ocr_text.strip()
                elif has_clear_text:
                    document_mode = "text"   # Immagine prevalentemente testuale
                    content_description = f"Immagine testuale: principalmente testo OCR (affidabilità: {ocr_reliability}). Testo estratto: {len(ocr_text.strip())} caratteri."
                    extracted_content = ocr_text.strip()
                else:
                    document_mode = "image"  # Immagine pura o con testo non affidabile
                    content_description = f"Immagine pura: contenuto prevalentemente visivo. OCR non affidabile (affidabilità: {ocr_reliability})."
                    extracted_content = ""  # Non usare OCR non affidabile
                
                # Crea document context completo con modalità e affidabilità
                document_context = {
                    "content": extracted_content,
                    "description": content_description,
                    "file_type": "image",
                    "document_mode": document_mode,
                    "source": "image_ocr",
                    "ocr_reliability": ocr_reliability,
                    "has_clear_text": has_clear_text,
                    "filename": file.filename,
                    "timestamp": str(uuid.uuid4())
                }
                
                # Imposta active_document per il chat context
                if http_request:
                    http_request.state.active_document = {
                        "user_id": user_id,
                        "content": extracted_content,
                        "description": content_description,
                        "file_type": "image",
                        "document_mode": document_mode,
                        "source": "image_ocr",
                        "ocr_reliability": ocr_reliability,
                        "has_clear_text": has_clear_text,
                        "timestamp": str(uuid.uuid4())
                    }
                
                logger.info(f"[UPLOAD][OCR] processed | mode={document_mode} | reliability={ocr_reliability} | has_text={has_clear_text}")
                
                # Salva document context per user_id SOLO se user_id valido
                if user_id:
                    last_document_context[user_id] = document_context
                    logger.info(f"[UPLOAD] document_context_saved | user_id={user_id} | mode={document_mode} | reliability={ocr_reliability}")
                else:
                    logger.warning(f"[UPLOAD] cannot save document_context - missing user_id")
                
                # Aggiorna analysis per riflettere il testo trovato
                analysis["has_text"] = has_clear_text
                analysis["text"] = extracted_content
                analysis["ocr_used"] = True
                analysis["document_mode"] = document_mode
                analysis["ocr_reliability"] = ocr_reliability
                    
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
        
        # Aggiungi anche il context persistente per user_id
        if user_id in last_document_context:
            result["persistent_context"] = last_document_context[user_id]
        
        return result
    
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")
