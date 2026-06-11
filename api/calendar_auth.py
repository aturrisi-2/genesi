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
CALENDAR_SCOPES = ['https://www.googleapis.com/auth/calendar']
GMAIL_SCOPES = [
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.send',
]
SCOPES = CALENDAR_SCOPES  # backward compat

CALLBACK_URI = f"{os.getenv('BASE_URL', 'http://localhost:8000')}/api/calendar/google/callback"

_SUCCESS_HTML = """<!DOCTYPE html>
<html>
<head>
  <title>Connessione Genesi</title>
  <style>
    body {{ font-family: -apple-system, sans-serif; background: #0c0c14; color: #fff;
           display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }}
    .card {{ background: #161625; padding: 40px; border-radius: 20px; text-align: center;
             max-width: 400px; border: 1px solid #232335; }}
    h1 {{ color: #00e5ff; margin-bottom: 16px; }}
    p {{ color: #b4b4c3; line-height: 1.6; }}
  </style>
</head>
<body>
  <div class="card">
    <h1>✅ Connesso!</h1>
    <p>Genesi ha ora accesso a <strong>{service}</strong>.</p>
    <p>Puoi chiudere questa scheda e tornare nella chat.</p>
  </div>
  <script>setTimeout(() => window.close(), 5000);</script>
</body>
</html>"""

@router.get("/login")
async def google_login(user: AuthUser = Depends(require_auth)):
    """Inizia il flusso OAuth con Google per il Calendar."""
    if not os.path.exists(CLIENT_SECRETS_FILE):
        log("GOOGLE_OAUTH_ERROR", error="client_secrets_missing", path=CLIENT_SECRETS_FILE)
        return JSONResponse(
            status_code=500,
            content={"error": f"Configurazione Google mancante sul server ({CLIENT_SECRETS_FILE})."}
        )

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=CALENDAR_SCOPES,
        redirect_uri=CALLBACK_URI,
    )
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        prompt='consent',
        include_granted_scopes='true',
        state=user.id,
    )
    return RedirectResponse(authorization_url)

@router.get("/callback")
async def google_callback(state: str, code: str, request: Request):
    """
    Callback di ritorno da Google — gestisce sia Calendar sia Gmail.
    Il campo `state` può essere:
      - "{user_id}"          → flusso Calendar (comportamento originale)
      - "{user_id}|gmail"    → flusso Gmail (redirect URI condiviso)
    """
    # Parse state
    parts = state.split("|", 1)
    user_id = parts[0]
    platform = parts[1] if len(parts) > 1 else "calendar"

    if not os.path.exists(CLIENT_SECRETS_FILE):
        return HTMLResponse("Errore: Client secrets non trovati.", status_code=500)

    # Usa gli scope corretti in base alla piattaforma
    scopes = GMAIL_SCOPES if platform == "gmail" else CALENDAR_SCOPES

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=scopes,
        redirect_uri=CALLBACK_URI,
    )

    try:
        import os as _os
        # Allow Google to return extra scopes (e.g. calendar appended to gmail)
        # without oauthlib raising "Scope has changed" error
        _os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
        flow.fetch_token(code=code)
        credentials = flow.credentials

        if platform == "gmail":
            # Salva nel registro delle integrazioni Gmail
            from core.integrations.gmail_integration import gmail_integration
            await gmail_integration.save_tokens(user_id, {
                "access_token": credentials.token,
                "refresh_token": credentials.refresh_token,
                "expires_at": credentials.expiry.isoformat() if credentials.expiry else None,
                "scopes": list(credentials.scopes or GMAIL_SCOPES),
                "profile": {},
            })
            log("GMAIL_OAUTH_SUCCESS", user_id=user_id)
            service_name = "Gmail"
        else:
            # Flusso Calendar originale: salva in profile.google_token
            profile = await storage.load(f"profile:{user_id}", default={})
            profile["google_token"] = json.loads(credentials.to_json())
            await storage.save(f"profile:{user_id}", profile)
            log("GOOGLE_OAUTH_SUCCESS", user_id=user_id)
            service_name = "Google Calendar"

        return HTMLResponse(content=_SUCCESS_HTML.format(service=service_name))

    except Exception as e:
        log("GOOGLE_OAUTH_CALLBACK_ERROR", error=str(e), user_id=user_id, platform=platform)
        return HTMLResponse(f"Errore durante l'autorizzazione: {str(e)}", status_code=400)
