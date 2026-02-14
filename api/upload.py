"""
UPLOAD API v2 - Genesi Core v2
Upload + analisi automatica file (PDF, immagini, testo).
Smista a file_analyzer per elaborazione.
"""

from fastapi import APIRouter, UploadFile, File, HTTPException
from core.file_analyzer import analyze_file

router = APIRouter(prefix="/upload")


@router.post("/")
async def upload_file(file: UploadFile = File(...)):
    try:
        result = await analyze_file(file)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
