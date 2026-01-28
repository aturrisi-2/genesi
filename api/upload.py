from fastapi import APIRouter, HTTPException, UploadFile, File, status
import os
import uuid
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

UPLOAD_DIR = "/tmp/genesi_uploads"

@router.post("/upload")
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
        
        return {
            "file_id": file_id,
            "filename": file.filename,
            "content_type": file.content_type or "application/octet-stream"
        }
    
    except Exception as e:
        logger.error(f"Upload error: {e}")
        raise HTTPException(status_code=500, detail="Upload failed")
