"""
ICLOUD SERVICE - Genesi Core
Integrazione con iCloud Reminders e Calendar via CalDAV.
"""

import os
import caldav
from datetime import datetime
from typing import List, Dict, Any, Optional
from core.log import log

class ICloudService:
    def __init__(self, username: Optional[str] = None, password: Optional[str] = None, cookie_directory: Optional[str] = None):
        self.username = username or os.environ.get("ICLOUD_USER")
        self.password = password or os.environ.get("ICLOUD_PASSWORD")
        self.cookie_directory = cookie_directory
        self._client = None # Changed from _api to _client
        log("ICLOUD_SERVICE_INIT", user=self.username)

    def _get_client(self):
        """Inizializza il client CalDAV con la password specifica per le app."""
        if self._client: # Added caching for the client
            return self._client

        if not self.username or not self.password:
            log("ICLOUD_AUTH_MISSING", user=self.username, level="ERROR")
            return None
            
        try:
            # Apple richiede l'URL diretto per evitare bug di discovery
            # Spesso funziona il generico, ma caldav library gestisce bene il redirect
            client = caldav.DAVClient(
                url="https://caldav.icloud.com",
                username=self.username,
                password=self.password
            )
            self._client = client # Store the client
            log("ICLOUD_CALDAV_CLIENT_INIT", user=self.username)
            return client
        except Exception as e:
            log("ICLOUD_CALDAV_INIT_ERROR", user=self.username, error=str(e), level="ERROR")
            return None

    # Removed authenticate_with_2fa as it's specific to pyicloud

    def get_reminders_lists(self) -> List[Dict[str, Any]]:
        """Recupera le liste di promemoria tramite CalDAV."""
        client = self._get_client()
        if not client: return []
        
        try:
            principal = client.principal()
            calendars = principal.calendars()
            
            lists = []
            for cal in calendars:
                # Verifichiamo se è una lista di promemoria (task) o calendario (event)
                # In iCloud sono spesso misti o separati da proprietà
                props = cal.get_properties([caldav.elements.dav.DisplayName()])
                name = props.get('{DAV:}displayname', 'Senza nome')
                
                lists.append({
                    "id": cal.url,
                    "name": name
                })
            
            log("ICLOUD_CALDAV_LISTS_FOUND", count=len(lists), user=self.username)
            return lists
        except Exception as e:
            log("ICLOUD_CALDAV_LIST_ERROR", user=self.username, error=str(e), level="ERROR")
            return []

    def get_reminders(self, list_name: str = "Promemoria") -> List[Dict[str, Any]]:
        """Recupera i promemoria pendenti da una lista specifica."""
        client = self._get_client()
        if not client: return []
        
        try:
            principal = client.principal()
            calendars = principal.calendars()
            
            target_cal = None
            list_name_lower = list_name.lower()
            
            # Cerca la lista per nome
            for cal in calendars:
                props = cal.get_properties([caldav.elements.dav.DisplayName()])
                name = (props.get('{DAV:}displayname') or '').lower()
                if list_name_lower in name:
                    target_cal = cal
                    break
            
            # Fallback alla prima se non trovata
            if not target_cal and calendars:
                target_cal = calendars[0]
                
            if not target_cal:
                return []

            # Fetch tasks (VTODO)
            tasks = target_cal.todos()
            
            reminders = []
            for task in tasks:
                vobj = task.vobject_instance.vtodo
                
                # Escludi completati
                if hasattr(vobj, 'status') and vobj.status.value.lower() == 'completed':
                    continue
                if hasattr(vobj, 'completed'):
                    continue
                    
                summary = vobj.summary.value if hasattr(vobj, 'summary') else "Senza titolo"
                
                reminders.append({
                    "summary": summary,
                    "status": "not_completed",
                    "due": None # Parsing date rimosso per stabilità
                })
                
            log("ICLOUD_CALDAV_REMINDERS_FETCH", count=len(reminders), user=self.username)
            return reminders
            
        except Exception as e:
            log("ICLOUD_CALDAV_FETCH_ERROR", user=self.username, error=str(e), level="ERROR")
            return []

# Istanza per compatibilità (fallback su env se non specificato)
icloud_service = ICloudService()
