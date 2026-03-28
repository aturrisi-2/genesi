"""
ADMIN FACEBOOK API — Genesi
Endpoint per gestire l'integrazione Facebook: modalità, gruppi, post pending, heartbeat.
"""

from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel
from auth.router import require_admin
from auth.models import AuthUser
from core.facebook_service import facebook_service

router = APIRouter(prefix="/admin/facebook", tags=["admin-facebook"])


# ── Models ─────────────────────────────────────────────────────────────────────

class ModePayload(BaseModel):
    mode: str   # "semi" | "full"

class GroupPayload(BaseModel):
    action: str   # "add" | "remove"
    group:  str

class ImportSessionPayload(BaseModel):
    cookies: list   # lista cookie da Cookie-Editor / EditThisCookie

class MentionPayload(BaseModel):
    action:  str   # "add" | "remove"
    mention: str   # nome come appare su Facebook (es. "Alfio Turrisi")


# ── Endpoints ──────────────────────────────────────────────────────────────────

@router.get("/status")
async def fb_status(_: AuthUser = Depends(require_admin)):
    """Stato del servizio: mode, enabled, sessione, pending, statistiche."""
    return await facebook_service.get_status()


@router.get("/pending")
async def fb_pending(_: AuthUser = Depends(require_admin)):
    """Lista dei post in attesa di approvazione."""
    posts = await facebook_service.get_pending_posts()
    return {"pending": posts, "count": len(posts)}


@router.post("/pending/{post_id}/approve")
async def fb_approve(post_id: str, _: AuthUser = Depends(require_admin)):
    """Approva un post pending e lo pubblica su Facebook."""
    result = await facebook_service.approve_pending_post(post_id)
    return result


@router.post("/pending/{post_id}/reject")
async def fb_reject(post_id: str, _: AuthUser = Depends(require_admin)):
    """Rifiuta un post pending (non viene pubblicato)."""
    ok = await facebook_service.reject_pending_post(post_id)
    await facebook_service._record_interaction("post_rejected", post_id=post_id)
    return {"ok": ok}


@router.get("/pending-replies")
async def fb_pending_replies(_: AuthUser = Depends(require_admin)):
    """Lista delle risposte ai commenti in attesa di approvazione."""
    replies = await facebook_service.get_pending_replies()
    return {"replies": replies, "count": len(replies)}


@router.post("/pending-replies/{reply_id}/approve")
async def fb_approve_reply(reply_id: str, _: AuthUser = Depends(require_admin)):
    """Approva e pubblica una risposta a un commento."""
    result = await facebook_service.approve_pending_reply(reply_id)
    return result


@router.post("/pending-replies/{reply_id}/reject")
async def fb_reject_reply(reply_id: str, _: AuthUser = Depends(require_admin)):
    """Rifiuta una risposta (non viene pubblicata)."""
    ok = await facebook_service.reject_pending_reply(reply_id)
    return {"ok": ok}


@router.post("/mode")
async def fb_set_mode(payload: ModePayload, _: AuthUser = Depends(require_admin)):
    """
    Cambia modalità operativa.
    semi  → Genesi propone, admin approva, commenti auto
    full  → Genesi fa tutto in automatico
    """
    ok = await facebook_service.set_mode(payload.mode)
    return {"ok": ok, "mode": payload.mode}


@router.post("/enable")
async def fb_enable(_: AuthUser = Depends(require_admin)):
    """Abilita il servizio Facebook."""
    await facebook_service.set_enabled(True)
    return {"ok": True, "enabled": True}


@router.post("/disable")
async def fb_disable(_: AuthUser = Depends(require_admin)):
    """Disabilita il servizio Facebook."""
    await facebook_service.set_enabled(False)
    return {"ok": True, "enabled": False}


@router.post("/groups")
async def fb_groups(payload: GroupPayload, _: AuthUser = Depends(require_admin)):
    """Aggiungi o rimuovi un gruppo dalla lista di monitoraggio."""
    if payload.action == "add":
        await facebook_service.add_group(payload.group)
    elif payload.action == "remove":
        await facebook_service.remove_group(payload.group)
    else:
        return {"ok": False, "error": "action deve essere 'add' o 'remove'"}
    status = await facebook_service.get_status()
    return {"ok": True, "groups": status["groups"]}


@router.post("/heartbeat")
async def fb_heartbeat(_: AuthUser = Depends(require_admin)):
    """Trigger manuale del ciclo heartbeat."""
    result = await facebook_service.heartbeat()
    return result


@router.get("/feed")
async def fb_feed(group: str = "", _: AuthUser = Depends(require_admin)):
    """
    Legge il feed di un gruppo in tempo reale.
    Se group non specificato usa il primo gruppo configurato.
    """
    status = await facebook_service.get_status()
    if not group:
        groups = status.get("groups", [])
        group = groups[0] if groups else ""
    if not group:
        return {"posts": [], "error": "Nessun gruppo configurato"}

    from core.storage import storage
    cfg = await storage.load("facebook:config", default={})
    if not cfg.get("enabled", False):
        return {"posts": [], "error": "Servizio disabilitato"}

    ok = await facebook_service._ensure_browser()
    if not ok:
        return {"posts": [], "error": "Browser non disponibile"}
    await facebook_service.load_session()
    posts = await facebook_service.read_group_feed(group, max_posts=10)
    return {"posts": posts, "count": len(posts)}


@router.post("/login-start")
async def fb_login_start(_: AuthUser = Depends(require_admin)):
    """
    Avvia il login manuale in browser headful.
    Richiede display sul VPS (Xvfb) o esecuzione locale.
    Per VPS senza display, usa /import-session.
    """
    import asyncio
    asyncio.create_task(facebook_service.manual_login_session())
    return {
        "ok": True,
        "message": "Browser headful avviato. Completa il login su Facebook entro 5 minuti.",
        "note": "Se sei su VPS senza display, usa /admin/facebook/import-session invece."
    }


@router.get("/login-status")
async def fb_login_status(_: AuthUser = Depends(require_admin)):
    """Verifica se la sessione Facebook è attiva."""
    from core.storage import storage
    sess = await storage.load("facebook:session", default={})
    has_session = bool(sess.get("cookies"))
    return {
        "has_session": has_session,
        "saved_at":    sess.get("saved_at"),
        "source":      sess.get("source", "browser"),
    }


@router.post("/mentions")
async def fb_mentions(payload: MentionPayload, _: AuthUser = Depends(require_admin)):
    """
    Gestisce la lista delle menzioni (persone da taggare nei post bacheca).
    Usa il nome completo come appare su Facebook (es. 'Alfio Turrisi').
    """
    from core.storage import storage
    cfg = await storage.load("facebook:config", default={})
    mentions = cfg.get("mentions", [])
    if payload.action == "add" and payload.mention not in mentions:
        mentions.append(payload.mention)
    elif payload.action == "remove":
        mentions = [m for m in mentions if m != payload.mention]
    cfg["mentions"] = mentions
    await storage.save("facebook:config", cfg)
    return {"ok": True, "mentions": mentions}


@router.post("/import-session")
async def fb_import_session(payload: ImportSessionPayload, _: AuthUser = Depends(require_admin)):
    """
    Importa cookies di sessione da JSON esterno.
    Usa estensioni come 'Cookie-Editor' o 'EditThisCookie' per esportare
    i cookie di facebook.com dopo login manuale, poi incollali qui.
    """
    ok = await facebook_service.import_session_from_json(payload.cookies)
    return {"ok": ok, "cookies_imported": len(payload.cookies) if ok else 0}
