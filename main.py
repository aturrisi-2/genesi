from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import uvicorn
from pydantic import BaseModel

from core.state import CognitiveState
from api.user import router as user_router
from api.chat import router as chat_router
from tts.coqui import synthesize

# ======================================================
# Setup base
# ======================================================

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

# Root → index.html
@app.get("/")
async def serve_index():
    return FileResponse(BASE_DIR / "static" / "index.html")

# ======================================================
# API
# ======================================================

app.include_router(user_router)
app.include_router(chat_router)

# ======================================================
# TTS
# ======================================================

@app.post("/tts")
async def text_to_speech(request: TTSRequest):
    """
    Endpoint per la sintesi vocale.
    Riceve testo e restituisce audio WAV.
    Compatibile con Safari/iOS.
    """
    if not request.text or not request.text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Il campo 'text' è obbligatorio e non può essere vuoto"
        )

    try:
        # Genera il file audio
        audio_path = synthesize(request.text)
        
        # Imposta gli header per la riproduzione su tutti i browser, inclusi Safari/iOS
        return FileResponse(
            audio_path,
            media_type='audio/wav',
            headers={
                'Accept-Ranges': 'bytes',
                'Content-Disposition': 'inline',
                'Cache-Control': 'no-cache',
                'Content-Transfer-Encoding': 'binary'
            }
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore durante la sintesi vocale: {str(e)}"
        )

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