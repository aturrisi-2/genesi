"""
Email notification per reminder triggered.
Usa SMTP asincrono. Fail-safe: se fallisce non blocca il reminder.
"""
import asyncio
import os
import smtplib
from email.mime.text import MIMEText
from core.log import log


async def send_reminder_email(user_email: str, reminder_text: str, user_name: str = "") -> bool:
    """
    Invia email di notifica per reminder scattato.
    Returns True se inviata, False se fallita (non solleva eccezioni).
    """
    smtp_host = os.getenv("SMTP_HOST", "")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASSWORD", "")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)

    if not smtp_host or not smtp_user:
        log("REMINDER_EMAIL_SKIP", reason="smtp_not_configured")
        return False

    name_part = f", {user_name}" if user_name else ""
    subject = "🔔 Genesi — Promemoria"
    body = f"Ciao{name_part}!\n\nTi ricordo: {reminder_text}\n\n— Genesi"

    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = subject
        msg["From"] = smtp_from
        msg["To"] = user_email

        # Esegui in thread per non bloccare event loop
        def _send():
            with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.sendmail(smtp_from, [user_email], msg.as_string())

        await asyncio.get_event_loop().run_in_executor(None, _send)
        log("REMINDER_EMAIL_SENT", to=user_email, text=reminder_text[:50])
        return True

    except Exception as e:
        log("REMINDER_EMAIL_FAILED", to=user_email, error=str(e))
        return False
