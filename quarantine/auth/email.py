import aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from auth.config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASSWORD,
    EMAIL_FROM, EMAIL_REPLY_TO, BASE_URL,
)
from core.log import log as _log


async def send_verification_email(to_email: str, token: str):
    verify_url = f"{BASE_URL}/auth/verify-email?token={token}"
    subject = "Genesi — Verifica il tuo account"
    html = f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px; background: #0c0c14; color: #fff; border-radius: 12px;">
        <h2 style="color: #00e5ff; margin-bottom: 16px;">Benvenuto in Genesi</h2>
        <p style="line-height: 1.6; color: #b4b4c3;">
            Per attivare il tuo account, clicca sul pulsante qui sotto.
        </p>
        <a href="{verify_url}" style="display: inline-block; margin: 24px 0; padding: 12px 32px; background: #00e5ff; color: #0c0c14; text-decoration: none; border-radius: 8px; font-weight: 600;">
            Verifica Email
        </a>
        <p style="font-size: 13px; color: #666; margin-top: 24px;">
            Se non hai creato un account su Genesi, ignora questa email.<br>
            Il link scade tra 48 ore.
        </p>
    </div>
    """
    await _send_email(to_email, subject, html)


async def send_reset_password_email(to_email: str, token: str):
    reset_url = f"{BASE_URL}/reset-password?token={token}"
    subject = "Genesi — Recupero password"
    html = f"""
    <div style="font-family: -apple-system, sans-serif; max-width: 480px; margin: 0 auto; padding: 32px; background: #0c0c14; color: #fff; border-radius: 12px;">
        <h2 style="color: #00e5ff; margin-bottom: 16px;">Recupero Password</h2>
        <p style="line-height: 1.6; color: #b4b4c3;">
            Hai richiesto il reset della password. Clicca il pulsante per impostarne una nuova.
        </p>
        <a href="{reset_url}" style="display: inline-block; margin: 24px 0; padding: 12px 32px; background: #00e5ff; color: #0c0c14; text-decoration: none; border-radius: 8px; font-weight: 600;">
            Reimposta Password
        </a>
        <p style="font-size: 13px; color: #666; margin-top: 24px;">
            Se non hai richiesto il reset, ignora questa email.<br>
            Il link scade tra 1 ora.
        </p>
    </div>
    """
    await _send_email(to_email, subject, html)


async def _send_email(to_email: str, subject: str, html_body: str):
    if not SMTP_USER or not SMTP_PASSWORD:
        _log("EMAIL_SKIP", reason="SMTP credentials not configured", to=to_email)
        return

    msg = MIMEMultipart("alternative")
    msg["From"] = EMAIL_FROM
    msg["To"] = to_email
    msg["Reply-To"] = EMAIL_REPLY_TO
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASSWORD,
            start_tls=True,
        )
        _log("EMAIL_SENT", to=to_email, subject=subject)
    except Exception as e:
        _log("EMAIL_ERROR", to=to_email, error=str(e))
