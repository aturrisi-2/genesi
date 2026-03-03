"""
SETUP WIZARD - Genesi Core v2
Flusso conversazionale per configurare le integrazioni non ancora impostate.

Quando un'integrazione richiede credenziali (API key, token, app secret) non presenti
nel .env, questo modulo gestisce l'intervista guidata all'utente, scrive le variabili
nel file .env e le attiva immediatamente in os.environ (senza riavvio del server).

Storage key: setup_wizard:{user_id}
State structure:
  {
    "platform": "facebook",
    "step": "ask_app_id",       # nome del passo corrente
    "vars": {"FACEBOOK_APP_ID": "123", ...},  # credenziali raccolte finora
  }
"""

import os
import pathlib
import re
from typing import Any, Dict, Optional, Tuple

from core.log import log
from core.storage import storage

# Percorso al file .env nella root del progetto
_ENV_PATH = pathlib.Path(__file__).resolve().parent.parent / ".env"

# ─── Definizione wizard per ogni piattaforma ─────────────────────────────────
# Ogni piattaforma ha una lista di step:
#   (env_var, label, hint, regex_validator | None)
#
WIZARD_STEPS: Dict[str, list] = {
    "facebook": [
        (
            "FACEBOOK_APP_ID",
            "Facebook App ID",
            (
                "Per ottenerlo: vai su **[developers.facebook.com](https://developers.facebook.com)** "
                "→ Crea app → Tipo: Consumatore → Il numero App ID è in alto a sinistra."
            ),
            r"^\d{10,20}$",
        ),
        (
            "FACEBOOK_APP_SECRET",
            "Facebook App Secret",
            "Trovi l'App Secret in: Impostazioni App → Di base → App Secret (clicca Mostra).",
            r"^[a-f0-9]{32}$",
        ),
    ],
    "instagram": [
        (
            "FACEBOOK_APP_ID",
            "Facebook App ID",
            (
                "Instagram usa la stessa app Meta. Vai su **[developers.facebook.com](https://developers.facebook.com)** "
                "→ Crea app → aggiungi il prodotto Instagram Basic Display."
            ),
            r"^\d{10,20}$",
        ),
        (
            "FACEBOOK_APP_SECRET",
            "Facebook App Secret",
            "Trovi l'App Secret in: Impostazioni App → Di base → App Secret.",
            r"^[a-f0-9]{32}$",
        ),
    ],
    "tiktok": [
        (
            "TIKTOK_CLIENT_KEY",
            "TikTok Client Key",
            (
                "Vai su **[developers.tiktok.com](https://developers.tiktok.com)** → Crea app "
                "→ Il Client Key è nella sezione App info."
            ),
            None,
        ),
        (
            "TIKTOK_CLIENT_SECRET",
            "TikTok Client Secret",
            "Il Client Secret è nella stessa pagina App info di TikTok for Developers.",
            None,
        ),
    ],
    "telegram": [
        (
            "TELEGRAM_BOT_TOKEN",
            "Token del bot Telegram",
            (
                "Crea un bot gratis: apri Telegram → cerca **@BotFather** → scrivi `/newbot` "
                "→ scegli nome e username → copia il token (formato: `123456:ABC-DEF...`)."
            ),
            r"^\d+:[A-Za-z0-9_-]{35,}$",
        ),
    ],
}

# Piattaforme con wizard di configurazione disponibile
WIZARD_PLATFORMS = set(WIZARD_STEPS.keys())

# ─── Helpers .env ─────────────────────────────────────────────────────────────

def _write_env_vars(new_vars: Dict[str, str]) -> bool:
    """
    Scrive o aggiorna le variabili nel file .env e le imposta in os.environ.
    Ritorna True se il file è stato scritto con successo.
    """
    try:
        # Leggi il .env attuale
        if _ENV_PATH.exists():
            lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()
        else:
            lines = []

        # Aggiorna le righe esistenti e tieni traccia di quelle da aggiungere
        remaining = dict(new_vars)
        updated_lines = []
        for line in lines:
            match = re.match(r'^([A-Z_][A-Z0-9_]*)=.*$', line)
            if match and match.group(1) in remaining:
                key = match.group(1)
                updated_lines.append(f'{key}={remaining.pop(key)}')
            else:
                updated_lines.append(line)

        # Aggiungi le variabili nuove in fondo
        for key, val in remaining.items():
            updated_lines.append(f'{key}={val}')

        _ENV_PATH.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")

        # Applica immediatamente in os.environ (nessun riavvio necessario)
        for key, val in new_vars.items():
            os.environ[key] = val
            log("SETUP_WIZARD_ENV_SET", key=key)

        return True
    except Exception as e:
        log("SETUP_WIZARD_ENV_WRITE_ERROR", error=str(e))
        return False


# ─── Stato wizard ─────────────────────────────────────────────────────────────

async def load_wizard(user_id: str) -> Optional[Dict[str, Any]]:
    return await storage.load(f"setup_wizard:{user_id}", default=None)


async def save_wizard(user_id: str, state: Dict[str, Any]) -> None:
    await storage.save(f"setup_wizard:{user_id}", state)


async def clear_wizard(user_id: str) -> None:
    await storage.delete(f"setup_wizard:{user_id}")


# ─── Entry point: avvia il wizard ─────────────────────────────────────────────

