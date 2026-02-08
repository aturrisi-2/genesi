from fastapi import FastAPI, HTTPException, Request, status, UploadFile, File
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
    # LOG DI CONFINE TTS_PRE
    # ===============================
    text_head = text[:100] + "..." if len(text) > 100 else text
    text_tail = "..." + text[-100:] if len(text) > 100 else text
    print(f"[TTS_PRE] len={len(text)} head='{text_head}' tail='{text_tail}'", flush=True)
    
    # ASSERT FINALE: testo non vuoto
    if not text or len(text.strip()) == 0:
        print(f"[TTS_PRE] ERROR: testo vuoto!", flush=True)
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
    original_len = len(text)
    text = re.sub(r'\s+', ' ', text).strip()
    after_spaces_len = len(text)
    
    # Assicura che il testo contenga solo caratteri umani
    if not re.search(r'[a-zA-ZàèéìòùÀÈÉÌÒÙ]', text):
        print(f"[TTS_PRE] ERROR: testo non contiene caratteri validi dopo sanitizzazione!", flush=True)
        return JSONResponse(status_code=400, content={"error": "Testo non valido"})
    
    # Verifica modifiche durante sanitizzazione
    if original_len != after_spaces_len:
        print(f"[TTS_PRE] INFO: rimossi {original_len - after_spaces_len} caratteri spazi", flush=True)
    
    print(f"[TTS] sanitized text='{text[:100]}...' (len={len(text)})", flush=True)

    try:
        audio_bytes = await synthesize_bytes_async(text)
        audio_size = len(audio_bytes)
        
        # Calcola durata stimata (MP3 ~128 kbps = 16 KB/s)
        estimated_duration = audio_size / 16000 if audio_size > 0 else 0
        
        print(f"[TTS] OUTPUT: size={audio_size} bytes, duration_est={estimated_duration:.2f}s", flush=True)
        
        # ASSERT FINALE: audio size > 0
        if audio_size == 0:
            print(f"[TTS] ERROR: Audio size 0! text_len={len(text)}", flush=True)
            return JSONResponse(status_code=500, content={"error": "Audio generation failed - empty output"})
        
        if audio_size < 100:
            print(f"[TTS] WARNING: Audio very small ({audio_size} bytes)", flush=True)
        
        return Response(
            content=audio_bytes,
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": "inline",
                "Content-Length": str(audio_size),
                "X-Audio-Duration": str(estimated_duration)
            }
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
