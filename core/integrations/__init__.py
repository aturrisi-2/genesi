"""
INTEGRATIONS REGISTRY - Genesi Core v2
Registry globale di tutte le integrazioni esterne disponibili.
Uso: from core.integrations import integrations_registry
"""

from core.integrations.gmail_integration import gmail_integration
from core.integrations.google_calendar_integration import google_calendar_integration
from core.integrations.telegram_integration import telegram_integration
from core.integrations.whatsapp_integration import whatsapp_integration
from core.integrations.facebook_integration import facebook_integration
from core.integrations.instagram_integration import instagram_integration
from core.integrations.tiktok_integration import tiktok_integration

# Registry piattaforma → istanza
integrations_registry = {
    "gmail": gmail_integration,
    "google_calendar": google_calendar_integration,
    "telegram": telegram_integration,
    "whatsapp": whatsapp_integration,
    "facebook": facebook_integration,
    "instagram": instagram_integration,
    "tiktok": tiktok_integration,
}

__all__ = [
    "integrations_registry",
    "gmail_integration",
    "google_calendar_integration",
    "telegram_integration",
    "whatsapp_integration",
    "facebook_integration",
    "instagram_integration",
    "tiktok_integration",
]
