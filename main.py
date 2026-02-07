from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import uvicorn
from pydantic import BaseModel

from core.state import CognitiveState
from api.user import router as user_router
from api.chat import router as chat_router
from api.upload import router as upload_router
from tts.coqui import synthesize_bytes_async

# ======================================================
# Config
# ======================================================

ENABLE_TTS = True

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI()

# ======================================================
# Modelli
# ======================================================

class TTSRequest(BaseModel):
    text: str

# ======================================================
# Static files
# ======================================================

app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def serve_index():
    return FileResponse(BASE_DIR / "static" / "index.html")

# ======================================================
# API
# ======================================================

app.include_router(user_router)
app.include_router(chat_router)
app.include_router(upload_router)

# ======================================================
# TTS — Edge TTS (Microsoft Neural, gratuito)
# ======================================================

@app.post("/tts")
async def text_to_speech(request: TTSRequest):
    if not ENABLE_TTS:
        return JSONResponse(status_code=200, content={"enabled": False})

    text = (request.text or "").strip()
    if not text:
        return JSONResponse(status_code=400, content={"error": "Testo vuoto"})

    try:
        audio_bytes = await synthesize_bytes_async(text)
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={"Content-Disposition": "inline"}
        )
    except Exception as e:
        print(f"[TTS] error: {e}", flush=True)
        return JSONResponse(status_code=500, content={"error": str(e)})

# ======================================================
# State
# ======================================================

@app.get("/state/{user_id}")
async def get_state(user_id: str):
    state = CognitiveState.build(user_id)
    return {
        "user": state.user.to_dict(),
        "recent_events": [e.to_dict() for e in state.recent_events],
        "context": state.context
    }

# ======================================================
# Run
# ======================================================

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
