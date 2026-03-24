"""
MAIN ENTRY POINT - Genesi Core v2
Architettura: Chat libera (Qwen) vs Tecnica (GPT) con Proactor
1 intent → 1 funzione con orchestratore centrale
"""

import os
from dotenv import load_dotenv

# Carica variabili d'ambiente IMMEDIATAMENTE (prima degli import che le usano)
load_dotenv()

from fastapi import FastAPI, HTTPException, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path
import uvicorn
import asyncio
import time
from datetime import datetime, timedelta

# Import base
from api.user import router as user_router
from api.chat import router as chat_router
from api.memory import router as memory_router
from api.proactor_api import router as proactor_router
from tts.tts_api import router as tts_router
from api.stt import router as stt_router
from api.upload import router as upload_router
from auth.router import router as auth_router
from api.notifications import router as notifications_router
from api.conversations import router as conversations_router
from api.coding import coding_router
from api.calendar_auth import router as calendar_auth_router
from api.admin_fallback import router as admin_fallback_router
from api.admin.training import router as admin_training_router
from api.admin.logs import router as admin_logs_router
from api.admin.moltbook import router as admin_moltbook_router
from api.admin.improvement_score import router as admin_improvement_router
from api.integrations import router as integrations_router
from api.news import router as news_router
from api.telegram import router as telegram_router
from api.whatsapp import router as whatsapp_router
from api.widget import router as widget_router
from auth.database import init_db, async_session
from auth.models import Visit
from core.log import log
from core.reminder_engine import reminder_engine
from core.training_autopilot import autopilot as training_autopilot
from core.moltbook_service import moltbook_service
from core.improvement_health import improvement_health
from lab.supervisor import SupervisorEngine
from calendar_manager import calendar_manager

# ===============================
# Applicazione FastAPI
# ===============================

BASE_DIR = Path(__file__).resolve().parent

@asynccontextmanager
async def lifespan(app: FastAPI):
    # STARTUP
    await init_db()
    log("AUTH_DB_INIT", status="ok")
    
    # Start background tasks — keep strong refs in a set to prevent GC
    _bg_tasks: set = set()
    for coro, label in [
        (reminder_checker_background(),        "REMINDER_CHECKER"),
        (calendar_checker_background(),        "CALENDAR_CHECKER"),
        (evolution_scheduler(),                "EVOLUTION_SCHEDULER"),
        (training_autopilot.run_background_loop(), "TRAINING_AUTOPILOT"),
        (moltbook_heartbeat_background(),      "MOLTBOOK_HEARTBEAT"),
        (improvement_health.run_background_loop(), "IMPROVEMENT_HEALTH"),
    ]:
        t = asyncio.create_task(coro)
        _bg_tasks.add(t)
        t.add_done_callback(_bg_tasks.discard)
        log(f"{label}_STARTED", status="ok")

    # Registra webhook Telegram
    from core.telegram_bot import set_webhook
    asyncio.create_task(set_webhook("https://genesi.lucadigitale.eu/api/telegram/webhook"))

    yield  # ← app in esecuzione

    # SHUTDOWN — cancella tutti i background task
    for t in list(_bg_tasks):
        t.cancel()
    if _bg_tasks:
        await asyncio.gather(*_bg_tasks, return_exceptions=True)
    log("BACKGROUND_TASKS_STOPPED", count=len(_bg_tasks), status="ok")

app = FastAPI(title="Genesi Core v2 - Proactor Architecture", redirect_slashes=False, lifespan=lifespan)

