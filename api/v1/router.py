"""
GENESI PUBLIC API v1
Accesso programmatico a Genesi tramite API key (header X-API-Key: gns_...).

Endpoints:
  POST   /v1/chat          — invia un messaggio, risposta JSON sincrona
  POST   /v1/chat/stream   — invia un messaggio, risposta SSE streaming
  POST   /v1/upload        — carica un file (immagine, PDF, testo)
  GET    /v1/status        — stato del servizio + info API key

Autenticazione:
  Crea una API key su /auth/api-keys (richiede login JWT).
  Poi usa:  X-API-Key: gns_xxxxxxxxxxxxxxxx

Isolamento:
  Ogni API key mappa su un user_id Genesi separato.
  Memoria, profilo e documenti sono isolati per chiave.

Sicurezza:
  - user_id estratto SOLO dalla API key. Mai dal body.
  - Rate limit configurabile per chiave (default 30 req/min).
  - La chiave raw viene hashata (SHA-256): mai salvata in chiaro.
"""

import asyncio
import json
import io
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from auth.router import require_api_key
from auth.models import AuthUser
from auth.database import get_db
from core.simple_chat import simple_chat_handler
from core.file_analyzer import analyze_file
from core.document_memory import save_document, decay_and_forget, cleanup_by_size
from core.storage import storage
from core.log import log

router = APIRouter(tags=["v1"])

MAX_MESSAGE_LENGTH = 4000
UPLOAD_MAX_MB = 20
UPLOAD_ALLOWED = {'.pdf', '.png', '.jpg', '.jpeg', '.webp', '.txt', '.md', '.heic', '.heif'}


# ─── Schemas ──────────────────────────────────────────────────────────────────

class V1ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None  # conversation_id, auto-generato se assente


class V1ChatResponse(BaseModel):
    response: str
    session_id: str
    intent: Optional[str] = None
    status: str = "ok"


class V1UploadResponse(BaseModel):
    doc_id: str
    filename: str
    type: str
    response: str          # breve conferma
    session_id: str        # conversation_id attiva
    preview_url: Optional[str] = None   # URL HTTP per visualizzare l'immagine


# ─── Helper: salva immagine su disco per servirla via HTTP ────────────────────

_MEDIA_DIR = "memory/v1_media"

import os
os.makedirs(_MEDIA_DIR, exist_ok=True)


def _save_media_file(data: bytes, ext: str, user_id: str) -> str:
    """Salva il file in memory/v1_media/ e ritorna il path relativo."""
    fname = f"{user_id}_{uuid.uuid4().hex[:12]}{ext}"
    path = os.path.join(_MEDIA_DIR, fname)
    with open(path, "wb") as f:
        f.write(data)
    return fname


# ─── GET /v1/status ───────────────────────────────────────────────────────────

@router.get("/status", summary="Stato del servizio")
async def v1_status(user: AuthUser = Depends(require_api_key)):
    return {
        "status": "ok",
        "service": "Genesi API v1",
        "user_id": user.id,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }


# ─── POST /v1/chat ────────────────────────────────────────────────────────────

