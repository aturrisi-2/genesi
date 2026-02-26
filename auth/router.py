import re
import os
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from auth.config import (
    ADMIN_EMAILS, VERIFY_TOKEN_EXPIRE_HOURS, RESET_TOKEN_EXPIRE_HOURS,
)
from auth.database import get_db
from auth.models import AuthUser, AuthToken, Visit, UsageLog
from auth.security import (
    hash_password, verify_password,
    create_access_token, create_refresh_token,
    decode_token, generate_secure_token,
)
from auth.email import send_verification_email, send_reset_password_email
from auth.init_environment import initialize_user_environment
from core.log import log as _log

# Development mode check
DEV_MODE = os.getenv("DEV_MODE", "false").lower() == "true"

router = APIRouter(prefix="/auth", tags=["auth"])

# ===============================
# Rate limiting (in-memory, per-IP)
# ===============================
_rate_store: dict = {}
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 10     # max requests per window


def _check_rate_limit(ip: str, endpoint: str):
    key = f"{ip}:{endpoint}"
    now = datetime.utcnow()
    entries = _rate_store.get(key, [])
    entries = [t for t in entries if (now - t).total_seconds() < RATE_LIMIT_WINDOW]
    if len(entries) >= RATE_LIMIT_MAX:
        _log("RATE_LIMIT", ip=ip, endpoint=endpoint)
        raise HTTPException(status_code=429, detail="Troppi tentativi. Riprova tra poco.")
    entries.append(now)
    _rate_store[key] = entries


# ===============================
# Schemas
# ===============================

class RegisterRequest(BaseModel):
    email: str
    password: str
    preferences: Optional[dict] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class ResendVerificationRequest(BaseModel):
    email: str


# ===============================
# Validation helpers
# ===============================

EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def _validate_email(email: str):
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Email non valida.")


def _validate_password(password: str):
    if len(password) < 8:
        raise HTTPException(status_code=400, detail="La password deve avere almeno 8 caratteri.")
    if not re.search(r"[A-Z]", password):
        raise HTTPException(status_code=400, detail="La password deve contenere almeno una lettera maiuscola.")
    if not re.search(r"[0-9]", password):
        raise HTTPException(status_code=400, detail="La password deve contenere almeno un numero.")


# ===============================
# STEP 2: Registrazione
# ===============================

@router.post("/register")
async def register(req: RegisterRequest, http_request: Request, db: AsyncSession = Depends(get_db)):
    ip = http_request.client.host if http_request.client else "unknown"
    _check_rate_limit(ip, "register")

    email = req.email.strip().lower()
    _validate_email(email)
    _validate_password(req.password)

    # Check duplicato
    existing_result = await db.execute(select(AuthUser).where(AuthUser.email == email))
    existing = existing_result.scalar_one_or_none()
    if existing:
        _log("AUTH_REGISTER_FAIL", email=email, reason="duplicate", user_id=existing.id)
        if existing.is_verified:
            raise HTTPException(status_code=409, detail="Email già registrata. Prova ad accedere.")
        else:
            raise HTTPException(status_code=409, detail="Email registrata ma non verificata. Controlla la tua posta o richiedi un nuovo invio.")

    # Crea utente
    is_admin = email in ADMIN_EMAILS
    # In DEV_MODE auto-verifichiamo l'utente
    auto_verify = DEV_MODE
    
    user = AuthUser(
        email=email,
        password_hash=hash_password(req.password),
        is_verified=auto_verify,
        is_admin=is_admin,
        preferences=req.preferences or {
            "language": "it",
            "timezone": "Europe/Rome",
            "style_preference": "relazionale",
            "main_goal": "",
            "age_range": "",
        },
    )
    db.add(user)
    await db.flush()  # Assegna user.id prima di creare il token

    if auto_verify:
         _log("AUTH_REGISTER_AUTO_VERIFIED", user_id=user.id, email=email)
         # Inizializza ambiente subito se auto-verificato
         initialize_user_environment(user.id, user.email, user.preferences)
         await db.commit()
         return {
             "message": "Registrazione completata con successo (Accesso immediato abilitato).",
             "user_id": user.id,
             "auto_verified": True
         }

    # Token verifica email (solo se non auto-verificato)
    token_str = generate_secure_token()
    token = AuthToken(
        user_id=user.id,
        token=token_str,
        token_type="verify_email",
        expires_at=datetime.utcnow() + timedelta(hours=VERIFY_TOKEN_EXPIRE_HOURS),
    )
    db.add(token)
    await db.commit()

    _log("AUTH_REGISTER", user_id=user.id, email=email, is_admin=is_admin)

    # Invio email verifica
    await send_verification_email(email, token_str)

    return {
        "message": "Registrazione completata. Controlla la tua email per verificare l'account.",
        "user_id": user.id,
    }