# CORS — origini configurabili via CORS_ORIGINS env var
_ALLOWED_ORIGINS = [
    o.strip()
    for o in os.getenv("CORS_ORIGINS", "http://localhost:8000,http://127.0.0.1:8000").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Template configuration
templates = Jinja2Templates(directory="static")

# Build version for cache busting (timestamp di avvio server)
BUILD_VERSION = str(int(time.time()))


# ===============================


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
                try:
                    user_id = reminder["user_id"]
                    reminder_id = reminder["id"]
                    reminder_text = reminder["text"]
                    
                    # Mark as triggered (alarm activated)
                    reminder_engine.mark_reminder_triggered(user_id, reminder_id)
                    
                    # Log the reminder trigger
                    log("REMINDER_ALARM_TRIGGERED", user_id=user_id, reminder_id=reminder_id, text=reminder_text[:50])
                    
                    # Aggiungi notifica in-chat all'utente
                    try:
                        from core.chat_memory import chat_memory
                        
                        # Costruisci messaggio di notifica
                        notification_text = f"🔔 Promemoria: {reminder_text}"
                        
                        # Aggiungi ai messaggi in chat dell'utente
                        chat_memory.add_message(
                            user_id=user_id,
                            message="",  # nessun messaggio utente
                            response=notification_text,
                            intent="reminder_alarm"
                        )
                        log("REMINDER_NOTIFICATION_QUEUED", user_id=user_id, reminder_id=reminder_id)
                        
                    except Exception as e:
                        log("REMINDER_NOTIFICATION_ERROR", user_id=user_id, error=str(e))
                        # Non bloccare: reminder è già triggered anche se notifica fallisce
                    
                    # Email notification
                    try:
                        from core.notification_email import send_reminder_email
                        from auth.database import get_user_by_id
                        from core.storage import storage

                        user = await get_user_by_id(user_id)
                        if user and user.email:
                            # Tenta di recuperare il nome dal profilo
                            profile = await storage.load(f"profile:{user_id}", default={})
                            user_name = profile.get("name", "")
                            
                            asyncio.create_task(
                                send_reminder_email(
                                    user_email=user.email,
                                    reminder_text=reminder_text,
                                    user_name=user_name
                                )
                            )
                    except Exception as e:
                        log("REMINDER_EMAIL_ERROR", user_id=user_id, error=str(e))
                        # Fail-safe: continua anche se email fallisce
                    
                    # Set global alarm flag for frontend
                    import os
                    os.environ["GENESI_ALARM_ACTIVE"] = "true"
                    os.environ["GENESI_ALARM_USER"] = user_id
                    os.environ["GENESI_ALARM_TEXT"] = reminder_text[:100]
                    
                    # TODO: Send notification to user (could be via WebSocket, email, etc.)
                    # TODO: Force TTS response with priority
                    # TODO: Set alarm flag for frontend
                    
                except Exception as e:
                    log("REMINDER_PROCESS_ERROR", reminder_id=reminder.get("id"), error=str(e))
                    # Continua con il prossimo reminder anche se questo fallisce
                
            # Wait 30 seconds before next check
            await asyncio.sleep(30)
            
        except Exception as e:
            log("REMINDER_CHECKER_ERROR", error=str(e))
            # Wait 30 seconds even on error
            await asyncio.sleep(30)


async def calendar_checker_background():
    """
    Background task that checks for calendar reminders every 5 minutes.
    """
    while True:
        try:
            # Check imminent events for all users
            reminders_path = Path("data/reminders")
            if reminders_path.exists():
                for file_path in reminders_path.glob("*.json"):
                    user_id = file_path.stem
                    rems = calendar_manager.list_reminders(user_id, days=1)
                    now = datetime.now()
                    window = timedelta(minutes=10)
                    for r in rems:
                        dt_str = r.get("due")
                        if not dt_str: continue
                        try:
                            clean_dt = dt_str.replace("Z", "+00:00").split(".")[0] if "T" in dt_str else dt_str
                            dt = datetime.fromisoformat(clean_dt)
                            if dt.tzinfo: dt = dt.replace(tzinfo=None)
                            if now <= dt <= now + window:
                                log("CALENDAR_EVENT_IMMINENT", user_id=user_id, summary=r["summary"])
                        except: continue


            await asyncio.sleep(300) # 5 minuti
        except Exception as e:
            log("CALENDAR_CHECKER_ERROR", error=str(e))
            await asyncio.sleep(60)


async def moltbook_heartbeat_background():
    """Moltbook heartbeat ogni 30 min: rispondi a commenti, upvota feed."""
    await asyncio.sleep(60)  # attendi 1 min dopo startup
    while True:
        try:
            await moltbook_service.heartbeat()
        except Exception as e:
            log("MOLTBOOK_LOOP_ERROR", error=str(e))
        await asyncio.sleep(600)   # ogni 10 minuti


async def evolution_scheduler():
    """Evolution scheduler that runs every 12 hours."""
    supervisor = SupervisorEngine()
    while True:
        await asyncio.sleep(43200)  # 12 ore
        try:
            supervisor.run()
        except Exception as e:
            log("EVOLUTION_SCHEDULER_ERROR", error=str(e))


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
    return FileResponse(BASE_DIR / "static" / "admin.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@app.get("/training-admin")
async def serve_training_admin():
    return FileResponse(BASE_DIR / "static" / "admin-training.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@app.get("/admin-logs")
async def serve_admin_logs():
    return FileResponse(BASE_DIR / "static" / "admin-logs.html", headers={"Cache-Control": "no-cache, no-store, must-revalidate"})

@app.get("/brochure")
async def serve_brochure():
    return FileResponse(
        BASE_DIR / "static" / "brochure.html",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )

@app.get("/guida-icloud")
async def serve_guida_icloud():
    return FileResponse(BASE_DIR / "static" / "guida-icloud.html")

@app.get("/widget.js")
async def serve_widget_js():
    return FileResponse(
        BASE_DIR / "static" / "widget.js",
        media_type="application/javascript",
        headers={"Cache-Control": "no-cache"},
    )

@app.get("/widget-demo")
async def serve_widget_demo():
    return FileResponse(BASE_DIR / "static" / "widget-demo.html")

@app.get("/widget-demo-salute")
async def serve_widget_demo_salute():
    return FileResponse(BASE_DIR / "static" / "widget-demo-salute.html")

@app.get("/sw.js")
async def serve_sw():
    return FileResponse(
        BASE_DIR / "static" / "sw.js",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )

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
app.include_router(notifications_router, prefix="/api")
app.include_router(conversations_router, prefix="/api")
app.include_router(calendar_auth_router, prefix="/api")
app.include_router(admin_fallback_router, prefix="/api")
app.include_router(admin_training_router, prefix="/api")
app.include_router(admin_logs_router, prefix="/api")
app.include_router(admin_moltbook_router, prefix="/api")
app.include_router(admin_improvement_router, prefix="/api")
app.include_router(integrations_router, prefix="/api")
app.include_router(news_router)
app.include_router(coding_router)
app.include_router(telegram_router)
app.include_router(whatsapp_router)
app.include_router(widget_router)
from api.weather_widget import router as weather_widget_router
app.include_router(weather_widget_router)
from api.push import router as push_router
app.include_router(push_router)
from api.v1.router import router as v1_router
app.include_router(v1_router, prefix="/v1")

# ===============================
# Health check
# ===============================

@app.get("/health")
async def health_check():
    return {"status": "healthy", "version": "v2", "architecture": "proactor", "storage": "in-memory"}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
