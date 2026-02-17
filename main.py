"""
MAIN ENTRY POINT - Genesi Core v2
Architettura: Chat libera (Qwen) vs Tecnica (GPT) con Proactor
1 intent → 1 funzione con orchestratore centrale
"""

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path
import uvicorn
import asyncio
import time
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
from lab.supervisor import SupervisorEngine

# ===============================
# Applicazione FastAPI
# ===============================

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="Genesi Core v2 - Proactor Architecture", redirect_slashes=False)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Template configuration
templates = Jinja2Templates(directory="static")

# Build version for cache busting (timestamp di avvio server)
BUILD_VERSION = str(int(time.time()))


# ===============================
# Startup: init auth DB
# ===============================

@app.on_event("startup")
async def startup():
    await init_db()
    log("AUTH_DB_INIT", status="ok")
    
    # Start reminder checker background task
    asyncio.create_task(reminder_checker_background())
    
    # Start evolution scheduler (12 hours)
    asyncio.create_task(evolution_scheduler())
    log("REMINDER_CHECKER_STARTED", status="ok")


async def reminder_checker_background():
    """
    Background task that checks for due reminders every 30 seconds.
    """
    while True:
        try:
            # Get due reminders
            due_reminders = reminder_engine.get_due_reminders()
            
            # Log solo se ci sono reminder dovuti
            if due_reminders:
                log("REMINDER_DUE", total_due=len(due_reminders))
            
            for reminder in due_reminders:
                user_id = reminder["user_id"]
                reminder_id = reminder["id"]
                reminder_text = reminder["text"]
                
                # Mark as triggered (alarm activated)
                reminder_engine.mark_reminder_triggered(user_id, reminder_id)
                
                # Log the reminder trigger
                log("REMINDER_ALARM_TRIGGERED", user_id=user_id, reminder_id=reminder_id, text=reminder_text[:50])
                
                # Set global alarm flag for frontend
                import os
                os.environ["GENESI_ALARM_ACTIVE"] = "true"
                os.environ["GENESI_ALARM_USER"] = user_id
                os.environ["GENESI_ALARM_TEXT"] = reminder_text[:100]
                
                # TODO: Send notification to user (could be via WebSocket, email, etc.)
                # TODO: Force TTS response with priority
                # TODO: Set alarm flag for frontend
                
            # Wait 30 seconds before next check
            await asyncio.sleep(30)
            
        except Exception as e:
            log("REMINDER_CHECKER_ERROR", error=str(e))
            # Wait 30 seconds even on error
            await asyncio.sleep(30)


async def evolution_scheduler():
    """Evolution scheduler that runs every 12 hours."""
    supervisor = SupervisorEngine()
    while True:
        await asyncio.sleep(43200)  # 12 ore
        try:
            supervisor.run()
        except Exception as e:
            print(f"EVOLUTION_SCHEDULER_ERROR {e}")


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
async def serve_index(request: Request):
    return templates.TemplateResponse("index.html", {
        "request": request,
        "build_version": BUILD_VERSION
    })


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
