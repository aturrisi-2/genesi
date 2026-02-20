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
                "updated_at": c.get("updated_at"),
                "message_count": len(messages)
            })
        except: pass
    return {"conversations": convs}

@router.post("/conversations")
async def create_conversation(current_user: AuthUser = Depends(require_auth)):
    user_id = str(current_user.id)
    conv = {"id": str(uuid.uuid4()), "title": "Nuova chat", "messages": [], "created_at": datetime.now().isoformat(), "updated_at": datetime.now().isoformat()}
    _save_conv(user_id, conv)
    log("CONVERSATION_CREATE", user_id=user_id, conv_id=conv["id"])
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

@router.post("/conversations/{conv_id}/messages")
async def append_message(conv_id: str, body: dict, current_user: AuthUser = Depends(require_auth)):
    """Aggiunge un messaggio a una conversazione esistente."""
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
    return {"status": "ok"}
