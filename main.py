"""
MAIN ENTRY POINT - Genesi Core v2
Architettura: Chat libera (Qwen) vs Tecnica (GPT) con Proactor
1 intent → 1 funzione con orchestratore centrale
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path
import uvicorn
import asyncio
from datetime import datetime

# Import base
from api.user import router as user_router
from api.chat import router as chat_router
from api.memory import router as memory_router
from api.proactor_api import router as proactor_router
from tts.tts_api import router as tts_router
from api.stt import router as stt_router
from api.upload import router as upload_router
from auth.router import router as auth_router
from auth.database import init_db, async_session
from auth.models import Visit
from core.log import log
from core.reminder_engine import reminder_engine

# ===============================
# Applicazione FastAPI
# ===============================

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Genesi Core v2 - Proactor Architecture")

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")


# ===============================
# Startup: init auth DB
# ===============================

@app.on_event("startup")
async def startup():
    await init_db()
    log("AUTH_DB_INIT", status="ok")
    
    # Start reminder checker background task
    asyncio.create_task(reminder_checker_background())
    log("REMINDER_CHECKER_STARTED", status="ok")


async def reminder_checker_background():
    """
    Background task that checks for due reminders every 30 seconds.
    """
    while True:
        try:
            # Get due reminders
            due_reminders = reminder_engine.get_due_reminders()
            
            for reminder in due_reminders:
                user_id = reminder["user_id"]
                reminder_id = reminder["id"]
                reminder_text = reminder["text"]
                
                # Log the reminder trigger
                log("REMINDER_TRIGGERED", user_id=user_id, reminder_id=reminder_id, text=reminder_text[:50])
                
                # Mark as done
                reminder_engine.mark_reminder_done(user_id, reminder_id)
                
                # TODO: Send notification to user (could be via WebSocket, email, etc.)
                # For now, just log it
            
            # Wait 30 seconds before next check
            await asyncio.sleep(30)
            
        except Exception as e:
            log("REMINDER_CHECKER_ERROR", error=str(e))
            # Wait 30 seconds even on error
            await asyncio.sleep(30)


# ===============================
# Visit tracking middleware
# ===============================

@app.middleware("http")
async def track_visits(request: Request, call_next):
    response = await call_next(request)
    # Track only page visits (GET on HTML pages), not API/static
    if request.method == "GET" and request.url.path in (
        "/", "/login", "/register", "/forgot-password", "/reset-password", "/admin"
    ):
        try:
            ip = request.client.host if request.client else "unknown"
            ua = request.headers.get("user-agent", "")[:200]
            async with async_session() as session:
                visit = Visit(ip=ip, user_agent=ua, path=request.url.path)
                session.add(visit)
                await session.commit()
        except Exception:
            pass  # Non-blocking: visit tracking must never break the app
    return response


# ===============================
# Auth page routes (serve HTML)
# ===============================

@app.get("/login")
async def serve_login():
    return FileResponse(BASE_DIR / "static" / "login.html")

@app.get("/register")
async def serve_register():
    return FileResponse(BASE_DIR / "static" / "register.html")

@app.get("/forgot-password")
async def serve_forgot_password():
    return FileResponse(BASE_DIR / "static" / "forgot-password.html")

@app.get("/reset-password")
async def serve_reset_password():
    return FileResponse(BASE_DIR / "static" / "reset-password.html")

@app.get("/admin")
async def serve_admin():
    return FileResponse(BASE_DIR / "static" / "admin.html")

@app.get("/")
async def serve_index():
    return FileResponse(BASE_DIR / "static" / "index.html")


# ===============================
# API routes
# ===============================

app.include_router(auth_router)
app.include_router(user_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(memory_router, prefix="/api")
app.include_router(proactor_router, prefix="/api")
app.include_router(tts_router, prefix="/api")
app.include_router(stt_router, prefix="/api")
app.include_router(upload_router, prefix="/api")

# ===============================
# Health check
# ===============================

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "v2", "architecture": "proactor", "storage": "in-memory"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
