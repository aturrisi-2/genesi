"""
UPLOAD API - Genesi Core v2
1 intent → 1 funzione
Upload semplice senza orchestrazione complessa
"""

from fastapi import APIRouter, HTTPException, UploadFile, File
from pathlib import Path
import uuid
import logging
from core.log import log

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

UPLOAD_DIR = Path("uploads")
UPLOAD_DIR.mkdir(exist_ok=True)

@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload file - 1 intent → 1 funzione
    
    Args:
        file: File da caricare
        
    Returns:
        Risposta semplice
    """
    try:
        # Genera filename unico
        file_id = str(uuid.uuid4())
        file_extension = Path(file.filename).suffix
        safe_filename = f"{file_id}{file_extension}"
        file_path = UPLOAD_DIR / safe_filename
        
        # Salva file
        with open(file_path, "wb") as buffer:
            content = await file.read()
            buffer.write(content)
        
        log("FILE_UPLOADED", filename=file.filename, file_id=file_id)
        
        return {
            "file_id": file_id,
            "filename": file.filename,
            "status": "uploaded",
            "message": f"File '{file.filename}' caricato con successo"
        }
        
    except Exception as e:
        log("UPLOAD_ERROR", error=str(e))
        raise HTTPException(status_code=500, detail="Upload error")

@router.get("/upload/{file_id}")
async def get_file(file_id: str):
    """
    Recupera file - 1 intent → 1 funzione
    """
    try:
        # Cerca file per ID
        for file_path in UPLOAD_DIR.glob(f"{file_id}.*"):
            log("FILE_RETRIEVED", file_id=file_id)
            return FileResponse(file_path)
        
        raise HTTPException(status_code=404, detail="File non trovato")
        
    except Exception as e:
        log("FILE_RETRIEVE_ERROR", error=str(e))
        raise HTTPException(status_code=500, detail="File retrieve error")
