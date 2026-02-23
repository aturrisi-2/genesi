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
    
    def create_reminder(self, user_id: str, text: str, reminder_datetime: datetime) -> Optional[str]:
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
                "datetime": reminder_datetime.isoformat(),
                "status": "pending",
                "created_at": now.isoformat()
            }
            
            reminders = self._load_reminders(user_id)
            reminders.append(reminder)
            reminders.sort(key=lambda r: r["datetime"])
            
            if self._save_reminders(user_id, reminders):
                log("REMINDER_CREATE", user_id=user_id, reminder_id=reminder_id, 
                    text=clean_text[:50], datetime=reminder_datetime.isoformat())
                return reminder_id
            
            return None
            
        except Exception as e:
            log("REMINDER_CREATE_ERROR", user_id=user_id, error=str(e))
            return None
    
    def create_reminder_with_response(self, user_id: str, text: str, reminder_datetime: datetime) -> tuple[Optional[str], Optional[str]]:
        """
        Create a new reminder and return response.
        """
        try:
            if not self.validate_datetime_presence(text, reminder_datetime):
                log("REMINDER_VALIDATION_FAILED", user_id=user_id, has_datetime=False, text=text[:50])
                return None, "Non ho capito quando vuoi che ti ricordi."
            
            reminder_id = self.create_reminder(user_id, text, reminder_datetime)
            
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
            cookie_dir = f"memory/icloud_sessions/{user_id}"
            os.makedirs(cookie_dir, exist_ok=True)
            
            return ICloudService(
                username=icloud_user,
                password=icloud_pass,
                cookie_directory=cookie_dir
            )
        except Exception as e:
            log("ICLOUD_SERVICE_GET_ERROR", user_id=user_id, error=str(e))
            return None

    async def fetch_icloud_reminders(self, user_id: str, list_name: str = "Promemoria") -> List[Dict[str, Any]]:
        """
        Fetch reminders from iCloud and MERGE them into local storage.
        Returns only the newly added reminders.
        """
        svc = await self._get_icloud_service(user_id)
        if not svc:
            return []
        
        try:
            icloud_data = svc.get_reminders(list_name)
            if not icloud_data:
                return []

            # Carichiamo i locali per il merge
            local_reminders = self._load_reminders(user_id)
            existing_guids = {r.get("id") for r in local_reminders}
            
            new_added = []
            for item in icloud_data:
                # Creiamo un ID stabile per iCloud usando il GUID
                guid = item.get('guid')
                reminder_id = f"icloud_{guid}" if guid else f"icloud_{uuid.uuid4()}"
                
                if reminder_id not in existing_guids:
                    new_item = {
                        "id": reminder_id,
                        "text": item.get('summary', 'Senza titolo'),
                        "datetime": item.get('due'), # Nessun fallback a 'now', altrimenti suonano subito
                        "status": "pending",
                        "source": "icloud",
                        "list": item.get('list', 'iCloud')
                    }
                    local_reminders.append(new_item)
                    new_added.append(new_item)
            
            if new_added:
                self._save_reminders(user_id, local_reminders)
                log("REMINDER_ICLOUD_MERGED", user_id=user_id, new_count=len(new_added))
            
            return new_added
            
        except Exception as e:
            log("ICLOUD_FETCH_ERROR", user_id=user_id, error=str(e))
            return []

    async def list_reminders(self, user_id: str, status_filter: Optional[str] = None, include_icloud: bool = False) -> List[Dict[str, Any]]:
        """
        List reminders for a user. 
        include_icloud=False di default per evitare congestione durante il polling.
        """
        try:
            # Se richiesto iCloud, facciamo il fetch reale
            if include_icloud:
                await self.fetch_icloud_reminders(user_id)

            # Leggiamo sempre dal file locale (che ora contiene anche quelli di iCloud syncati)
            reminders = self._load_reminders(user_id)
            
            if status_filter:
                reminders = [r for r in reminders if r.get("status") == status_filter]
            
            # Sort per data
            reminders.sort(key=lambda r: r.get("datetime") or "")
            
            log("REMINDER_LIST", user_id=user_id, count=len(reminders), status_filter=status_filter)
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
                    if (reminder.get("status") == "pending" and rem_date and
                        datetime.fromisoformat(rem_date) <= now):
                        reminder_copy = reminder.copy()
                        reminder_copy["user_id"] = user_id
                        due_reminders.append(reminder_copy)
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
                    dt = datetime.fromisoformat(dt_iso)
                    date_str = dt.strftime("%d %b %H:%M") + " – "
                text = reminder["text"]
                status = reminder.get("status", "pending")
                source = reminder.get("source", "local")
                source_tag = " (iCloud)" if source == "icloud" else ""
                status_icon = "✅" if status == "done" else "⏰" if status == "pending" else "🔔" if status == "triggered" else "❌"
                lines.append(f"{i}. {date_str}{text}{source_tag} {status_icon}")
            except: continue
        return "\n".join(lines)


# Global instance
reminder_engine = ReminderEngine()
