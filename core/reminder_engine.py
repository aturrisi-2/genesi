"""
REMINDER ENGINE - Genesi Core
Complete reminder system with scheduling and user isolation.
"""

import json
import uuid
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path
from core.log import log
from core.storage import storage
import asyncio


class ReminderEngine:
    """
    Reminder engine for scheduling and managing user reminders.
    Storage: data/reminders/{user_id}.json
    """
    
    def __init__(self):
        self.reminders_dir = Path("data/reminders")
        self.reminders_dir.mkdir(parents=True, exist_ok=True)
        log("REMINDER_ENGINE_ACTIVE", storage_dir=str(self.reminders_dir))
    
    def _get_reminders_file(self, user_id: str) -> Path:
        """Get the reminders file path for a user."""
        return self.reminders_dir / f"{user_id}.json"
    
    def _load_reminders(self, user_id: str) -> List[Dict[str, Any]]:
        """Load reminders for a user from storage."""
        try:
            file_path = self._get_reminders_file(user_id)
            if not file_path.exists():
                return []
            
            with open(file_path, 'r', encoding='utf-8') as f:
                reminders = json.load(f)
            
            if reminders:
                log("REMINDER_LOAD", user_id=user_id, count=len(reminders), level="DEBUG")
            return reminders
            
        except Exception as e:
            log("REMINDER_LOAD_ERROR", user_id=user_id, error=str(e))
            # Resilience: if file is corrupted, move it to avoid persistent crash
            try:
                file_path = self._get_reminders_file(user_id)
                if file_path.exists():
                    bak_path = file_path.with_suffix(".json.bak")
                    file_path.rename(bak_path)
                    log("REMINDER_FILE_CORRUPTED_MV", path=str(bak_path))
            except: pass
            return []
    
    def _save_reminders(self, user_id: str, reminders: List[Dict[str, Any]]) -> bool:
        """Save reminders for a user to storage."""
        try:
            file_path = self._get_reminders_file(user_id)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(reminders, f, indent=2, ensure_ascii=False)
            
            log("REMINDER_SAVE", user_id=user_id, count=len(reminders))
            return True
            
        except Exception as e:
            log("REMINDER_SAVE_ERROR", user_id=user_id, error=str(e))
            return False
    
    def create_reminder(self, user_id: str, text: str, reminder_datetime: datetime, source: str = "local") -> Optional[str]:
        """
        Create a new reminder for a user.
        """
        try:
            reminder_id = str(uuid.uuid4())
            now = datetime.now()
            
            from core.tts_sanitizer import strip_emojis
            clean_text = strip_emojis(text)
            
            reminder = {
                "id": reminder_id,
                "text": clean_text,
                "datetime": reminder_datetime.isoformat() if reminder_datetime else None,
                "status": "pending",
                "source": source,
                "created_at": now.isoformat()
            }
            
            reminders = self._load_reminders(user_id)
            reminders.append(reminder)
            # Handle None datetimes by putting them at the end
            reminders.sort(key=lambda r: (r.get("datetime") is None, r.get("datetime")))
            
            if self._save_reminders(user_id, reminders):
                log("REMINDER_CREATE", user_id=user_id, reminder_id=reminder_id, 
                    text=clean_text[:50], datetime=reminder_datetime.isoformat() if reminder_datetime else None)
                return reminder_id
            
            return None
            
        except Exception as e:
            log("REMINDER_CREATE_ERROR", user_id=user_id, error=str(e))
            return None
    
    def create_reminder_with_response(self, user_id: str, text: str, reminder_datetime: datetime, source: str = "local") -> tuple[Optional[str], Optional[str]]:
        """
        Create a new reminder and return response.
        """
        try:
            if not self.validate_datetime_presence(text, reminder_datetime):
                log("REMINDER_VALIDATION_FAILED", user_id=user_id, has_datetime=False, text=text[:50])
                return None, "Non ho capito quando vuoi che ti ricordi."
            
            reminder_id = self.create_reminder(user_id, text, reminder_datetime, source=source)
            
            if reminder_id:
                date_str = reminder_datetime.strftime("%d %b %H:%M")
                response = f"Perfetto. Ti ricorderò di {text} il {date_str}."
                log("REMINDER_VALIDATION", user_id=user_id, has_datetime=True, reminder_id=reminder_id)
                return reminder_id, response
            
            return None, "Errore nella creazione."
            
        except Exception as e:
            log("REMINDER_CREATE_ERROR", user_id=user_id, error=str(e))
            return None, "Errore di sistema."
    
    def validate_datetime_presence(self, text: str, parsed_datetime: Optional[datetime]) -> bool:
        if parsed_datetime is None:
            return False
        now = datetime.now()
        if parsed_datetime <= now + timedelta(minutes=1):
            return False
        return True

    async def _get_icloud_service(self, user_id: str):
        """Get an authenticated ICloudService for the user."""
        try:
            profile = await storage.load(f"profile:{user_id}", default={})
            icloud_user = profile.get("icloud_user")
            icloud_pass = profile.get("icloud_password")
            
            if not icloud_user or not icloud_pass:
                return None
            
            from core.icloud_service import ICloudService
            return ICloudService(
                username=icloud_user,
                password=icloud_pass
            )
        except Exception as e:
            log("ICLOUD_SERVICE_GET_ERROR", user_id=user_id, error=str(e))
            return None

    async def create_icloud_reminder(self, user_id: str, text: str, due_dt: datetime) -> bool:
        """Pushes a new reminder to iCloud using VTODO."""
        try:
            profile = await storage.load(f"profile:{user_id}", default={})
            icloud_user = profile.get("icloud_user")
            icloud_pass = profile.get("icloud_password")
            
            # Fallback to env ONLY for Admin
            if not icloud_user or not icloud_pass:
                from auth.config import ADMIN_EMAILS
                is_admin = profile.get("email") in ADMIN_EMAILS or user_id in ADMIN_EMAILS # Check both for safety
                if is_admin:
                    icloud_user = os.environ.get("ICLOUD_USER")
                    icloud_pass = os.environ.get("ICLOUD_PASSWORD") or os.environ.get("ICLOUD_PASS")
            
            if not icloud_user or not icloud_pass:
                return False
                
            from core.icloud_reminder_creator import ICloudReminderCreator
            creator = ICloudReminderCreator(user=icloud_user, password=icloud_pass)
            return await creator.create_reminder(text, due_dt)
        except Exception as e:
            log("ICLOUD_REMINDER_ENGINE_ERROR", error=str(e), user_id=user_id)
            return False

    async def fetch_icloud_reminders(self, user_id: str, list_name: str = "Promemoria", force: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch reminders from iCloud (VTODO + VEVENT) and MERGE them into local storage.
        """
        profile = await storage.load(f"profile:{user_id}", default={})
        last_sync = profile.get("last_icloud_sync")
        now_ts = datetime.now().timestamp()
        
        if not force and last_sync and (now_ts - last_sync < 30):
            return []

        svc = await self._get_icloud_service(user_id)
        if not svc: return []
        
        try:
            # Sincronizzazione cumulativa (VTODO + VEVENT)
            icloud_data = svc.get_all_items()
            profile["last_icloud_sync"] = now_ts
            await storage.save(f"profile:{user_id}", profile)
            
            if not icloud_data: return []

            local_reminders = self._load_reminders(user_id)
            new_added = []
            updates_count = 0
            
            # Mappa per accesso rapido
            local_map = {r.get("id"): i for i, r in enumerate(local_reminders)}
            
            for item in icloud_data:
                guid = item.get('guid')
                reminder_id = f"icloud_{guid}" if guid else None
                if not reminder_id: continue
                
                status_val = item.get('status', 'pending')
                # Mappatura stati Apple -> Genesi
                if status_val in ['COMPLETED', 'CANCELLED']:
                    local_status = 'completed'
                else:
                    local_status = 'pending'

                new_data = {
                    "id": reminder_id,
                    "text": item.get('summary', 'Senza titolo'),
                    "datetime": item.get('due'),
                    "status": local_status,
                    "source": "icloud",
                    "list": item.get('list', 'iCloud')
                }
                
                if reminder_id in local_map:
                    # Aggiorna se diverso
                    idx = local_map[reminder_id]
                    old_item = local_reminders[idx]
                    if old_item.get("status") != local_status or old_item.get("text") != new_data["text"]:
                        local_reminders[idx].update(new_data)
                        updates_count += 1
                else:
                    local_reminders.append(new_data)
                    new_added.append(new_data)
            
            if new_added or updates_count > 0:
                local_reminders.sort(key=lambda r: (r.get("status") == "completed", r.get("datetime") is None, r.get("datetime") or ""))
                self._save_reminders(user_id, local_reminders)
                log("REMINDER_ICLOUD_SYNC_RES", user_id=user_id, added=len(new_added), updated=updates_count)
            
            return new_added
        except Exception as e:
            log("ICLOUD_FETCH_ERROR", user_id=user_id, error=str(e))
            return []

    async def list_reminders(self, user_id: str, status_filter: Optional[str] = None, include_icloud: bool = True) -> List[Dict[str, Any]]:
        """
        List unified reminders: Local + iCloud + Google.
        """
        try:
            # Load from local (includes iCloud synced items)
            reminders = self._load_reminders(user_id)
            
            # 1. Fetch iCloud/Google ONLY if user is Admin or has credentials
            # This prevents common users from seeing Admin's calendars defined in .env
            from auth.config import ADMIN_EMAILS
            # Get email from profile to check admin status
            profile = await storage.load(f"profile:{user_id}", default={})
            user_email = profile.get("email", "")
            
            # Debug: log the identifies being used
            is_admin = user_email in ADMIN_EMAILS
            has_own_creds = bool(profile.get("icloud_user") or profile.get("google_token"))

            unified_items = []
            if include_icloud and (is_admin or has_own_creds):
                try:
                    from calendar_manager import calendar_manager
                    # Se l'utente ha credenziali proprie, dovremmo idealmente usare un'istanza dedicata.
                    # Per ora, se è Admin usa quella globale (che ha i dati in .env)
                    if is_admin:
                        await asyncio.to_thread(calendar_manager.list_reminders)
                        unified_items = calendar_manager.list_reminders(days=7)
                except Exception as e:
                    log("REMINDER_SYNC_SKIP", user_id=user_id, reason=str(e))
            
            # 4. Merge Google items (only if relevant to filter)
            if not status_filter or status_filter == "pending":
                # Deduplication hashes
                existing_hashes = {f"{r['text'].lower()}_{r.get('datetime')}" for r in reminders if r.get('text')}
                
                for gi in unified_items:
                    summary = gi.get('summary')
                    due = gi.get('due')
                    provider = gi.get('provider', 'unified')
                    item_hash = f"{summary.lower()}_{due}"
                    if item_hash not in existing_hashes:
                        reminders.append({
                            "id": f"{provider}_{hash(summary)}_{due}",
                            "text": summary,
                            "datetime": due,
                            "source": provider,
                            "status": "pending"
                        })
                        existing_hashes.add(item_hash)

            # 5. Apply Status Filter to the final list
            if status_filter:
                reminders = [r for r in reminders if r.get("status") == status_filter]
                
            reminders.sort(key=lambda r: (r.get("datetime") is None, r.get("datetime") or ""))
            log("REMINDER_LIST_UNIFIED", user_id=user_id, count=len(reminders), filter=status_filter, is_admin=is_admin)
            return reminders
            
        except Exception as e:
            log("REMINDER_LIST_ERROR", user_id=user_id, error=str(e))
            return []

    def get_due_reminders(self) -> List[Dict[str, Any]]:
        try:
            now = datetime.now()
            due_reminders = []
            for file_path in self.reminders_dir.glob("*.json"):
                user_id = file_path.stem
                reminders = self._load_reminders(user_id)
                for reminder in reminders:
                    rem_date = reminder.get("datetime")
                    if reminder.get("status") == "pending" and rem_date:
                        try:
                            rem_dt = datetime.fromisoformat(rem_date)
                            # Handle offset-naive vs offset-aware comparison
                            if rem_dt.tzinfo is not None:
                                current_now = datetime.now(rem_dt.tzinfo)
                            else:
                                current_now = now
                                
                            if rem_dt <= current_now:
                                reminder_copy = reminder.copy()
                                reminder_copy["user_id"] = user_id
                                due_reminders.append(reminder_copy)
                        except Exception as parse_err:
                            log("REMINDER_DATE_PARSE_ERROR", error=str(parse_err), date=rem_date)
                            continue

            return due_reminders
        except Exception as e:
            log("REMINDER_DUE_ERROR", error=str(e))
            return []
    
    def mark_reminder_done(self, user_id: str, reminder_id: str) -> bool:
        try:
            reminders = self._load_reminders(user_id)
            for reminder in reminders:
                if reminder.get("id") == reminder_id:
                    reminder["status"] = "done"
                    reminder["done_at"] = datetime.now().isoformat()
                    return self._save_reminders(user_id, reminders)
            return False
        except Exception as e:
            log("REMINDER_DONE_ERROR", user_id=user_id, error=str(e))
            return False

    def delete_reminder(self, user_id: str, reminder_id: str) -> bool:
        try:
            reminders = self._load_reminders(user_id)
            updated = [r for r in reminders if r.get("id") != reminder_id]
            if len(updated) != len(reminders):
                return self._save_reminders(user_id, updated)
            return False
        except Exception as e:
            log("REMINDER_DELETE_ERROR", user_id=user_id, error=str(e))
            return False

    def delete_all_pending(self, user_id: str) -> int:
        try:
            reminders = self._load_reminders(user_id)
            updated = [r for r in reminders if r.get("status") != "pending"]
            deleted_count = len(reminders) - len(updated)
            if deleted_count > 0:
                self._save_reminders(user_id, updated)
            return deleted_count
        except Exception as e:
            log("REMINDER_DELETE_ALL_ERROR", user_id=user_id, error=str(e))
            return 0

    def get_latest_pending(self, user_id: str) -> Optional[Dict[str, Any]]:
        try:
            reminders = self._load_reminders(user_id)
            pending = [r for r in reminders if r.get("status") == "pending"]
            pending.sort(key=lambda r: r["datetime"], reverse=True)
            return pending[0] if pending else None
        except Exception as e:
            log("REMINDER_GET_LATEST_ERROR", user_id=user_id, error=str(e))
            return None

    def mark_reminder_triggered(self, user_id: str, reminder_id: str) -> bool:
        try:
            reminders = self._load_reminders(user_id)
            for reminder in reminders:
                if reminder.get("id") == reminder_id:
                    reminder["status"] = "triggered"
                    reminder["triggered_at"] = datetime.now().isoformat()
                    if self._save_reminders(user_id, reminders):
                        try:
                            from api.push import send_push_notification
                            send_push_notification(user_id, "⏰ Promemoria Genesi", reminder["text"])
                        except: pass
                        return True
            return False
        except Exception as e:
            log("REMINDER_TRIGGERED_ERROR", user_id=user_id, error=str(e))
            return False

    def format_reminders_list(self, reminders: List[Dict[str, Any]]) -> str:
        if not reminders:
            return "Non hai promemoria impostati."
        lines = ["I tuoi promemoria:"]
        for i, reminder in enumerate(reminders, 1):
            try:
                dt_iso = reminder.get("datetime")
                date_str = ""
                if dt_iso:
                    # ISO Format resilience
                    clean_dt = dt_iso.replace("Z", "+00:00").split(".")[0] if "T" in dt_iso else dt_iso
                    try:
                        dt = datetime.fromisoformat(clean_dt)
                        date_str = dt.strftime("%d %b %H:%M") + " – "
                    except:
                        date_str = f"({dt_iso}) – "
                
                text = reminder.get("text", "Senza titolo")
                status = reminder.get("status", "pending")
                source = str(reminder.get("source", "local")).lower()
                
                # Source Labeling
                source_tag = ""
                if source == "icloud" or source == "apple":
                    source_tag = " (iCloud)"
                elif source == "google":
                    source_tag = " (Google)"
                else:
                    source_tag = " (Genesi)"
                
                status_icon = "✅" if status == "done" else "⏰" if status == "pending" else "🔔" if status == "triggered" else "❌"
                lines.append(f"{i}. {date_str}{text}{source_tag} {status_icon}")
            except: continue
        return "\n".join(lines)


# Global instance
reminder_engine = ReminderEngine()
