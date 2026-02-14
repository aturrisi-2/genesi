"""
UPLOAD API v2 - Genesi Core v2
Upload + analisi automatica file (PDF, immagini, testo).
Smista a file_analyzer per elaborazione.
Salva documento in memoria e aggiorna profilo utente.
"""

import uuid
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from core.file_analyzer import analyze_file
from core.document_memory import save_document
from core.storage import storage
from core.log import log

router = APIRouter(prefix="/upload")


@router.post("/")
async def upload_file(file: UploadFile = File(...), user_id: str = Form("")):
    try:
        result = await analyze_file(file)

        # If user_id provided, persist document and set as active
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

            # Set active_document_id on user profile
            try:
                profile = await storage.load(f"profile:{user_id}", default={})
                profile["active_document_id"] = doc_id
                await storage.save(f"profile:{user_id}", profile)
                log("ACTIVE_DOCUMENT_SET", user_id=user_id, doc_id=doc_id)
            except Exception as profile_err:
                log("ACTIVE_DOCUMENT_SET_ERROR", user_id=user_id, error=str(profile_err))

        # Build response for frontend
        filename = result.get("meta", {}).get("filename", file.filename or "file")
        file_type = result.get("type", "unknown")
        content_preview = (result.get("content", "") or "")[:300]

        if file_type == "image":
            response_text = f"Ho analizzato l'immagine '{filename}'. {content_preview}"
        elif file_type == "pdf":
            pages = result.get("meta", {}).get("pages", "?")
            response_text = f"Ho letto il PDF '{filename}' ({pages} pagine). Puoi chiedermi qualsiasi cosa su di esso."
        else:
            lines = result.get("meta", {}).get("lines", "?")
            response_text = f"Ho letto il file '{filename}' ({lines} righe). Puoi chiedermi qualsiasi cosa su di esso."

        return {
            "type": result.get("type"),
            "content": result.get("content"),
            "meta": result.get("meta"),
            "doc_id": doc_id,
            "response": response_text,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