@router.post("/chat", response_model=V1ChatResponse, summary="Invia un messaggio a Genesi")
async def v1_chat(body: V1ChatRequest, user: AuthUser = Depends(require_api_key)):
    if len(body.message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(400, detail=f"Messaggio troppo lungo (max {MAX_MESSAGE_LENGTH} caratteri).")

    session_id = body.session_id or str(uuid.uuid4())
    log("V1_CHAT_REQUEST", user_id=user.id, session_id=session_id, msg_len=len(body.message))

    try:
        result = await simple_chat_handler(user.id, body.message, conversation_id=session_id)
        if isinstance(result, tuple):
            response_text, intent = result
        else:
            response_text, intent = result, None

        # simple_chat_handler può restituire JSON (es. image_generation)
        # Proviamo a estrarre solo il testo per la risposta v1
        if response_text and response_text.strip().startswith("{"):
            try:
                parsed = json.loads(response_text)
                response_text = parsed.get("text", response_text)
            except Exception:
                pass

        log("V1_CHAT_RESPONSE", user_id=user.id, session_id=session_id, intent=intent)
        return V1ChatResponse(
            response=response_text,
            session_id=session_id,
            intent=intent,
        )
    except Exception as e:
        log("V1_CHAT_ERROR", user_id=user.id, error=str(e))
        raise HTTPException(500, detail="Errore interno. Riprova.")


# ─── POST /v1/chat/stream ─────────────────────────────────────────────────────

@router.post("/chat/stream", summary="Invia un messaggio a Genesi (SSE streaming)")
async def v1_chat_stream(body: V1ChatRequest, user: AuthUser = Depends(require_api_key)):
    if len(body.message) > MAX_MESSAGE_LENGTH:
        raise HTTPException(400, detail=f"Messaggio troppo lungo (max {MAX_MESSAGE_LENGTH} caratteri).")

    session_id = body.session_id or str(uuid.uuid4())
    log("V1_STREAM_REQUEST", user_id=user.id, session_id=session_id)

    async def event_generator():
        try:
            # Invia session_id come primo evento
            yield f"data: {json.dumps({'session_id': session_id})}\n\n"

            result = await simple_chat_handler(user.id, body.message, conversation_id=session_id)
            if isinstance(result, tuple):
                response_text, intent = result
            else:
                response_text, intent = result, None

            if response_text and response_text.strip().startswith("{"):
                try:
                    parsed = json.loads(response_text)
                    response_text = parsed.get("text", response_text)
                except Exception:
                    pass

            # Chunking manuale (il proactor non è SSE-native via v1)
            chunk_size = 80
            for i in range(0, len(response_text), chunk_size):
                chunk = response_text[i:i + chunk_size]
                yield f"data: {json.dumps({'chunk': chunk})}\n\n"
                await asyncio.sleep(0.01)

            yield f"data: {json.dumps({'done': True, 'intent': intent, 'response': response_text})}\n\n"
            log("V1_STREAM_DONE", user_id=user.id, session_id=session_id)
        except Exception as e:
            log("V1_STREAM_ERROR", user_id=user.id, error=str(e))
            yield f"data: {json.dumps({'error': 'Errore interno.'})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ─── POST /v1/upload ─────────────────────────────────────────────────────────

@router.post("/upload", response_model=V1UploadResponse, summary="Carica un file")
async def v1_upload(
    file: UploadFile = File(...),
    user: AuthUser = Depends(require_api_key),
):
    import os as _os

    if not file.filename:
        raise HTTPException(400, detail="Nessun file selezionato.")

    ext = _os.path.splitext(file.filename.lower())[1]
    if ext not in UPLOAD_ALLOWED:
        raise HTTPException(400, detail=f"Formato non supportato: {ext}")

    # Leggi i bytes per validare dimensione
    raw_data = await file.read()
    size_mb = len(raw_data) / (1024 * 1024)
    if size_mb > UPLOAD_MAX_MB:
        raise HTTPException(400, detail=f"File troppo grande: {size_mb:.1f}MB (max {UPLOAD_MAX_MB}MB)")

    # Rimetti a posto il file pointer per analyze_file
    file.file = io.BytesIO(raw_data)
    file.size = len(raw_data)

    log("V1_UPLOAD_START", user_id=user.id, filename=file.filename, size_mb=round(size_mb, 2))

    try:
        result = await analyze_file(file)
    except Exception as e:
        log("V1_UPLOAD_ANALYZE_ERROR", user_id=user.id, error=str(e))
        raise HTTPException(500, detail="Errore nell'analisi del file.")

    user_id = user.id
    doc_id = f"{user_id}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"

    try:
        saved_doc = await save_document(
            doc_id=doc_id,
            user_id=user_id,
            filename=result.get("meta", {}).get("filename", file.filename),
            file_type=result.get("type", "unknown"),
            content=result.get("content", ""),
            meta=result.get("meta", {}),
        )
    except Exception as e:
        log("V1_UPLOAD_SAVE_ERROR", user_id=user_id, error=str(e))
        raise HTTPException(500, detail="Errore nel salvataggio del documento.")

    # Aggiorna active_documents nel profilo
    try:
        profile = await storage.load(f"profile:{user_id}", default={})
        active_docs = profile.get("active_documents", [])
        if doc_id not in active_docs:
            active_docs.append(doc_id)
        while len(active_docs) > 10:
            active_docs.pop(0)
        profile["active_documents"] = active_docs
        await storage.save(f"profile:{user_id}", profile)
    except Exception:
        pass

    # Decay + cleanup asincrono
    asyncio.create_task(asyncio.to_thread(decay_and_forget, user_id))
    asyncio.create_task(asyncio.to_thread(cleanup_by_size, user_id))

    file_type = result.get("type", "unknown")

    # Per immagini: salva su disco e fornisci URL HTTP
    preview_url = None
    if file_type == "image":
        try:
            fname = _save_media_file(raw_data, ext, user_id)
            preview_url = f"/v1/media/{fname}"
        except Exception:
            pass

    # Risposta breve
    display_name = (saved_doc.get("title") if saved_doc else None) or file.filename
    if file_type == "image":
        # Usa la descrizione vision reale se disponibile (GPT-4o ha già analizzato l'immagine)
        vision_content = result.get("content", "").strip()
        if vision_content:
            response_text = vision_content
        else:
            response_text = f"Immagine '{display_name}' caricata. Dimmi cosa vuoi fare!"
    elif file_type == "pdf":
        pages = result.get("meta", {}).get("pages", "?")
        response_text = f"Documento '{display_name}' caricato ({pages} pagine). Cosa vuoi sapere?"
    else:
        lines = result.get("meta", {}).get("lines", "?")
        response_text = f"File '{display_name}' caricato ({lines} righe). Cosa vuoi sapere?"

    log("V1_UPLOAD_OK", user_id=user_id, doc_id=doc_id, type=file_type)

    return V1UploadResponse(
        doc_id=doc_id,
        filename=file.filename,
        type=file_type,
        response=response_text,
        session_id=str(uuid.uuid4()),
        preview_url=preview_url,
    )


# ─── GET /v1/media/{filename} ─────────────────────────────────────────────────

from fastapi.responses import FileResponse

@router.get("/media/{filename}", summary="Accede a un file media caricato via API")
async def v1_media(filename: str, user: AuthUser = Depends(require_api_key)):
    # Sanitize: solo caratteri alfanumerici, trattini, underscore, punto
    import re
    if not re.match(r'^[\w\-\.]+$', filename):
        raise HTTPException(400, detail="Nome file non valido.")

    path = os.path.join(_MEDIA_DIR, filename)
    if not os.path.isfile(path):
        raise HTTPException(404, detail="File non trovato.")

    # Sicurezza: verifica che il file appartenga all'utente (il nome inizia con user_id)
    if not filename.startswith(user.id):
        raise HTTPException(403, detail="Accesso negato.")

    return FileResponse(path)
