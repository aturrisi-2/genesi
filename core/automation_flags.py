"""
AUTOMATION FLAGS — Genesi (FASE 0)
==================================

Interruttore CENTRALIZZATO e reversibile per tutte le automazioni proattive.

Principio (fail-safe):
  - Master switch ``GENESI_PASSIVE_MODE`` (default True): se attivo, OGNI
    automazione proattiva è disattivata, a prescindere dai flag granulari.
  - Ogni flag proattivo è OFF di default. Per riattivare un comportamento
    servono DUE condizioni: ``GENESI_PASSIVE_MODE=false`` E il flag specifico
    = ``true``.
  - Le funzioni "su richiesta" (risposta a chi interpella Genesi) NON passano
    da qui: restano sempre attive.

Nessun codice viene cancellato: i punti di uscita outbound chiamano
``flag_enabled(...)`` (o gli helper ``is_*``) e, se False, fanno early-return.

Tutto è governato da variabili ambiente, quindi riattivabile senza redeploy.
"""

from __future__ import annotations

import os

from core.log import log

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off", ""}


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    v = raw.strip().lower()
    if v in _TRUE:
        return True
    if v in _FALSE:
        return False
    return default


# ── Master switch ──────────────────────────────────────────────────────────────

def passive_mode() -> bool:
    """True (default) = modalità passiva: tutte le automazioni proattive OFF."""
    return _env_bool("GENESI_PASSIVE_MODE", True)


# ── Registro flag proattivi ─────────────────────────────────────────────────────
# nome_logico -> (ENV_VAR principale, default, [alias env], [umbrella che lo spengono])
# Un flag è ON solo se: passive_mode()==False AND env(principale|alias)==true
#                       AND nessun umbrella applicabile è esplicitamente off.

# Umbrella: se l'umbrella è False, anche i figli sono forzati OFF.
_UMBRELLAS = {
    "proactive_messages": "ENABLE_PROACTIVE_MESSAGES",
    "social_autopublish": "ENABLE_SOCIAL_AUTOPUBLISH",
}

# flag_logico -> dict(env, default, aliases, umbrellas)
_FLAGS: dict[str, dict] = {
    # Saluti / messaggi proattivi (umbrella: proactive_messages)
    "morning_greetings":        {"env": "ENABLE_MORNING_GREETINGS",        "default": False, "umbrellas": ["proactive_messages"]},
    "birthday_greetings":       {"env": "ENABLE_BIRTHDAY_GREETINGS",       "default": False, "umbrellas": ["proactive_messages"]},
    "group_interventions":      {"env": "ENABLE_GROUP_INTERVENTIONS",      "default": False, "umbrellas": ["proactive_messages"]},
    "group_auto_presentation":  {"env": "ENABLE_GROUP_AUTO_PRESENTATION",  "default": False, "umbrellas": ["proactive_messages"]},
    "group_greeting_replies":   {"env": "ENABLE_GROUP_GREETING_REPLIES",   "default": False, "umbrellas": ["proactive_messages"]},

    # Social / pubblicazione esterna (umbrella: social_autopublish)
    "instagram_posting":        {"env": "ENABLE_INSTAGRAM_POSTING",        "default": False, "umbrellas": ["social_autopublish"]},
    "instagram_reels":          {"env": "ENABLE_INSTAGRAM_REELS",          "default": False, "umbrellas": ["social_autopublish"]},
    "instagram_comment_replies":{"env": "ENABLE_INSTAGRAM_COMMENT_REPLIES","default": False, "umbrellas": ["social_autopublish"]},
    "facebook_automation":      {"env": "ENABLE_FACEBOOK_AUTOMATION",      "default": False, "umbrellas": ["social_autopublish"]},
    "moltbook_autopublish":     {"env": "ENABLE_MOLTBOOK_AUTOPUBLISH",     "default": False, "umbrellas": ["social_autopublish"],
                                 "aliases": ["ENABLE_MOLTBOK_AUTOPUBLISH", "ENABLE_MULTBOOK_AUTOPUBLISH"]},

    # Interni (non-outbound, disattivati per prudenza/costi)
    "training_autopilot":       {"env": "ENABLE_TRAINING_AUTOPILOT",       "default": False, "umbrellas": []},
    "improvement_health":       {"env": "ENABLE_IMPROVEMENT_HEALTH",       "default": False, "umbrellas": []},

    # Reminder + email proattiva — modalità passiva totale: governati da passive_mode
    "reminders":                {"env": "ENABLE_REMINDERS",                "default": False, "umbrellas": []},
    "proactive_email":          {"env": "ENABLE_PROACTIVE_EMAIL",          "default": False, "umbrellas": ["proactive_messages"]},

    # ── Funzioni su richiesta / innocue: default ON, NON soggette a passive_mode ──
    # calendar_check logga soltanto (nessun outbound); meta_dm_replies è la
    # risposta a chi scrive in DM 1:1 → va tenuta (Genesi risponde se interpellata).
    "calendar_check":           {"env": "ENABLE_CALENDAR_CHECK",           "default": True,  "umbrellas": [], "on_request": True},
    "meta_dm_replies":          {"env": "ENABLE_META_DM_REPLIES",          "default": True,  "umbrellas": [], "on_request": True},
}


def _raw_flag(spec: dict) -> bool:
    """Valore dell'env (principale o alias) senza considerare master/umbrella."""
    if _env_bool(spec["env"], spec["default"]):
        return True
    for alias in spec.get("aliases", []):
        if _env_bool(alias, False):
            return True
    return False


def flag_enabled(name: str) -> bool:
    """
    True se l'automazione ``name`` deve eseguire.

    Regola:
      - flag "on_request": rispetta solo il proprio env (default True), ignora
        passive_mode (sono risposte a chi interpella Genesi).
      - flag proattivi: ON solo se passive_mode()==False AND ogni umbrella
        applicabile è ON AND il flag specifico è ON.
    """
    spec = _FLAGS.get(name)
    if spec is None:
        log("AUTOMATION_FLAG_UNKNOWN", flag=name)
        return False

    if spec.get("on_request"):
        return _raw_flag(spec)

    if passive_mode():
        return False

    for umb in spec.get("umbrellas", []):
        env = _UMBRELLAS[umb]
        if not _env_bool(env, False):
            return False

    return _raw_flag(spec)


def ensure_active(name: str) -> bool:
    """
    Helper per i punti di gate: ritorna flag_enabled e, se False, logga lo skip.
    Uso tipico:
        if not automation_flags.ensure_active("moltbook_autopublish"):
            return
    """
    ok = flag_enabled(name)
    if not ok:
        log("AUTOMATION_SKIPPED", flag=name, passive=passive_mode())
    return ok


def snapshot() -> dict:
    """Stato corrente di tutti i flag (per /health, admin, diagnostica)."""
    return {
        "passive_mode": passive_mode(),
        "flags": {name: flag_enabled(name) for name in _FLAGS},
    }
