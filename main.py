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
from api.stt import router as stt_router
from tts.coqui import synthesize_bytes_async
from auth.router import router as auth_router
from auth.database import init_db

# ======================================================
# Config
# ======================================================

ENABLE_TTS = True

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI()


@app.on_event("startup")
async def startup():
    await init_db()

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


@app.get("/register")
async def serve_register():
    return FileResponse(BASE_DIR / "static" / "register.html")


@app.get("/login")
async def serve_login():
    return FileResponse(BASE_DIR / "static" / "login.html")


@app.get("/forgot-password")
async def serve_forgot_password():
    return FileResponse(BASE_DIR / "static" / "forgot-password.html")


@app.get("/reset-password")
async def serve_reset_password():
    return FileResponse(BASE_DIR / "static" / "reset-password.html")


@app.get("/admin")
async def serve_admin():
    return FileResponse(BASE_DIR / "static" / "admin.html")

# ======================================================
# API
# ======================================================

app.include_router(user_router)
app.include_router(chat_router)
app.include_router(upload_router)
app.include_router(stt_router)
app.include_router(auth_router)

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

    # ===============================
    # SANITIZZAZIONE DIFENSIVA TTS
    # ===============================
    # Rimuovi timestamp ISO (es: 2025-02-07T23:42:00.123Z)
    import re
    text = re.sub(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d{3})?Z\s*', '', text)
    # Rimuovi prefissi di log [TAG]
    text = re.sub(r'^\[[A-Z_]+\]\s*', '', text)
    # Rimuovi numeri iniziali seguiti da spazio (es: "1234567890 ")
    text = re.sub(r'^\d+\s+', '', text)
    # Rimuovi parametri temporali residui (ms) che Edge TTS non supporta
    if re.search(r'\d+ms', text):
        print(f"[TTS] WARNING: rimosso parametri temporali dal testo", flush=True)
        text = re.sub(r'\d+\s?ms', '', text)
    # Rimuovi spazi multipli residui
    text = re.sub(r'\s+', ' ', text).strip()
    # Assicura che il testo contenga solo caratteri umani
    if not re.search(r'[a-zA-ZàèéìòùÀÈÉÌÒÙ]', text):
        return JSONResponse(status_code=400, content={"error": "Testo non valido"})
    
    print(f"[TTS] sanitized text='{text[:100]}...'", flush=True)

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
