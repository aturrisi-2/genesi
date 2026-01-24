from fastapi import FastAPI, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from pydantic import BaseModel
from typing import Dict, Any
from core.state import CognitiveState
from api.user import router as user_router
from api.chat import router as chat_router
from tts.leonardo import synthesize

app = FastAPI()

# Modello per la richiesta TTS
class TTSRequest(BaseModel):
    text: str

# Serve i file statici
app.mount("/static", StaticFiles(directory="static"), name="static")

# API
app.include_router(user_router)
app.include_router(chat_router)

@app.post("/tts")
async def text_to_speech(request: TTSRequest):
    """Endpoint per la sintesi vocale"""
    if not request.text or not isinstance(request.text, str) or not request.text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Il campo 'text' è obbligatorio e non può essere vuoto"
        )

    try:
        wav_path = await synthesize(request.text.strip())
        return FileResponse(
            wav_path,
            media_type="audio/wav",
            filename="sintesi_vocale.wav"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Errore durante la sintesi vocale: {str(e)}"
        )

@app.get("/state/{user_id}")
async def get_state(user_id: str):
    state = CognitiveState.build(user_id)

    def serialize_event(event):
        event_dict = event.to_dict()
        if hasattr(event, "decayed_affect"):
            event_dict["decayed_affect"] = event.decayed_affect
        return event_dict

    return {
        "user": state.user.to_dict(),
        "recent_events": [serialize_event(e) for e in state.recent_events],
        "context": state.context
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)