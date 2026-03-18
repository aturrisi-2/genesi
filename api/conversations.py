"""
Conversations API — salvataggio e gestione chat history per utente.
Storage: data/conversations/{user_id}/{conversation_id}.json
"""
from fastapi import APIRouter, Depends
from auth.router import require_auth
from auth.models import AuthUser
from core.log import log
import json, uuid
from datetime import datetime
from pathlib import Path

router = APIRouter()
CONV_DIR = Path("data/conversations")
CONV_DIR.mkdir(parents=True, exist_ok=True)

def _user_dir(user_id: str) -> Path:
    p = CONV_DIR / user_id
    p.mkdir(parents=True, exist_ok=True)
    return p

def _load_conv(user_id: str, conv_id: str) -> dict | None:
    path = _user_dir(user_id) / f"{conv_id}.json"
    if not path.exists(): return None
    return json.loads(path.read_text())

def _save_conv(user_id: str, conv: dict):
    path = _user_dir(user_id) / f"{conv['id']}.json"
    path.write_text(json.dumps(conv, indent=2, ensure_ascii=False))

@router.get("/conversations")
async def list_conversations(current_user: AuthUser = Depends(require_auth)):
    user_id = str(current_user.id)
    convs = []
    for f in sorted((_user_dir(user_id)).glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True):
        try:
            c = json.loads(f.read_text())
            messages = c.get("messages", [])
            convs.append({
                "id": c["id"],
                "title": c.get("title", "Nuova chat"),
                "conv_type": c.get("conv_type", "chat"),
                "pinned": c.get("pinned", False),
                "updated_at": c.get("updated_at"),
                "message_count": len(messages),
                "messages": messages  # <-- aggiunto per frontend
            })
        except: pass
    return {"conversations": convs}

@router.post("/conversations")
async def create_conversation(body: dict = None, current_user: AuthUser = Depends(require_auth)):
    user_id = str(current_user.id)
    conv_type = (body or {}).get("conv_type", "chat")
    if conv_type not in ("chat", "coding"):
        conv_type = "chat"
    conv = {"id": str(uuid.uuid4()), "title": "Nuova chat", "conv_type": conv_type, "messages": [], "pinned": False, "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat()}
    _save_conv(user_id, conv)
    log("CONVERSATION_CREATE", user_id=user_id, conv_id=conv["id"], conv_type=conv_type)
    return conv

@router.delete("/conversations/empty")
async def delete_empty_conversations(current_user = Depends(require_auth)):
    user_dir = Path(CONV_DIR) / current_user.id
    if not user_dir.exists():
        return {"deleted": 0}
    deleted = 0
    for f in user_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text())
            if not data.get("messages") or len(data["messages"]) == 0:
                f.unlink()
                deleted += 1
        except:
            pass
    log("CONVERSATIONS_CLEAN_EMPTY", user_id=current_user.id, deleted=deleted)
    return {"deleted": deleted}

@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: str, current_user: AuthUser = Depends(require_auth)):
    user_id = str(current_user.id)
    conv = _load_conv(user_id, conv_id)
    if not conv: return {"error": "not found"}, 404
    return conv

@router.patch("/conversations/{conv_id}")
async def rename_conversation(conv_id: str, body: dict, current_user: AuthUser = Depends(require_auth)):
    user_id = str(current_user.id)
    conv = _load_conv(user_id, conv_id)
    if not conv: return {"error": "not found"}
    conv["title"] = body.get("title", conv["title"])[:60]
    if "conv_type" in body and body["conv_type"] in ("chat", "coding"):
        conv["conv_type"] = body["conv_type"]
    conv["updated_at"] = datetime.now().isoformat()
    _save_conv(user_id, conv)
    log("CONVERSATION_RENAME", user_id=user_id, conv_id=conv_id)
    return {"status": "ok"}

@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str, current_user: AuthUser = Depends(require_auth)):
    user_id = str(current_user.id)
    path = _user_dir(user_id) / f"{conv_id}.json"
    if path.exists(): path.unlink()
    log("CONVERSATION_DELETE", user_id=user_id, conv_id=conv_id)
    return {"status": "ok"}

@router.delete("/conversations")
async def delete_all_conversations(current_user: AuthUser = Depends(require_auth)):
    user_id = str(current_user.id)
    user_dir = Path(CONV_DIR) / user_id
    if not user_dir.exists():
        return {"deleted": 0}
    deleted = 0
    for f in user_dir.glob("*.json"):
        try:
            f.unlink()
            deleted += 1
        except:
            pass
    log("CONVERSATIONS_DELETE_ALL", user_id=user_id, deleted=deleted)
    return {"status": "ok", "deleted": deleted}

@router.patch("/conversations/{conv_id}/pin")
async def toggle_pin_conversation(conv_id: str, body: dict, current_user: AuthUser = Depends(require_auth)):
    user_id = str(current_user.id)
    conv = _load_conv(user_id, conv_id)
    if not conv: return {"error": "not found"}
    conv["pinned"] = body.get("pinned", False)
    conv["updated_at"] = datetime.now().isoformat()
    _save_conv(user_id, conv)
    log("CONVERSATION_PIN_TOGGLE", user_id=user_id, conv_id=conv_id, pinned=conv["pinned"])
    return {"status": "ok", "pinned": conv["pinned"]}

@router.post("/conversations/{conv_id}/messages")
async def append_message(conv_id: str, body: dict, current_user: AuthUser = Depends(require_auth)):
    """Aggiunge un messaggio a una conversazione esistente."""
    import asyncio
    user_id = str(current_user.id)
    conv = _load_conv(user_id, conv_id)
    if not conv: return {"error": "not found"}
    conv["messages"].append({"role": body["role"], "content": body["content"], "ts": datetime.now().isoformat()})
    conv["updated_at"] = datetime.now().isoformat()
    # Auto-titolo: usa il primo messaggio utente se il titolo è ancora default
    if conv["title"] == "Nuova chat":
        first_user = next((m for m in conv["messages"] if m["role"] == "user"), None)
        if first_user:
            conv["title"] = first_user["content"][:50]
    _save_conv(user_id, conv)
    # Background: aggiorna sommario conversazione ogni 3 messaggi (>=2 totali)
    msg_count = len(conv["messages"])
    if msg_count >= 2 and msg_count % 3 == 0:
        try:
            from core.conversation_summary_service import conv_summary_service
            asyncio.create_task(conv_summary_service.record_summary(
                user_id, conv_id, conv.get("title", ""), conv["messages"]
            ))
        except Exception:
            pass
    return {"status": "ok"}
