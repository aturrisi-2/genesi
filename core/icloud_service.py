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

    def _get_calendars(self, client):
        """Discovery ultra-selettivo per evitare errori 500 su iCloud."""
        try:
            principal = client.principal()
            
            # Tentativo 1: Chiediamo solo collezioni che supportano VTODO (Promemoria)
            # Questo evita di scansionare calendari, indirizzi, ecc. che causano il 500.
            try:
                calendars = principal.find_calendars(ctype='todo')
                if calendars:
                    log("ICLOUD_CALDAV_DISCOVERY_SUCCESS", count=len(calendars), user=self.username)
                    return calendars
            except Exception as e:
                log("ICLOUD_CALDAV_DISCOVERY_TODO_FAIL", error=str(e), level="WARNING")

            # Tentativo 2: Fallback su ricerca generica ma ultra-protetta
            try:
                all_cals = principal.calendars()
                return [c for c in all_cals if c is not None]
            except Exception as e:
                log("ICLOUD_CALDAV_DISCOVERY_GENERIC_FAIL", error=str(e), level="ERROR")
                
            return []
        except Exception as e:
            log("ICLOUD_CALDAV_DISCOVERY_FATAL", error=str(e), level="ERROR")
            return []

    def get_reminders_lists(self) -> List[Dict[str, Any]]:
        """Recupera le liste di promemoria tramite CalDAV."""
        client = self._get_client()
        if not client: return []
        
        try:
            calendars = self._get_calendars(client)
            lists = []
            for cal in calendars:
                try:
                    # Otteniamo il nome in modo sicuro
                    props = cal.get_properties([caldav.elements.dav.DisplayName()])
                    name = props.get('{DAV:}displayname', 'Senza nome')
                    lists.append({
                        "id": str(cal.url),
                        "name": name
                    })
                except: continue
            
            return lists
        except Exception as e:
            log("ICLOUD_CALDAV_LIST_ERROR", user=self.username, error=str(e), level="ERROR")
            return []

    def get_reminders(self, list_name: str = "Promemoria") -> List[Dict[str, Any]]:
        """Recupera i promemoria pendenti con gestione errori per-lista."""
        client = self._get_client()
        if not client: return []
        
        try:
            calendars = self._get_calendars(client)
            if not calendars: return []

            target_cal = None
            list_name_lower = list_name.lower()
            
            # 1. Cerca match esatto o parziale nel nome
            for cal in calendars:
                try:
                    props = cal.get_properties([caldav.elements.dav.DisplayName()])
                    name = (props.get('{DAV:}displayname') or '').lower()
                    if list_name_lower in name or name in list_name_lower or "reminder" in name or "promemoria" in name:
                        target_cal = cal
                        break
                except: continue
            
            # 2. Se non trovato, usa il primo disponibile che ha dei todo
            if not target_cal and calendars:
                target_cal = calendars[0]

            if not target_cal: return []

            # 3. Fetch dei todo con protezione 500
            try:
                tasks = target_cal.todos()
                reminders = []
                for task in tasks:
                    try:
                        vobj = task.vobject_instance.vtodo
                        status = (getattr(vobj, 'status', None) and vobj.status.value.lower()) or ""
                        if status == 'completed': continue
                        if hasattr(vobj, 'completed'): continue
                            
                        reminders.append({
                            "summary": vobj.summary.value if hasattr(vobj, 'summary') else "Senza titolo",
                            "status": "pending",
                            "due": None
                        })
                    except: continue
                
                log("ICLOUD_CALDAV_REMINDERS_FETCH", count=len(reminders), user=self.username)
                return reminders
            except Exception as e:
                log("ICLOUD_CALDAV_LIST_FETCH_ERROR", list=str(target_cal.url), error=str(e), level="ERROR")
                return []
                
        except Exception as e:
            log("ICLOUD_CALDAV_FETCH_ERROR", user=self.username, error=str(e), level="ERROR")
            return []

# Istanza per compatibilità (fallback su env se non specificato)
icloud_service = ICloudService()
