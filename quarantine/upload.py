from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import FileResponse
import os
import re
import uuid
import logging
from pathlib import Path
from core.file_analyzer import analyze_file, MAX_FILE_SIZE
from core.decision_engine import decide_response_strategy
from core.response_router import route_response
from core.text_post_processor import text_post_processor

# ===============================
# DOCUMENT CONTEXT TEMPORANEO PER USER
# ===============================
last_document_context = {}

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/upload")

UPLOAD_DIR = "/tmp/genesi_uploads"

def _sanitize_filename(name: str) -> str:
    """Rimuove caratteri pericolosi dal filename."""
    name = Path(name).name  # solo il nome, no path traversal
    name = re.sub(r"[^\w.\-]", "_", name)
    return name[:200]  # max 200 chars


# ===============================
# SERVE FILE PER PREVIEW
# ===============================
@router.get("/file/{file_id}/{filename}")
async def serve_uploaded_file(file_id: str, filename: str):
    """Serve file caricati per preview nel frontend."""
    safe_name = _sanitize_filename(filename)
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{safe_name}")
    if not os.path.exists(file_path):
        # Prova con il filename originale
        for f in os.listdir(UPLOAD_DIR):
            if f.startswith(file_id):
                file_path = os.path.join(UPLOAD_DIR, f)
                break
        else:
            raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path)


# ===============================
# UPLOAD PRINCIPALE
# ===============================
@router.post("/")
async def upload_file(file: UploadFile = File(...), user_id: str = Form(...), http_request: Request = None):
    if not file or not file.filename:
        raise HTTPException(status_code=400, detail="File required")

    if not user_id:
        raise HTTPException(status_code=400, detail="user_id required")

    logger.info(f"[UPLOAD] file={file.filename} user={user_id} ct={file.content_type}")

    os.makedirs(UPLOAD_DIR, exist_ok=True)

    file_id = str(uuid.uuid4())
    safe_filename = _sanitize_filename(file.filename)
    file_path = os.path.join(UPLOAD_DIR, f"{file_id}_{safe_filename}")

    try:
        content = await file.read()

        # Sicurezza: limite dimensione
        if len(content) > MAX_FILE_SIZE:
            raise HTTPException(status_code=413, detail=f"File troppo grande. Limite: 20MB.")

        with open(file_path, "wb") as f:
            f.write(content)

        # Analisi file
        analysis = analyze_file(file_path, file.filename, file.content_type or "")
        kind = analysis.get("kind", "binary")

        # File rifiutato (troppo grande)
        if kind == "rejected":
            return {
                "file_id": file_id,
                "filename": file.filename,
                "analysis": analysis,
                "response": analysis.get("error", "File non processabile.")
            }

        # ===============================
        # PREVIEW URL
        # ===============================
        preview_url = None
        if kind == "image":
            preview_url = f"/upload/file/{file_id}/{safe_filename}"
        elif kind == "document" and analysis.get("subtype") == "pdf":
            preview_url = f"/upload/file/{file_id}/{safe_filename}"

        # ===============================
        # ROUTING PER TIPO
        # ===============================
        response_text = ""
        document_context = None

        if kind == "image":
            # IMMAGINI: GPT-4o Vision + OCR fallback
            from core.image_handler import handle_image

            ocr_text = analysis.get("text", "")
            has_text = analysis.get("has_text", False)

            document_context = {
                "content": ocr_text,
                "has_clear_text": has_text,
                "filename": file.filename,
                "file_type": "image",
                "document_mode": "image",
                "ocr_reliability": "low" if has_text else "none",
                "source": "image_ocr" if analysis.get("ocr_used") else "upload",
            }

            response_text = await handle_image(
                image_context=document_context,
                user_message="Analizza questa immagine in dettaglio.",
                user_id=user_id,
                file_path=file_path
            )

        elif kind == "document" and analysis.get("subtype") == "pdf":
            # PDF: testuale o scansionato
            if analysis.get("has_text"):
                # PDF testuale → analisi contenuto
                response_text = await route_response(analysis, file_path, {"user_id": user_id})
            else:
                # PDF scansionato → OCR già tentato in analyze_file
                if analysis.get("ocr_used") and analysis.get("text"):
                    response_text = await route_response(analysis, file_path, {"user_id": user_id})
                else:
                    response_text = f"Il PDF '{file.filename}' sembra essere una scansione. Non sono riuscito a estrarre testo leggibile. Prova a caricare una versione con testo selezionabile."

        elif kind == "text":
            # Testo/codice
            response_text = await route_response(analysis, file_path, {"user_id": user_id})

        elif kind in ["audio", "video", "archive", "binary"]:
            # File non analizzabili direttamente
            desc = analysis.get("description", "")
            if desc:
                response_text = desc
            else:
                size_bytes = analysis.get("size_bytes", 0)
                size_str = f"{size_bytes / 1024:.0f}KB" if size_bytes < 1024 * 1024 else f"{size_bytes / (1024*1024):.1f}MB"
                response_text = f"Ho ricevuto '{file.filename}' ({analysis.get('mime', 'sconosciuto')}, {size_str}). Questo tipo di file non è analizzabile direttamente, ma è stato caricato correttamente."

        else:
            # Fallback: prova route_response
            try:
                response_text = await route_response(analysis, file_path, {"user_id": user_id})
            except Exception:
                response_text = f"Ho ricevuto '{file.filename}'. Il file è stato caricato correttamente."

        # POST-PROCESSOR LINGUISTICO - Pulisci anche risposte upload
        if response_text:
            original_text = response_text
            # ❌ BYPASS TOTALE per chat_free - nessuna formattazione Q/A
            # Note: upload non ha intent_type, ma se è chat_free bypassiamo
            if "chat_free" not in str(response_text).lower():  # Detection semplice
                response_text = text_post_processor.clean_response(response_text)
            else:
                # chat_free: testo nudo, nessun post-processing
                pass
            if original_text != response_text:
                logger.info(f"[UPLOAD] TEXT_POST_PROCESSOR: {len(original_text)}→{len(response_text)} chars")

        # Salva document context
        if document_context and user_id:
            last_document_context[user_id] = document_context

        result = {
            "file_id": file_id,
            "filename": file.filename,
            "content_type": file.content_type or "application/octet-stream",
            "analysis": analysis,
            "response": response_text or "File ricevuto."
        }

        if preview_url:
            result["preview_url"] = preview_url

        if document_context:
            result["document_context"] = document_context

        logger.info(f"[UPLOAD] done: {file.filename} kind={kind} preview={'yes' if preview_url else 'no'}")
        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[UPLOAD] error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Upload failed")
