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
        creds_path = os.environ.get("GOOGLE_CREDENTIALS_PATH", "credentials.json")
        scopes = ['https://www.googleapis.com/auth/calendar']
        
        creds = None
        if os.path.exists(token_path):
            try:
                with open(token_path, 'rb') as token:
                    creds = pickle.load(token)
            except Exception as e:
                log("GOOGLE_TOKEN_LOAD_ERROR", error=str(e))

        # If no valid credentials, try to get them
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    log("GOOGLE_CREDENTIALS_REFRESH_ERROR", error=str(e))
                    creds = None
            
            if not creds and os.path.exists(creds_path):
                # This requires interaction, might be tricky on a VPS
                # But we implement it as requested
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(creds_path, scopes)
                    creds = flow.run_local_server(port=0)
                    # Save the credentials for the next run
                    with open(token_path, 'wb') as token:
                        pickle.dump(creds, token)
                    log("GOOGLE_AUTH_FLOW_COMPLETED")
                except Exception as e:
                    log("GOOGLE_AUTH_FLOW_ERROR", error=str(e))

        if creds and creds.valid:
            try:
                self._google_service = build('calendar', 'v3', credentials=creds)
                log("GOOGLE_CALENDAR_SERVICE_READY")
            except Exception as e:
                log("GOOGLE_SERVICE_BUILD_ERROR", error=str(e))

    def add_event(self, title: str, dt: datetime, provider: str = 'detect'):
        """
        Adds an event or reminder. 
        Provider: 'apple', 'apple_rem', 'google', 'local', 'detect'.
        """
        if provider == 'detect':
            if self._icloud_user:
                provider = 'apple'
            elif self._google_service:
                provider = 'google'
            else:
                provider = 'local'

        log("CALENDAR_ADD_REQUEST", title=title, provider=provider, time=dt.isoformat())

        if provider == 'apple':
            # iCloud Calendar via CalDAV (using existing service)
            return icloud_service.create_reminder(title, dt)
        elif provider == 'apple_rem':
            # iCloud Reminders via pyremindkit (if credentials provided)
            if Reminders and self._icloud_user and self._icloud_pass:
                try:
                    # Note: pyremindkit might need specific setup not shown in snippet
                    # but following the user's example:
                    client = Reminders(self._icloud_user, self._icloud_pass)
                    client.reminders().create(title=title, due_date=dt.strftime("%Y-%m-%d"))
                    log("APPLE_REM_CREATED", title=title)
                    return True
                except Exception as e:
                    log("APPLE_REM_ERROR", error=str(e))
            return icloud_service.create_reminder(title, dt) # Fallback
        elif provider == 'google':
            return self._add_google(title, dt)
        else:
            return self._add_local(title, dt)

    def _add_local(self, title, dt):
        # Using icalendar for local storage
        cal = Calendar()
        event = Event()
        event.add('summary', title)
        event.add('dtstart', dt)
        event.add('dtend', dt + timedelta(hours=1))
        cal.add_component(event)
        
        # Save to local file
        os.makedirs("data", exist_ok=True)
        with open("data/local_events.ics", "ab") as f:
            f.write(cal.to_ical())
            
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

    def list_reminders(self, days: int = 7) -> List[Dict[str, Any]]:
        """Lists pending reminders and upcoming calendar events from all active sources."""
        all_rems = []
        now = datetime.now()
        end_date = now + timedelta(days=days)
        
        # 1. Google Calendar (Upcoming Events)
        if self._google_service:
            try:
                events_result = self._google_service.events().list(
                    calendarId='primary', 
                    timeMin=now.isoformat() + 'Z',
                    timeMax=end_date.isoformat() + 'Z',
                    maxResults=10, 
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                events = events_result.get('items', [])
                for e in events:
                    start = e['start'].get('dateTime', e['start'].get('date'))
                    all_rems.append({
                        "summary": e.get('summary', 'Senza titolo'),
                        "due": start,
                        "provider": "google",
                        "status": "pending"
                    })
                log("GOOGLE_LIST_SUCCESS", count=len(events))
            except Exception as e:
                log("GOOGLE_LIST_ERROR", error=str(e))

        # 2. Apple (Reminders)
        if self._icloud_user:
            try:
                apple_rems = icloud_service.get_reminders()
                for r in apple_rems:
                    r['provider'] = 'apple'
                    all_rems.append(r)
            except Exception as e:
                log("APPLE_LIST_ERROR", error=str(e))

        # 3. Local
        for r in self.local_reminders:
            if r['status'] == 'pending':
                r['provider'] = 'local'
                # Match schema
                all_rems.append({
                    "summary": r.get('text'),
                    "due": r.get('due'),
                    "provider": "local",
                    "status": "pending"
                })

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
