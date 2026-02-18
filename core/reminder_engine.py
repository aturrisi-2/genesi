"""
REMINDER ENGINE - Genesi Core
Complete reminder system with scheduling and user isolation.
"""

import json
import uuid
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
                log("REMINDER_LOAD", user_id=user_id, count=len(reminders))
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
        
        Args:
            user_id: User identifier
            text: Reminder text
            reminder_datetime: When to remind
            
        Returns:
            Reminder ID if successful, None otherwise
        """
        try:
            reminder_id = str(uuid.uuid4())
            now = datetime.now()
            
            # Strip emojis from reminder text before saving
            from core.tts_sanitizer import strip_emojis
            clean_text = strip_emojis(text)
            
            reminder = {
                "id": reminder_id,
                "text": clean_text,
                "datetime": reminder_datetime.isoformat(),
                "status": "pending",  # pending, done, cancelled, triggered
                "created_at": now.isoformat()
            }
            
            reminders = self._load_reminders(user_id)
            reminders.append(reminder)
            
            # Sort by datetime
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
        Create a new reminder for a user and return response message.
        APPLICA VALIDAZIONE DATETIME PRESENCE.
        
        Args:
            user_id: User identifier
            text: Reminder text
            reminder_datetime: When to remind
            
        Returns:
            Tuple of (reminder_id, response_message) if successful, (None, error_message) otherwise
        """
        try:
            # VALIDAZIONE DATETIME PRESENCE
            if not self.validate_datetime_presence(text, reminder_datetime):
                log("REMINDER_VALIDATION_FAILED", user_id=user_id, has_datetime=False, text=text[:50])
                return None, "Non ho capito quando vuoi che ti ricordi."
            
            reminder_id = self.create_reminder(user_id, text, reminder_datetime)
            
            if reminder_id:
                # Format confirmation message
                date_str = reminder_datetime.strftime("%d %b %H:%M")
                response = f"Perfetto. Ti ricorderò di {text} il {date_str}."
                log("REMINDER_VALIDATION", user_id=user_id, has_datetime=True, reminder_id=reminder_id)
                return reminder_id, response
            
            return None
            
        except Exception as e:
            log("REMINDER_CREATE_ERROR", user_id=user_id, error=str(e))
            return None
    
    def validate_datetime_presence(self, text: str, parsed_datetime: Optional[datetime]) -> bool:
        """
        Valida presenza effettiva di data/orario nel reminder.
        Blocca creazione se parsed_datetime è None.
        
        Args:
            text: Testo del reminder
            parsed_datetime: DateTime parsato dal sistema
            
        Returns:
            True se datetime valido, False altrimenti
        """
        if parsed_datetime is None:
            return False
        
        # Verifica che la datetime sia nel futuro (almeno 1 minuto)
        now = datetime.now()
        if parsed_datetime <= now + timedelta(minutes=1):
            return False
        
        return True
    
    def list_reminders(self, user_id: str, status_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List reminders for a user, optionally filtered by status.
        
        Args:
            user_id: User identifier
            status_filter: Optional status filter ('pending', 'done', 'cancelled')
            
        Returns:
            List of reminders sorted chronologically
        """
        try:
            reminders = self._load_reminders(user_id)
            
            if status_filter:
                reminders = [r for r in reminders if r.get("status") == status_filter]
            
            # Sort by datetime (chronological order)
            reminders.sort(key=lambda r: r["datetime"])
            
            log("REMINDER_LIST", user_id=user_id, count=len(reminders), status_filter=status_filter)
            return reminders
            
        except Exception as e:
            log("REMINDER_LIST_ERROR", user_id=user_id, error=str(e))
            return []
    
    def get_due_reminders(self) -> List[Dict[str, Any]]:
        """
        Get all reminders that are due (datetime <= now and status = pending).
        
        Returns:
            List of due reminders with user_id included
        """
        try:
            now = datetime.now()
            due_reminders = []
            
            # Iterate through all reminder files
            for file_path in self.reminders_dir.glob("*.json"):
                user_id = file_path.stem
                reminders = self._load_reminders(user_id)
                
                for reminder in reminders:
                    if (reminder.get("status") == "pending" and 
                        datetime.fromisoformat(reminder["datetime"]) <= now):
                        
                        # Add user_id to reminder for processing
                        reminder_copy = reminder.copy()
                        reminder_copy["user_id"] = user_id
                        due_reminders.append(reminder_copy)
            
            if due_reminders:
                log("REMINDER_DUE_CHECK", total_due=len(due_reminders))
            return due_reminders
            
        except Exception as e:
            log("REMINDER_DUE_ERROR", error=str(e))
            return []
    
    def mark_reminder_done(self, user_id: str, reminder_id: str) -> bool:
        """
        Mark a reminder as done.
        
        Args:
            user_id: User identifier
            reminder_id: Reminder ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            reminders = self._load_reminders(user_id)
            
            for reminder in reminders:
                if reminder.get("id") == reminder_id:
                    reminder["status"] = "done"
                    reminder["done_at"] = datetime.now().isoformat()
                    
                    if self._save_reminders(user_id, reminders):
                        log("REMINDER_DONE", user_id=user_id, reminder_id=reminder_id)
                        return True
                    return False
            
            log("REMINDER_DONE_NOT_FOUND", user_id=user_id, reminder_id=reminder_id)
            return False
            
        except Exception as e:
            log("REMINDER_DONE_ERROR", user_id=user_id, reminder_id=reminder_id, error=str(e))
            return False
    
    def cancel_reminder(self, user_id: str, reminder_id: str) -> bool:
        """
        Cancel a reminder.
        
        Args:
            user_id: User identifier
            reminder_id: Reminder ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            reminders = self._load_reminders(user_id)
            
            for reminder in reminders:
                if reminder.get("id") == reminder_id:
                    reminder["status"] = "cancelled"
                    reminder["cancelled_at"] = datetime.now().isoformat()
                    
                    if self._save_reminders(user_id, reminders):
                        log("REMINDER_CANCEL", user_id=user_id, reminder_id=reminder_id)
                        return True
                    return False
            
            log("REMINDER_CANCEL_NOT_FOUND", user_id=user_id, reminder_id=reminder_id)
            return False
            
        except Exception as e:
            log("REMINDER_CANCEL_ERROR", user_id=user_id, reminder_id=reminder_id, error=str(e))
            return False
    
    def delete_reminder(self, user_id: str, reminder_id: str) -> bool:
        """
        Delete a reminder completely.
        
        Args:
            user_id: User identifier
            reminder_id: Reminder ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            reminders = self._load_reminders(user_id)
            
            # Filter out the reminder to delete
            updated_reminders = [r for r in reminders if r.get("id") != reminder_id]
            
            if len(updated_reminders) != len(reminders):
                if self._save_reminders(user_id, updated_reminders):
                    log("REMINDER_DELETE", user_id=user_id, reminder_id=reminder_id)
                    return True
            
            log("REMINDER_DELETE_NOT_FOUND", user_id=user_id, reminder_id=reminder_id)
            return False
            
        except Exception as e:
            log("REMINDER_DELETE_ERROR", user_id=user_id, reminder_id=reminder_id, error=str(e))
            return False
    
    def delete_all_pending(self, user_id: str) -> int:
        """
        Delete all pending reminders for a user.
        
        Args:
            user_id: User identifier
            
        Returns:
            Number of deleted reminders
        """
        try:
            reminders = self._load_reminders(user_id)
            
            # Filter to keep only non-pending reminders
            updated_reminders = [r for r in reminders if r.get("status") != "pending"]
            deleted_count = len(reminders) - len(updated_reminders)
            
            if deleted_count > 0:
                if self._save_reminders(user_id, updated_reminders):
                    log("REMINDER_DELETE_ALL", user_id=user_id, count=deleted_count)
                    return deleted_count
            
            return 0
            
        except Exception as e:
            log("REMINDER_DELETE_ALL_ERROR", user_id=user_id, error=str(e))
            return 0
    
    def get_latest_pending(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent pending reminder.
        
        Args:
            user_id: User identifier
            
        Returns:
            Latest pending reminder or None
        """
        try:
            reminders = self._load_reminders(user_id)
            
            # Filter pending reminders and sort by datetime (most recent first)
            pending_reminders = [r for r in reminders if r.get("status") == "pending"]
            pending_reminders.sort(key=lambda r: r["datetime"], reverse=True)
            
            return pending_reminders[0] if pending_reminders else None
            
        except Exception as e:
            log("REMINDER_GET_LATEST_ERROR", user_id=user_id, error=str(e))
            return None
    
    def update_reminder_datetime(self, user_id: str, reminder_id: str, new_datetime: datetime) -> bool:
        """
        Update the datetime of an existing reminder.
        
        Args:
            user_id: User identifier
            reminder_id: Reminder ID
            new_datetime: New reminder datetime
            
        Returns:
            True if successful, False otherwise
        """
        try:
            reminders = self._load_reminders(user_id)
            
            for reminder in reminders:
                if reminder.get("id") == reminder_id:
                    reminder["datetime"] = new_datetime.isoformat()
                    reminder["updated_at"] = datetime.now().isoformat()
                    
                    # Re-sort by datetime
                    reminders.sort(key=lambda r: r["datetime"])
                    
                    if self._save_reminders(user_id, reminders):
                        log("REMINDER_UPDATE", user_id=user_id, reminder_id=reminder_id, 
                            datetime=new_datetime.isoformat())
                        return True
                    return False
            
            log("REMINDER_UPDATE_NOT_FOUND", user_id=user_id, reminder_id=reminder_id)
            return False
            
        except Exception as e:
            log("REMINDER_UPDATE_ERROR", user_id=user_id, reminder_id=reminder_id, error=str(e))
            return False
    
    def mark_reminder_triggered(self, user_id: str, reminder_id: str) -> bool:
        """
        Mark a reminder as triggered (alarm activated).
        
        Args:
            user_id: User identifier
            reminder_id: Reminder ID
            
        Returns:
            True if successful, False otherwise
        """
        try:
            reminders = self._load_reminders(user_id)
            
            for reminder in reminders:
                if reminder.get("id") == reminder_id:
                    reminder["status"] = "triggered"
                    reminder["triggered_at"] = datetime.now().isoformat()
                    
                    if self._save_reminders(user_id, reminders):
                        log("REMINDER_TRIGGERED", user_id=user_id, reminder_id=reminder_id)
                        return True
                    return False
            
            log("REMINDER_TRIGGERED_NOT_FOUND", user_id=user_id, reminder_id=reminder_id)
            return False
            
        except Exception as e:
            log("REMINDER_TRIGGERED_ERROR", user_id=user_id, reminder_id=reminder_id, error=str(e))
            return False
    
    def format_reminders_list(self, reminders: List[Dict[str, Any]]) -> str:
        """
        Format reminders list for user display.
        
        Args:
            reminders: List of reminders
            
        Returns:
            Formatted string
        """
        if not reminders:
            return "Non hai promemoria impostati."
        
        lines = ["I tuoi promemoria:"]
        
        for i, reminder in enumerate(reminders, 1):
            try:
                dt = datetime.fromisoformat(reminder["datetime"])
                date_str = dt.strftime("%d %b %H:%M")
                text = reminder["text"]
                status = reminder.get("status", "pending")
                
                status_icon = "✅" if status == "done" else "⏰" if status == "pending" else "🔔" if status == "triggered" else "❌"
                lines.append(f"{i}. {date_str} – {text} {status_icon}")
                
            except Exception as e:
                log("REMINDER_FORMAT_ERROR", reminder_id=reminder.get("id"), error=str(e))
                continue
        
        return "\n".join(lines)


# Global instance
reminder_engine = ReminderEngine()
