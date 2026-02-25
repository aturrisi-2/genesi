from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from google_auth_oauthlib.flow import Flow
import json
import os
from core.storage import storage
from auth.router import require_auth
from auth.models import AuthUser
from core.log import log

router = APIRouter(prefix="/calendar/google", tags=["calendar"])

# Carichiamo i percorsi dal .env
CLIENT_SECRETS_FILE = os.getenv("GOOGLE_CREDENTIALS_PATH", "data/calendar/credentials.json")
SCOPES = ['https://www.googleapis.com/auth/calendar']

@router.get("/login")
async def google_login(user: AuthUser = Depends(require_auth)):
    """Inizia il flusso OAuth con Google."""
    if not os.path.exists(CLIENT_SECRETS_FILE):
        log("GOOGLE_OAUTH_ERROR", error="client_secrets_missing", path=CLIENT_SECRETS_FILE)
        return JSONResponse(
            status_code=500,
            content={"error": f"Configurazione Google mancante sul server ({CLIENT_SECRETS_FILE})."}
        )

    # Configuriamo il flow
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=f"{os.getenv('BASE_URL')}/api/calendar/google/callback"
    )

    # Generiamo l'URL di autorizzazione
    # Usiamo 'state' per passare lo user_id in modo sicuro
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        prompt='consent',
        include_granted_scopes='true',
        state=user.id
    )

    return RedirectResponse(authorization_url)

@router.get("/callback")
async def google_callback(state: str, code: str, request: Request):
    """Callback di ritorno da Google."""
    user_id = state
    
    if not os.path.exists(CLIENT_SECRETS_FILE):
        return HTMLResponse("Errore: Client secrets non trovati.", status_code=500)

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=f"{os.getenv('BASE_URL')}/api/calendar/google/callback"
    )

    try:
        # Scambiamo il codice per i token
        flow.fetch_token(code=code)
        credentials = flow.credentials
        
        # Salviamo tutto nel profilo utente su storage
        profile = await storage.load(f"profile:{user_id}", default={})
        profile["google_token"] = json.loads(credentials.to_json())
        await storage.save(f"profile:{user_id}", profile)
        
        log("GOOGLE_OAUTH_SUCCESS", user_id=user_id)
        
        return HTMLResponse(content=f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Connessione Genesi</title>
            <style>
                body {{ font-family: -apple-system, sans-serif; background: #0c0c14; color: #fff; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }}
                .card {{ background: #161625; padding: 40px; border-radius: 20px; text-align: center; max-width: 400px; border: 1px solid #232335; }}
                h1 {{ color: #00e5ff; margin-bottom: 16px; }}
                p {{ color: #b4b4c3; line-height: 1.6; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h1>✅ Connesso!</h1>
                <p>Genesi ha ora accesso al tuo Google Calendar.</p>
                <p>Puoi chiudere questa scheda e tornare nella chat.</p>
            </div>
            <script>setTimeout(() => window.close(), 5000);</script>
        </body>
        </html>
        """)
    except Exception as e:
        log("GOOGLE_OAUTH_CALLBACK_ERROR", error=str(e), user_id=user_id)
        return HTMLResponse(f"Errore durante l'autorizzazione: {str(e)}", status_code=400)
