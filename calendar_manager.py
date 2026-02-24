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
from core.calendar_history import calendar_history

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
        creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json")
        scopes = ['https://www.googleapis.com/auth/calendar']
        
        creds = None
        if os.path.exists(token_path):
            try:
                with open(token_path, 'rb') as token:
                    creds = pickle.load(token)
            except Exception as e:
                log("GOOGLE_TOKEN_LOAD_ERROR", error=str(e))

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    log("GOOGLE_CREDENTIALS_REFRESH_ERROR", error=str(e))
                    creds = None
            else:
                creds = None

        if creds:
            try:
                self._google_service = build('calendar', 'v3', credentials=creds)
                log("GOOGLE_CALENDAR_CONNECTED")
            except Exception as e:
                log("GOOGLE_SERVICE_BUILD_ERROR", error=str(e))

    def list_reminders(self, days: int = 7) -> List[Dict[str, Any]]:
        """Lists Google Calendar events, iCloud (Events + Reminders), and local."""
        all_rems = []
        now = datetime.now()
        end_date = now + timedelta(days=days)
        
        # 1. Google Calendar
        if self._google_service:
            try:
                # Use UTC for Google API consistency
                time_min = datetime.utcnow().isoformat() + 'Z'
                time_max = (datetime.utcnow() + timedelta(days=days)).isoformat() + 'Z'
                
                events_result = self._google_service.events().list(
                    calendarId='primary', 
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=25, 
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
                for e in events_result.get('items', []):
                    start = e['start'].get('dateTime', e['start'].get('date'))
                    guid = e.get('id', f"google_{start}_{e.get('summary')}")
                    
                    item_data = {
                        "guid": guid,
                        "summary": e.get('summary', 'Senza titolo'),
                        "due": start,
                        "provider": "google",
                        "status": "pending",
                        "updated_at": datetime.now().isoformat()
                    }
                    
                    # Salva nello storico
                    calendar_history.add_item(guid, item_data)
                    all_rems.append(item_data)
                
                calendar_history.save()
                log("GOOGLE_LIST_CONNECTED", count=len(events_result.get('items', [])))
            except Exception as e:
                log("GOOGLE_LIST_ERROR", error=str(e))

        # 2. iCloud (Unified)
        if icloud_service.username:
            try:
                ic_items = icloud_service.get_all_items(days=days)
                for item in ic_items:
                    all_rems.append({
                        "summary": item.get('summary', 'Senza titolo'),
                        "due": item.get('due'),
                        "provider": "icloud",
                        "status": "pending"
                    })
                log("ICLOUD_LIST_CONNECTED", count=len(ic_items))
            except Exception as e:
                log("ICLOUD_LIST_ERROR", error=str(e))

        # 3. Local
        for r in self.local_reminders:
            if r.get('status') == 'pending':
                all_rems.append({
                    "summary": r.get('text') or r.get('summary'),
                    "due": r.get('due') or r.get('datetime'),
                    "provider": "local",
                    "status": "pending"
                })
        
        return all_rems

    def add_event(self, title: str, dt: datetime, provider: str = 'detect'):
        if provider == 'detect':
            provider = 'apple' if self._icloud_user else 'google' if self._google_service else 'local'

        if provider == 'google':
            return self._add_google(title, dt)
        elif provider == 'apple' or provider == 'icloud':
            return icloud_service.create_reminder(title, dt)
        else:
            return self._add_local(title, dt)

    async def check_async(self) -> List[Dict[str, Any]]:
        """Controlla se ci sono eventi imminentissimi (prossimi 5-10 min)."""
        rems = self.list_reminders(days=1)
        due = []
        now = datetime.now()
        window = timedelta(minutes=10)
        
        for r in rems:
            dt_str = r.get("due")
            if not dt_str: continue
            try:
                # Normalizzazione basilare
                clean_dt = dt_str.replace("Z", "+00:00").split(".")[0] if "T" in dt_str else dt_str
                dt = datetime.fromisoformat(clean_dt)
                if dt.tzinfo: dt = dt.replace(tzinfo=None) # Comparison simplified
                
                if now <= dt <= now + window:
                    due.append({"text": r["summary"], "time": dt_str})
            except: continue
        return due

    def _add_local(self, title, dt):
        try:
            reminder_entry = {
                "id": len(self.local_reminders) + 1,
                "text": title,
                "due": dt.isoformat(),
                "status": "pending",
                "provider": "local"
            }
            self.local_reminders.append(reminder_entry)
            log("LOCAL_REMINDER_CREATED", title=title)
            return True
        except: return False

    def _add_google(self, title, dt):
        if not self._google_service: 
            return False
        
        # Assume Europe/Rome if naive
        iso_str = dt.isoformat()
        
        event_body = {
            'summary': title,
            'start': {'dateTime': iso_str, 'timeZone': 'Europe/Rome'},
            'end': {'dateTime': (dt + timedelta(hours=1)).isoformat(), 'timeZone': 'Europe/Rome'},
        }
        
        try:
            self._google_service.events().insert(calendarId='primary', body=event_body).execute()
            log("GOOGLE_EVENT_CREATED", title=title)
            return True
        except Exception as e:
            log("GOOGLE_EVENT_ERROR", error=str(e))
            return False

# Global instance
calendar_manager = UnifiedCalendar()
