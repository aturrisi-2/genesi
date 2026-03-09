import os
import logging
import warnings
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ===============================
# JWT
# ===============================
_JWT_DEFAULT = "dev_secret_key_for_testing_only_32b"
JWT_SECRET = os.getenv("JWT_SECRET", _JWT_DEFAULT)

if JWT_SECRET == _JWT_DEFAULT:
    warnings.warn(
        "ATTENZIONE SICUREZZA: JWT_SECRET non è impostato nel file .env. "
        "Il sistema sta usando un segreto di sviluppo NON SICURO per la produzione. "
        "Genera un segreto con: python -c \"import secrets; print(secrets.token_hex(32))\" "
        "e aggiungilo al file .env come JWT_SECRET=<valore>",
        stacklevel=1,
    )
    logging.getLogger(__name__).critical(
        "JWT_SECRET non configurato — uso valore di default NON SICURO"
    )
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
REFRESH_TOKEN_EXPIRE_DAYS = 365

# ===============================
# EMAIL (SMTP Gmail)
# ===============================
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM = os.getenv("EMAIL_FROM", "no-reply@lucadigitale.eu")
EMAIL_REPLY_TO = os.getenv("EMAIL_REPLY_TO", "idappleturrisi@gmail.com")

# ===============================
# APP
# ===============================
BASE_URL = os.getenv("BASE_URL", "http://localhost:8000")

# ===============================
# ADMIN WHITELIST
# ===============================
ADMIN_EMAILS = [e.strip() for e in os.getenv("ADMIN_EMAILS", "idappleturrisi@gmail.com").split(",")]

# ===============================
# DATABASE
# ===============================
DB_DIR = Path("data/auth")
DB_DIR.mkdir(parents=True, exist_ok=True)
DATABASE_URL = f"sqlite+aiosqlite:///{DB_DIR}/genesi_auth.db"

# ===============================
# TOKEN EXPIRY
# ===============================
VERIFY_TOKEN_EXPIRE_HOURS = 48
RESET_TOKEN_EXPIRE_HOURS = 1
