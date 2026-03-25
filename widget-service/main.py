"""
Genesi Widget Service — servizio standalone embeddabile.
Proxy leggero verso Genesi core: nessuna logica AI locale.

Avvio:
  uvicorn main:app --host 0.0.0.0 --port 8001

Variabili d'ambiente richieste (vedere .env.example):
  GENESI_URL, OPENROUTER_API_KEY, WIDGET_KEYS o WIDGET_API_KEY+WIDGET_EMAIL+WIDGET_PASSWORD
"""
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from api.widget import router as widget_router

app = FastAPI(
    title="Genesi Widget Service",
    # Nessuna documentazione pubblica — protezione IP
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

app.include_router(widget_router)

# Serve static files (widget.min.js, demo pages)
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/widget.js")
async def serve_widget():
    """Serve widget.min.js come /widget.js — URL pubblico per i clienti."""
    minified = "static/widget.min.js"
    source   = "static/widget.js"
    path = minified if os.path.exists(minified) else source
    return FileResponse(path, media_type="application/javascript")


@app.get("/demo")
async def serve_demo():
    return FileResponse("static/demo-cplace.html", media_type="text/html")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "genesi-widget"}