async def start_wizard(user_id: str, platform: str) -> str:
    """
    Avvia il wizard di configurazione per la piattaforma indicata.
    Salva lo stato iniziale e ritorna il primo messaggio di benvenuto + prima domanda.
    """
    steps = WIZARD_STEPS.get(platform)
    if not steps:
        return f"⚙️ Non so ancora come configurare **{platform}** automaticamente."

    # Verifica quante credenziali mancano (potrebbero esserne già alcune)
    missing = [(k, label, hint, rx) for (k, label, hint, rx) in steps if not os.getenv(k)]
    if not missing:
        return f"✅ **{platform.title()}** è già configurato! Prova a collegarti."

    first_key, first_label, first_hint, _ = missing[0]
    state = {
        "platform": platform,
        "step": first_key,
        "vars": {},
        "pending_steps": [(k, label, hint, rx) for (k, label, hint, rx) in missing[1:]],
    }
    await save_wizard(user_id, state)

    icon = {"facebook": "📘", "instagram": "📸", "tiktok": "🎵", "telegram": "✈️"}.get(platform, "⚙️")
    return (
        f"{icon} **Configurazione {platform.title()}**\n\n"
        f"{first_hint}\n\n"
        f"➡️ Inserisci il tuo **{first_label}**:\n"
        f"_(Scrivi 'annulla' per interrompere)_"
    )


# ─── Gestione step ────────────────────────────────────────────────────────────

async def handle_wizard_step(user_id: str, message: str, state: Dict[str, Any]) -> str:
    """
    Gestisce la risposta dell'utente a un passo del wizard.
    Ritorna il prossimo messaggio (domanda successiva o conferma finale).
    """
    msg = message.strip()

    # Annulla
    if msg.lower() in ("annulla", "stop", "esci", "cancel", "no", "interrompi"):
        await clear_wizard(user_id)
        return "⚙️ Configurazione annullata. Puoi ricominciare quando vuoi."

    platform = state["platform"]
    current_step_key = state["step"]
    collected = state.get("vars", {})
    pending = state.get("pending_steps", [])

    # Trova il regex validator per lo step corrente
    steps = WIZARD_STEPS.get(platform, [])
    current_rx = None
    current_label = current_step_key
    for (k, label, hint, rx) in steps:
        if k == current_step_key:
            current_label = label
            current_rx = rx
            break

    # Valida il valore inserito
    if current_rx and not re.match(current_rx, msg):
        return (
            f"⚠️ Il valore inserito non sembra corretto per **{current_label}**.\n"
            f"Esempio formato atteso: `{_format_example(current_step_key)}`\n\n"
            f"Riprova oppure scrivi 'annulla'."
        )

    # Salva il valore raccolto
    collected[current_step_key] = msg

    # Ci sono altri step?
    if pending:
        next_key, next_label, next_hint, _ = pending[0]
        remaining = pending[1:]
        new_state = {
            "platform": platform,
            "step": next_key,
            "vars": collected,
            "pending_steps": remaining,
        }
        await save_wizard(user_id, new_state)
        return (
            f"✅ **{current_label}** salvato.\n\n"
            f"{next_hint}\n\n"
            f"➡️ Inserisci il tuo **{next_label}**:"
        )

    # Tutti gli step completati → scrivi sul .env e applica
    await clear_wizard(user_id)
    ok = _write_env_vars(collected)
    if not ok:
        return (
            f"❌ Errore nella scrittura del file .env. "
            f"Contatta l'amministratore del server."
        )

    icon = {"facebook": "📘", "instagram": "📸", "tiktok": "🎵", "telegram": "✈️"}.get(platform, "⚙️")
    keys_str = ", ".join(f"`{k}`" for k in collected.keys())
    log("SETUP_WIZARD_COMPLETE", platform=platform, user_id=user_id, keys=list(collected.keys()))

    # Per Telegram: genera subito il link token
    if platform == "telegram":
        from core.integrations.telegram_integration import telegram_integration
        try:
            token = await telegram_integration.generate_link_token(user_id)
            bot_status = await telegram_integration.get_status(user_id)
            bot_username = bot_status.get("bot_username", "GenesiBot")
            return (
                f"{icon} **Telegram configurato!** Variabili salvate: {keys_str}\n\n"
                f"Ora collega il tuo account Telegram inviando al bot:\n\n"
                f"`/start {token}`\n\n"
                f"Oppure: [Apri @{bot_username}](https://t.me/{bot_username}?start={token})"
            )
        except Exception as e:
            return (
                f"{icon} Variabili salvate ({keys_str}), ma errore nella generazione del link: {e}\n"
                f"Riprova con 'collega telegram'."
            )

    # Per OAuth: genera URL di autorizzazione
    from core.integrations import integrations_registry
    integration = integrations_registry.get(platform)
    if integration:
        base_url = os.getenv("BASE_URL", "http://localhost:8000")
        try:
            auth_url = await integration.get_auth_url(user_id, base_url)
            if auth_url:
                return (
                    f"{icon} **{platform.title()} configurato!** Variabili salvate: {keys_str}\n\n"
                    f"Ora puoi autorizzare l'accesso:\n"
                    f"[🔗 Connetti {platform.title()}]({auth_url})"
                )
        except Exception:
            pass

    return (
        f"{icon} **{platform.title()} configurato!** Variabili salvate: {keys_str}\n\n"
        f"Ora puoi tornare nelle Impostazioni → Integrazioni e cliccare **Collega**."
    )


def _format_example(env_key: str) -> str:
    """Ritorna un esempio di formato per la chiave env."""
    examples = {
        "FACEBOOK_APP_ID": "123456789012345",
        "FACEBOOK_APP_SECRET": "a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4",
        "TIKTOK_CLIENT_KEY": "awxxxxxxxxxxxxxx",
        "TIKTOK_CLIENT_SECRET": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
        "TELEGRAM_BOT_TOKEN": "1234567890:ABCdefGhIJKlmnOPQRstUVwXYZ12345678",
    }
    return examples.get(env_key, "valore")
