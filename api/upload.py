"""
UPLOAD API v2 - Genesi Core v2
Upload + analisi automatica file (PDF, immagini, testo).
Smista a file_analyzer per elaborazione.
Salva documento in memoria e aggiorna profilo utente.

SICUREZZA: user_id estratto SOLO dal JWT. Mai dal client.
"""

import uuid
import os
import asyncio
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Request, Depends
from core.file_analyzer import analyze_file
from core.document_memory import save_document
from core.storage import storage
from core.log import log
from auth.router import require_auth
from auth.models import AuthUser

router = APIRouter(prefix="/upload")

# Upload validation constants
UPLOAD_MAX_SIZE_MB = 20
UPLOAD_ALLOWED_EXTENSIONS = {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.txt', '.md'}

def _validate_upload(filename: str, file_size_bytes: int) -> tuple[bool, str]:
    """Valida dimensione e estensione file."""
    size_mb = file_size_bytes / (1024 * 1024)
    if size_mb > UPLOAD_MAX_SIZE_MB:
        return False, f"File troppo grande: {size_mb:.1f}MB (max {UPLOAD_MAX_SIZE_MB}MB)"
    ext = os.path.splitext(filename.lower())[1]
    if ext not in UPLOAD_ALLOWED_EXTENSIONS:
        return False, f"Formato non supportato: {ext}"
    return True, ""

async def _ocr_with_retry(file_path: str, max_retries: int = 3) -> str:
    """OCR con retry automatico per migliorare affidabilità."""
    from core.ocr_service import extract_text_from_image
    
    for attempt in range(max_retries):
        try:
            result = await extract_text_from_image(file_path)
            if result and len(result.strip()) > 0:
                log("OCR_SUCCESS", attempt=attempt+1, chars=len(result))
                return result
            log("OCR_EMPTY", attempt=attempt+1)
        except Exception as e:
            log("OCR_ERROR", attempt=attempt+1, error=str(e))
            if attempt < max_retries - 1:
                await asyncio.sleep(1)
    log("OCR_FAILED", reason="all_attempts_exhausted")
    return ""


@router.post("/")
async def upload_file(file: UploadFile = File(...), user: AuthUser = Depends(require_auth)):
    try:
        # STEP 1: Validazione upload prima di qualsiasi elaborazione
        if not file.filename:
            raise HTTPException(status_code=400, detail="Nessun file selezionato")
        
        # Validazione dimensione e estensione
        is_valid, error_msg = _validate_upload(file.filename, file.size or 0)
        if not is_valid:
            raise HTTPException(status_code=400, detail=error_msg)
        
        log("UPLOAD_VALIDATED", filename=file.filename, size_mb=round((file.size or 0)/(1024*1024), 1))
        
        user_id = user.id
        result = await analyze_file(file)

        # Always persist document for authenticated user
        doc_id = None
        if user_id:
            doc_id = f"{user_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"
            await save_document(
                doc_id=doc_id,
                user_id=user_id,
                filename=result.get("meta", {}).get("filename", file.filename or "unknown"),
                file_type=result.get("type", "unknown"),
                content=result.get("content", ""),
                meta=result.get("meta", {}),
            )
            
            # STEP 2: Register in Document Context Manager (NotebookLM behavior)
            try:
                from core.document_context_manager import get_document_context_manager
                doc_manager = get_document_context_manager()
                file_ext = os.path.splitext(file.filename.lower())[1] if file.filename else "unknown"
                doc_manager.add_document(
                    user_id=user_id, 
                    filename=result.get("meta", {}).get("filename", file.filename or "unknown"), 
                    content=result.get("content", ""), 
                    file_type=result.get("type", "unknown")
                )
                log("DOCUMENT_CONTEXT_REGISTERED", user_id=user_id, filename=file.filename)
            except Exception as doc_err:
                log("DOCUMENT_CONTEXT_REGISTER_ERROR", user_id=user_id, error=str(doc_err))

            # Add to active_documents list on user profile (max 5)
            try:
                profile = await storage.load(f"profile:{user_id}", default={})
                active_docs = profile.get("active_documents", [])
                # Migrate from old active_document_id if present
                old_id = profile.pop("active_document_id", None)
                if old_id and old_id not in active_docs:
                    active_docs.append(old_id)
                # Add new doc
                if doc_id not in active_docs:
                    active_docs.append(doc_id)
                # Enforce max 5 — remove oldest
                while len(active_docs) > 5:
                    active_docs.pop(0)
                profile["active_documents"] = active_docs
                await storage.save(f"profile:{user_id}", profile)
                log("ACTIVE_DOCUMENTS_UPDATED", user_id=user_id, doc_id=doc_id, count=len(active_docs))
            except Exception as profile_err:
                log("ACTIVE_DOCUMENTS_UPDATE_ERROR", user_id=user_id, error=str(profile_err))

        # Build response for frontend
        filename = result.get("meta", {}).get("filename", file.filename or "file")
        file_type = result.get("type", "unknown")
        if file_type == "image":
            # Per le immagini, l'utente vuole la descrizione completa
            response_text = f"Ho analizzato l'immagine '{filename}'. {result.get('content', '')}"
        elif file_type == "pdf":
            pages = result.get("meta", {}).get("pages", "?")
            response_text = f"Ho letto il PDF '{filename}' ({pages} pagine). Puoi chiedermi qualsiasi cosa su di esso."
        else:
            lines = result.get("meta", {}).get("lines", "?")
            response_text = f"Ho letto il file '{filename}' ({lines} righe). Puoi chiedermi qualsiasi cosa su di esso."

        # List active documents for frontend
        active_docs_info = []
        if user_id:
            profile = await storage.load(f"profile:{user_id}", default={})
            for did in profile.get("active_documents", []):
                from core.document_memory import load_document
                d = load_document(did)
                if d:
                    active_docs_info.append({"doc_id": did, "filename": d.get("filename", "?"), "type": d.get("type", "?")})

        if len(active_docs_info) >= 2:
            names = [d["filename"] for d in active_docs_info[-2:]]
            response_text += f"\n\nPuoi chiedere: confronta '{names[0]}' e '{names[1]}'"

        return {
            "type": result.get("type"),
            "content": result.get("content"),
            "meta": result.get("meta"),
            "doc_id": doc_id,
            "active_documents": active_docs_info,
            "response": response_text,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