# ===============================
# STEP 3: Verifica Email
# ===============================

@router.get("/verify-email")
async def verify_email(token: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(AuthToken).where(
            AuthToken.token == token,
            AuthToken.token_type == "verify_email",
            AuthToken.used == False,
        )
    )
    auth_token = result.scalar_one_or_none()

    if not auth_token:
        return HTMLResponse(
            content=_html_page("Token non valido", "Il link di verifica non è valido o è già stato usato."),
            status_code=400,
        )

    if datetime.utcnow() > auth_token.expires_at:
        return HTMLResponse(
            content=_html_page("Token scaduto", "Il link di verifica è scaduto. Registrati di nuovo."),
            status_code=400,
        )

    # Attiva utente
    user_result = await db.execute(select(AuthUser).where(AuthUser.id == auth_token.user_id))
    user = user_result.scalar_one_or_none()

    if not user:
        return HTMLResponse(
            content=_html_page("Errore", "Utente non trovato."),
            status_code=404,
        )

    user.is_verified = True
    auth_token.used = True
    await db.commit()

    _log("AUTH_VERIFY", user_id=user.id, email=user.email)

    # Inizializza ambiente Genesi
    initialize_user_environment(user.id, user.email, user.preferences)

    return HTMLResponse(
        content=_html_page(
            "Account Verificato",
            "Il tuo account è stato attivato. Ora puoi accedere a Genesi.",
            show_login_link=True,
        ),
        status_code=200,
    )


# ===============================
# STEP 4: Login
# ===============================

@router.post("/login")
async def login(req: LoginRequest, http_request: Request, db: AsyncSession = Depends(get_db)):
    ip = http_request.client.host if http_request.client else "unknown"
    _check_rate_limit(ip, "login")

    email = req.email.strip().lower()

    result = await db.execute(select(AuthUser).where(AuthUser.email == email))
    user = result.scalar_one_or_none()

    # Risposta generica per sicurezza
    if not user or not verify_password(req.password, user.password_hash):
        _log("AUTH_LOGIN_FAIL", email=email, ip=ip)
        raise HTTPException(status_code=401, detail="Credenziali non valide.")

    if not user.is_verified and not DEV_MODE:
        _log("AUTH_LOGIN_UNVERIFIED", user_id=user.id, email=email)
        raise HTTPException(status_code=403, detail="Account non verificato. Controlla la tua email.")

    # Aggiorna last_login
    user.last_login = datetime.utcnow()
    await db.commit()

    access = create_access_token(user.id, user.is_admin)
    refresh = create_refresh_token(user.id)

    _log("AUTH_LOGIN", user_id=user.id, email=email)
    print(f"[DEBUG AUTH LOGIN] User ID created: {user.id}")  # DEBUG TEMPORANEO
    print(f"[DEBUG AUTH LOGIN] DB URL: {db.bind.url}")  # DEBUG TEMPORANEO

    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
        "user_id": user.id,
        "is_admin": user.is_admin,
    }


# ===============================
# Resend Verification Email
# ===============================

