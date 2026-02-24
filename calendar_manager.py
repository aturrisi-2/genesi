import os
import asyncio
import json
import pickle
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# External Libraries
import caldav
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from icalendar import Calendar, Event
import reminder  # From reminder.py package
try:
    from pyremindkit.reminders import Reminders
except ImportError:
    Reminders = None

# Genesi Imports
from core.log import log
from core.icloud_service import icloud_service

class UnifiedCalendar:
    def __init__(self):
        self._google_service = None
        self._icloud_user = os.environ.get("ICLOUD_USER")
        self._icloud_pass = os.environ.get("ICLOUD_PASSWORD") or os.environ.get("ICLOUD_PASS")
        self.local_reminders = []
        
        # Initialize Google if possible
        self._setup_google()
        
        log("UNIFIED_CALENDAR_INIT", 
            google_active=self._google_service is not None,
            icloud_active=bool(self._icloud_user)
        )

    def _setup_google(self):
        token_path = os.environ.get("GOOGLE_TOKEN_PATH", "token.json")
        if not os.path.exists(token_path):
            return
            
        try:
            with open(token_path, 'rb') as token:
                creds = pickle.load(token)
            
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(token_path, 'wb') as token:
                    pickle.dump(creds, token)
            
            if creds and creds.valid:
                self._google_service = build('calendar', 'v3', credentials=creds)
        except Exception as e:
            log("GOOGLE_AUTH_ERROR", error=str(e))

    def add_event(self, title: str, dt: datetime, provider: str = 'detect'):
        """
        Adds an event or reminder to the specified provider.
        Provider can be 'apple', 'google', 'local', or 'detect'.
        """
        if provider == 'detect':
            # Logic: If ICLOUD_USER is set and we're likely an Apple user (Merate IT hint)
            if self._icloud_user:
                provider = 'apple'
            elif self._google_service:
                provider = 'google'
            else:
                provider = 'local'

        log("CALENDAR_ADD_REQUEST", title=title, provider=provider, time=dt.isoformat())

        if provider == 'apple':
            return self._add_apple(title, dt)
        elif provider == 'google':
            return self._add_google(title, dt)
        else:
            return self._add_local(title, dt)

    def _add_apple(self, title, dt):
        # Prefer icloud_service (CalDAV) as it's already integrated
        try:
            success = icloud_service.create_reminder(title, dt)
            if success:
                log("APPLE_EVENT_CREATED", title=title)
                return True
        except Exception as e:
            log("APPLE_EVENT_ERROR", error=str(e))
        return False

    def _add_google(self, title, dt):
        if not self._google_service:
            log("GOOGLE_NOT_CONFIGURED")
            return False
        
        event = {
            'summary': title,
            'start': {
                'dateTime': dt.isoformat(),
                'timeZone': 'Europe/Rome',
            },
            'end': {
                'dateTime': (dt + timedelta(hours=1)).isoformat(),
                'timeZone': 'Europe/Rome',
            },
        }
        
        try:
            self._google_service.events().insert(calendarId='primary', body=event).execute()
            log("GOOGLE_EVENT_CREATED", title=title)
            return True
        except Exception as e:
            log("GOOGLE_EVENT_ERROR", error=str(e))
            return False

    def _add_local(self, title, dt):
        # Simple local list for now
        reminder_entry = {
            "id": len(self.local_reminders) + 1,
            "text": title,
            "due": dt.isoformat(),
            "status": "pending"
        }
        self.local_reminders.append(reminder_entry)
        log("LOCAL_REMINDER_CREATED", title=title)
        return True

    def list_reminders(self) -> List[Dict[str, Any]]:
        """Lists pending reminders from all active sources."""
        all_rems = []
        
        # Apple
        if self._icloud_user:
            try:
                apple_rems = icloud_service.get_reminders()
                for r in apple_rems:
                    r['provider'] = 'apple'
                    all_rems.append(r)
            except Exception as e:
                log("APPLE_LIST_ERROR", error=str(e))

        # Local
        for r in self.local_reminders:
            if r['status'] == 'pending':
                r['provider'] = 'local'
                all_rems.append(r)

        return all_rems

    async def check_async(self):
        """
        Background task to check for pending reminders.
        Integration point for main.py scheduler.
        """
        now = datetime.now()
        due = [r for r in self.local_reminders if r['status'] == 'pending' and datetime.fromisoformat(r['due']) <= now]
        
        for r in due:
            r['status'] = 'triggered'
            log("CALENDAR_REMINDER_TRIGGERED", text=r['text'], provider=r['provider'])
            # Here we would trigger Genesi notifications
            
        return due

# Singleton instance
calendar_manager = UnifiedCalendar()
