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

import asyncio
import threading

# Genesi Imports
from core.log import log
from core.icloud_service import icloud_service
from core.calendar_history import calendar_history
from core.storage import storage

class UnifiedCalendar:
    def __init__(self):
        self._lock = threading.Lock()
        self._admin_google_service = None
        self._icloud_user = os.environ.get("ICLOUD_USER")
        self._icloud_pass = os.environ.get("ICLOUD_PASSWORD") or os.environ.get("ICLOUD_PASS")
        
        # New multi-user state
        self._user_caches = {} # {user_id: {"rems": [], "last_sync": 0, "is_syncing": False}}
        self._user_services = {} # {user_id: service} - Short term cache for build() objects
        
        # Initialize Google Admin if possible
        self._setup_google_admin()
        
        log("UNIFIED_CALENDAR_INIT", 
            google_active=self._admin_google_service is not None,
            icloud_active=bool(self._icloud_user),
            version="5.0-MultiUser"
        )

    def _setup_google_admin(self):
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
                self._admin_google_service = build('calendar', 'v3', credentials=creds)
                log("GOOGLE_ADMIN_CONNECTED")
            except Exception as e:
                log("GOOGLE_ADMIN_BUILD_ERROR", error=str(e))

    def _get_google_service(self, user_id: str):
        """Returns the Google service for a specific user (either admin or user-specific)."""
        # 1. Check if we already have it in memory
        if user_id in self._user_services:
            return self._user_services[user_id]

        profile = storage.load_sync(f"profile:{user_id}", default={})
        
        # 2. Check if user has own token
        user_token = profile.get("google_token")
        if user_token:
            try:
                creds = Credentials.from_authorized_user_info(user_token)
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                    # Update token in profile
                    profile["google_token"] = json.loads(creds.to_json())
                    storage.save_sync(f"profile:{user_id}", profile)
                
                service = build('calendar', 'v3', credentials=creds)
                self._user_services[user_id] = service
                return service
            except Exception as e:
                log("GOOGLE_USER_SERVICE_ERROR", user_id=user_id, error=str(e))

        # 3. Fallback to Admin if user is admin
        from auth.config import ADMIN_EMAILS
        if profile.get("email") in ADMIN_EMAILS:
            return self._admin_google_service
            
        return None

    def list_reminders(self, user_id: str, days: int = 7, force_sync: bool = False) -> List[Dict[str, Any]]:
        """Recupera promemoria unificati per un utente specifico."""
        now_ts = datetime.now().timestamp()
        
        if user_id not in self._user_caches:
            self._user_caches[user_id] = {"rems": [], "last_sync": 0, "is_syncing": False}
            
        u_cache = self._user_caches[user_id]
        cache_age = now_ts - u_cache["last_sync"]
        
        if not force_sync and u_cache["rems"]:
            if cache_age < 60: # < 1 minuto
                return u_cache["rems"]
            elif cache_age < 600: # 1-10 minuti
                if not u_cache["is_syncing"]:
                    log("OPTIMISTIC_CACHE_HIT_USER", user_id=user_id, age=int(cache_age))
                    threading.Thread(target=self._perform_sync, args=(user_id, days), daemon=True).start()
                return u_cache["rems"]

        return self._perform_sync(user_id, days)

    def _perform_sync(self, user_id: str, days: int = 7) -> List[Dict[str, Any]]:
        """Esegue la sincronizzazione reale per utente."""
        # Initialize user state if missing
        if user_id not in self._user_caches:
            self._user_caches[user_id] = {"rems": [], "last_sync": 0, "is_syncing": False}
            
        u_state = self._user_caches[user_id]
        if u_state["is_syncing"]:
            return u_state["rems"]
            
        u_state["is_syncing"] = True
        try:
            with self._lock:
                all_rems = []
                now = datetime.now()
                
                # 1. Google (User Specific)
                g_service = self._get_google_service(user_id)
                if g_service:
                    try:
                        time_min = datetime.utcnow().isoformat() + 'Z'
                        time_max = (datetime.utcnow() + timedelta(days=days)).isoformat() + 'Z'
                        events_result = g_service.events().list(
                            calendarId='primary', timeMin=time_min, timeMax=time_max,
                            maxResults=25, singleEvents=True, orderBy='startTime'
                        ).execute()
                        
                        for e in events_result.get('items', []):
                            start = e['start'].get('dateTime', e['start'].get('date'))
                            guid = e.get('id', f"google_{start}_{e.get('summary')}")
                            item_data = {
                                "guid": guid, "summary": e.get('summary', 'Senza titolo'),
                                "due": start, "provider": "google", "status": "pending",
                                "updated_at": datetime.now().isoformat()
                            }
                            calendar_history.add_item(guid, item_data)
                            all_rems.append(item_data)
                        log("GOOGLE_USER_LIST", user_id=user_id, count=len(events_result.get('items', [])))
                    except Exception as e:
                        log("GOOGLE_USER_LIST_ERROR", user_id=user_id, error=str(e))

                # 2. iCloud (User Specific or Admin Fallback)
                profile = storage.load_sync(f"profile:{user_id}", default={})
                from auth.config import ADMIN_EMAILS
                is_admin = profile.get("email") in ADMIN_EMAILS
                
                icloud_user = profile.get("icloud_user")
                icloud_pass = profile.get("icloud_password")
                
                if not icloud_user and is_admin:
                    icloud_user = self._icloud_user
                    icloud_pass = self._admin_icloud_pass if hasattr(self, '_admin_icloud_pass') else self._icloud_pass
                
                if icloud_user and icloud_pass:
                    try:
                        # Dynamic service for this user
                        from core.icloud_service import ICloudService
                        user_icloud = ICloudService(username=icloud_user, password=icloud_pass)
                        ic_items = user_icloud.get_all_items(days=days)
                        for item in ic_items:
                            all_rems.append({
                                "guid": item.get('guid'),
                                "summary": item.get('summary', 'Senza titolo'),
                                "due": item.get('due'),
                                "provider": "icloud",
                                "status": "pending"
                            })
                    except Exception as e:
                        log("ICLOUD_USER_LIST_ERROR", user_id=user_id, error=str(e))

                u_state["rems"] = all_rems
                u_state["last_sync"] = now.timestamp()
                return all_rems
        finally:
            u_state["is_syncing"] = False
        return []

    def add_event(self, user_id: str, title: str, dt: datetime, provider: str = 'detect'):
        g_service = self._get_google_service(user_id)
        
        if provider == 'detect':
            profile = storage.load_sync(f"profile:{user_id}", default={})
            from auth.config import ADMIN_EMAILS
            is_admin = profile.get("email") in ADMIN_EMAILS
            has_apple = bool(profile.get("icloud_user") or (is_admin and self._icloud_user))
            # Prefer Google if connected (explicit OAuth), fall back to iCloud, then local
            provider = 'google' if g_service else 'apple' if has_apple else 'local'

        if provider == 'google':
            return self._add_google(user_id, title, dt)
        elif provider == 'apple' or provider == 'icloud':
            profile = storage.load_sync(f"profile:{user_id}", default={})
            from auth.config import ADMIN_EMAILS
            is_admin = profile.get("email") in ADMIN_EMAILS

            icloud_user = profile.get("icloud_user") or (self._icloud_user if is_admin else None)
            icloud_pass = profile.get("icloud_password") or (self._icloud_pass if is_admin else None)

            if icloud_user and icloud_pass:
                from core.icloud_service import ICloudService
                user_icloud = ICloudService(username=icloud_user, password=icloud_pass)
                return user_icloud.create_event(title, dt, is_todo=False)  # VEVENT → Calendario
            return False
        else:
            return False

    def _add_google(self, user_id, title, dt):
        g_service = self._get_google_service(user_id)
        if not g_service or not dt:
            return None

        iso_str = dt.isoformat()
        event_body = {
            'summary': title,
            'start': {'dateTime': iso_str, 'timeZone': 'Europe/Rome'},
            'end': {'dateTime': (dt + timedelta(hours=1)).isoformat(), 'timeZone': 'Europe/Rome'},
        }

        try:
            result = g_service.events().insert(calendarId='primary', body=event_body).execute()
            event_id = result.get('id')
            log("GOOGLE_EVENT_CREATED", user_id=user_id, title=title, event_id=event_id)
            return event_id  # stringa — retrocompatibile con bool check
        except Exception as e:
            log("GOOGLE_EVENT_ERROR", user_id=user_id, error=str(e))
            return None

    def delete_event(self, user_id: str, provider: str,
                     uid: str = None, event_id: str = None) -> bool:
        """
        Elimina un evento da iCloud (per UID CalDAV) o Google (per event_id).
        """
        try:
            if provider in ('apple', 'icloud') and uid:
                profile = storage.load_sync(f"profile:{user_id}", default={})
                from auth.config import ADMIN_EMAILS
                is_admin = profile.get("email") in ADMIN_EMAILS
                icloud_user = profile.get("icloud_user") or (self._icloud_user if is_admin else None)
                icloud_pass = profile.get("icloud_password") or (self._icloud_pass if is_admin else None)
                if icloud_user and icloud_pass:
                    from core.icloud_service import ICloudService
                    svc = ICloudService(username=icloud_user, password=icloud_pass)
                    return svc.delete_item_by_uid(uid, is_todo=False)
            elif provider == 'google' and event_id:
                g_service = self._get_google_service(user_id)
                if g_service:
                    g_service.events().delete(calendarId='primary', eventId=event_id).execute()
                    log("GOOGLE_EVENT_DELETED", user_id=user_id, event_id=event_id)
                    return True
        except Exception as e:
            log("CALENDAR_DELETE_ERROR", user_id=user_id, provider=provider, error=str(e))
        return False

    async def check_async(self) -> List[Dict[str, Any]]:
        """Deprecated global check."""
        return []

# Global instance
calendar_manager = UnifiedCalendar()