@router.post("/resend-verification")
async def resend_verification(req: ResendVerificationRequest, http_request: Request, db: AsyncSession = Depends(get_db)):
    ip = http_request.client.host if http_request.client else "unknown"
    _check_rate_limit(ip, "resend-verification")

    email = req.email.strip().lower()
    _validate_email(email)

    # User lookup
    result = await db.execute(select(AuthUser).where(AuthUser.email == email))
    user = result.scalar_one_or_none()

    if not user:
        # Generic response to avoid email enumeration
        _log("AUTH_RESEND_VERIFICATION", email=email, found=False)
        return {"status": "ok", "message": "Se l'email è registrata, riceverai un link di verifica."}

    if user.is_verified:
        _log("AUTH_RESEND_VERIFICATION", user_id=user.id, email=email, already_verified=True)
        return {"status": "ok", "message": "Il tuo account è già verificato. Puoi accedere normalmente."}

    # Invalidate previous verification tokens
    old_tokens = await db.execute(
        select(AuthToken).where(
            AuthToken.user_id == user.id,
            AuthToken.token_type == "verify_email",
            AuthToken.used == False,
        )
    )
    for old in old_tokens.scalars():
        old.used = True

    # New verification token
    token_str = generate_secure_token()
    token = AuthToken(
        user_id=user.id,
        token=token_str,
        token_type="verify_email",
        expires_at=datetime.utcnow() + timedelta(hours=VERIFY_TOKEN_EXPIRE_HOURS),
    )
    db.add(token)
    await db.commit()

    _log("AUTH_RESEND_VERIFICATION", user_id=user.id, email=email, found=True, already_verified=False)

    # Send verification email
    try:
        await send_verification_email(email, token_str)
        return {"status": "ok", "message": "Email di verifica inviata."}
    except Exception as e:
        _log("AUTH_RESEND_VERIFICATION_SMTP_ERROR", user_id=user.id, email=email, error=str(e))
        # Human-friendly response, no technical details
        raise HTTPException(
            status_code=500,
            detail="Non è stato possibile inviare l'email. Riprova tra qualche minuto oppure contatta l'amministratore."
        )


# ===============================
# Refresh Token
# ===============================

@router.post("/refresh")
async def refresh_token(req: RefreshRequest, db: AsyncSession = Depends(get_db)):
    payload = decode_token(req.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Refresh token non valido.")

    user_id = payload.get("sub")
    result = await db.execute(select(AuthUser).where(AuthUser.id == user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_verified:
        raise HTTPException(status_code=401, detail="Utente non valido.")

    access = create_access_token(user.id, user.is_admin)
    refresh = create_refresh_token(user.id)

    return {
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
    }


# ===============================
# STEP 5: Recupero Password
# ===============================

@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, http_request: Request, db: AsyncSession = Depends(get_db)):
    ip = http_request.client.host if http_request.client else "unknown"
    _check_rate_limit(ip, "forgot-password")

    email = req.email.strip().lower()

    # Risposta SEMPRE identica (sicurezza)
    generic_response = {"message": "Se l'email è registrata, riceverai un link per reimpostare la password."}

    result = await db.execute(select(AuthUser).where(AuthUser.email == email))
    user = result.scalar_one_or_none()

    if not user:
        _log("AUTH_FORGOT", email=email, found=False)
        return generic_response

    # Invalida token reset precedenti
    old_tokens = await db.execute(
        select(AuthToken).where(
            AuthToken.user_id == user.id,
            AuthToken.token_type == "reset_password",
            AuthToken.used == False,
        )
    )
    for old in old_tokens.scalars():
        old.used = True

    # Nuovo token
    token_str = generate_secure_token()
    token = AuthToken(
        user_id=user.id,
        token=token_str,
        token_type="reset_password",
        expires_at=datetime.utcnow() + timedelta(hours=RESET_TOKEN_EXPIRE_HOURS),
    )
    db.add(token)
    await db.commit()

    _log("AUTH_FORGOT", user_id=user.id, email=email, found=True)

    await send_reset_password_email(email, token_str)

    return generic_response


@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest, http_request: Request, db: AsyncSession = Depends(get_db)):
    ip = http_request.client.host if http_request.client else "unknown"
    _check_rate_limit(ip, "reset-password")

    _validate_password(req.new_password)

    result = await db.execute(
        select(AuthToken).where(
            AuthToken.token == req.token,
            AuthToken.token_type == "reset_password",
            AuthToken.used == False,
        )
    )
    auth_token = result.scalar_one_or_none()

    if not auth_token:
        raise HTTPException(status_code=400, detail="Token non valido o già usato.")

    if datetime.utcnow() > auth_token.expires_at:
        raise HTTPException(status_code=400, detail="Token scaduto. Richiedi un nuovo reset.")

    user_result = await db.execute(select(AuthUser).where(AuthUser.id == auth_token.user_id))
    user = user_result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato.")

    user.password_hash = hash_password(req.new_password)
    auth_token.used = True
    await db.commit()

    _log("AUTH_RESET", user_id=user.id, email=user.email)

    return {"message": "Password reimpostata con successo. Ora puoi accedere."}


# ===============================
# STEP 7: Admin Stats
# ===============================

@router.get("/admin/stats")
async def admin_stats(http_request: Request, db: AsyncSession = Depends(get_db)):
    # Verifica JWT dal header
    auth_header = http_request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token mancante.")

    payload = decode_token(auth_header.split(" ")[1])
    if not payload:
        raise HTTPException(status_code=401, detail="Token non valido.")

    if not payload.get("admin"):
        raise HTTPException(status_code=403, detail="Accesso negato.")

    # Verifica email whitelist
    user_result = await db.execute(select(AuthUser).where(AuthUser.id == payload["sub"]))
    user = user_result.scalar_one_or_none()
    if not user or user.email not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Accesso negato.")

    now = datetime.utcnow()
    seven_days_ago = now - timedelta(days=7)
    thirty_days_ago = now - timedelta(days=30)

    total = (await db.execute(select(func.count(AuthUser.id)))).scalar()
    verified = (await db.execute(
        select(func.count(AuthUser.id)).where(AuthUser.is_verified == True)
    )).scalar()
    active_7d = (await db.execute(
        select(func.count(AuthUser.id)).where(AuthUser.last_login >= seven_days_ago)
    )).scalar()
    active_30d = (await db.execute(
        select(func.count(AuthUser.id)).where(AuthUser.last_login >= thirty_days_ago)
    )).scalar()

    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    registrations_today = (await db.execute(
        select(func.count(AuthUser.id)).where(AuthUser.created_at >= today_start)
    )).scalar()

    # Visit tracking stats
    twenty_four_hours_ago = now - timedelta(hours=24)
    visits_24h = (await db.execute(
        select(func.count(Visit.id)).where(Visit.visited_at >= twenty_four_hours_ago)
    )).scalar()

    # Last 10 logins
    recent_logins_result = await db.execute(
        select(AuthUser.email, AuthUser.last_login)
        .where(AuthUser.last_login.isnot(None))
        .order_by(AuthUser.last_login.desc())
        .limit(10)
    )
    recent_logins = [
        {"email": row.email, "last_login": row.last_login.isoformat() if row.last_login else None}
        for row in recent_logins_result
    ]

    # User List with Usage
    # We join AuthUser with a subquery that sums UsageLog
    from sqlalchemy import outerjoin
    usage_sub = (
        select(
            UsageLog.user_id,
            func.sum(UsageLog.prompt_tokens).label("p_sum"),
            func.sum(UsageLog.completion_tokens).label("c_sum")
        )
        .group_by(UsageLog.user_id)
        .subquery()
    )
    
    users_result = await db.execute(
        select(
            AuthUser.email,
            AuthUser.created_at,
            AuthUser.last_login,
            usage_sub.c.p_sum,
            usage_sub.c.c_sum
        )
        .outerjoin(usage_sub, AuthUser.id == usage_sub.c.user_id)
        .order_by(AuthUser.created_at.desc())
    )
    
    user_list = []
    for row in users_result:
        user_list.append({
            "email": row.email,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "last_login": row.last_login.isoformat() if row.last_login else None,
            "prompt_tokens": int(row.p_sum or 0),
            "completion_tokens": int(row.c_sum or 0),
            "total_tokens": int((row.p_sum or 0) + (row.c_sum or 0))
        })

    # OpenRouter Balance (Optional)
    or_balance = None
    import httpx
    or_key = os.getenv("OPENROUTER_API_KEY")
    if or_key:
        try:
            async with httpx.AsyncClient() as client:
                res = await client.get(
                    "https://openrouter.ai/api/v1/auth/key",
                    headers={"Authorization": f"Bearer {or_key}"}
                )
                if res.status_code == 200:
                    or_balance = res.json().get("data", {}).get("usage", 0) # This is limit/usage info
                    # Note: OpenRouter key info usually has 'usage' and 'limit'
                    key_data = res.json().get("data", {})
                    or_balance = {
                        "usage": key_data.get("usage", 0),
                        "limit": key_data.get("limit", 0),
                        "is_free_tier": key_data.get("is_free_tier", False)
                    }
        except:
            pass

    _log("ADMIN_STATS", admin_id=user.id)

    return {
        "total_users": total,
        "verified_users": verified,
        "active_7d": active_7d,
        "active_30d": active_30d,
        "registrations_today": registrations_today,
        "visits_24h": visits_24h,
        "recent_logins": recent_logins,
        "user_list": user_list,
        "or_balance": or_balance,
        "timestamp": now.isoformat(),
    }


# ===============================
# STEP 8: /me — current user info
# ===============================

@router.get("/me")
async def get_me(http_request: Request, db: AsyncSession = Depends(get_db)):
    auth_header = http_request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token mancante.")

    payload = decode_token(auth_header.split(" ")[1])
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Token non valido o scaduto.")

    user_id = payload.get("sub")
    result = await db.execute(select(AuthUser).where(AuthUser.id == user_id))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Utente non trovato.")

    return {
        "user_id": user.id,
        "email": user.email,
        "is_admin": user.is_admin,
        "is_verified": user.is_verified,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "preferences": user.preferences,
    }


# ===============================
# STEP 9: /logout — invalidate (client-side, server ack)
# ===============================

@router.post("/logout")
async def logout(http_request: Request):
    auth_header = http_request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        payload = decode_token(auth_header.split(" ")[1])
        user_id = payload.get("sub") if payload else "unknown"
    else:
        user_id = "unknown"

    _log("AUTH_LOGOUT", user_id=user_id)
    return {"message": "Logout effettuato."}


# ===============================
# Middleware dependencies: require_auth, require_admin
# ===============================

async def require_auth(request: Request, db: AsyncSession = Depends(get_db)) -> AuthUser:
    """FastAPI dependency: extracts and validates JWT, returns AuthUser."""
    auth_header = request.headers.get("Authorization", "")
    token = None
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
    else:
        # Fallback to query param for link-based flows (OAuth)
        token = request.query_params.get("token")

    if not token:
        raise HTTPException(status_code=401, detail="Autenticazione richiesta.")
    print(f"TOKEN RECEIVED: {token}")  # DEBUG TEMPORANEO
    
    try:
        payload = decode_token(token)
        print(f"DECODED PAYLOAD: {payload}")  # DEBUG TEMPORANEO
    except Exception as e:
        print(f"JWT ERROR: {type(e)} - {str(e)}")  # DEBUG TEMPORANEO
        raise HTTPException(status_code=401, detail="Token non valido o scaduto.")
    
    if not payload or payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Token non valido o scaduto.")

    user_id = payload.get("sub")
    print(f"[DEBUG GET_CURRENT_USER] Looking for user_id: {user_id}")  # DEBUG TEMPORANEO
    result = await db.execute(select(AuthUser).where(AuthUser.id == user_id))
    user = result.scalar_one_or_none()
    print(f"[DEBUG GET_CURRENT_USER] User found: {user}")  # DEBUG TEMPORANEO

    if not user or (not user.is_verified and not DEV_MODE):
        print(f"[DEBUG GET_CURRENT_USER] User verification failed - user: {user}, is_verified: {user.is_verified if user else 'None'}, DEV_MODE: {DEV_MODE}")  # DEBUG TEMPORANEO
        raise HTTPException(status_code=401, detail="Utente non valido.")

    return user


async def require_admin(request: Request, db: AsyncSession = Depends(get_db)) -> AuthUser:
    """FastAPI dependency: require_auth + admin check."""
    user = await require_auth(request, db)
    if not user.is_admin or user.email not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="Accesso negato.")
    return user


# ===============================
# HTML helper per verify-email
# ===============================

def _html_page(title: str, message: str, show_login_link: bool = False) -> str:
    login_link = ""
    if show_login_link:
        login_link = '<a href="/login" style="display:inline-block;margin-top:24px;padding:12px 32px;background:#00e5ff;color:#0c0c14;text-decoration:none;border-radius:8px;font-weight:600;">Accedi</a>'

    return f"""<!DOCTYPE html>
<html lang="it">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} — Genesi</title>
    <style>
        body {{ font-family: -apple-system, sans-serif; background: #0c0c14; color: #fff; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; }}
        .card {{ max-width: 420px; padding: 40px; text-align: center; }}
        h1 {{ color: #00e5ff; margin-bottom: 16px; font-size: 24px; }}
        p {{ color: #b4b4c3; line-height: 1.6; }}
    </style>
</head>
<body>
    <div class="card">
        <h1>{title}</h1>
        <p>{message}</p>
        {login_link}
    </div>
</body>
</html>"""
