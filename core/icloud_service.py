"""
ICLOUD SERVICE - Genesi Core
Integrazione con iCloud Reminders e Calendar via CalDAV.
"""

import os
import logging
import caldav
from datetime import datetime
import re
from typing import List, Dict, Any, Optional
from core.log import log

logger = logging.getLogger(__name__)

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
            
            # Tentativo 1: Standard calendars()
            try:
                # calendars() restituisce la lista delle collezioni
                # Se questo dà 500, proveremo find_calendars (se esiste) o discovery manuale
                cals = principal.calendars()
                log("ICLOUD_CALDAV_DISCOVERY_SUCCESS", count=len(cals), user=self.username)
                return cals
            except Exception as e:
                log("ICLOUD_CALDAV_DISCOVERY_STD_FAIL", error=str(e), level="WARNING")
                
                # Tentativo 2: Usiamo find_calendars su Principal (alcune versioni lo hanno)
                if hasattr(principal, 'find_calendars'):
                    try:
                        return principal.find_calendars(ctype='todo')
                    except: pass
                
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
                    # Otteniamo il nome in modo sicuro. iCloud può dare 500 qui su alcune liste.
                    props = cal.get_properties([caldav.elements.dav.DisplayName()])
                    name = props.get('{DAV:}displayname', 'Senza nome')
                    lists.append({
                        "id": str(cal.url),
                        "name": name
                    })
                except Exception as e:
                    # Saltiamo silenziosamente le liste che danno errore (es. cartelle di sistema)
                    continue
            
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

            target_cals = []
            list_name_lower = list_name.lower()
            
            # 1. Filtriamo le liste che sembrano promemoria (più ampio per l'italiano)
            for cal in calendars:
                try:
                    if cal is None: continue
                    url_str = str(cal.url)
                    name = "Sconosciuta"
                    try:
                        props = cal.get_properties([caldav.elements.dav.DisplayName()])
                        name = props.get('{DAV:}displayname', 'Senza nome')
                    except: pass
                    
                    log("ICLOUD_CALDAV_LIST_DISCOVERED", name=name, url=url_str, user=self.username)

                    name_l = name.lower()
                    url_l = url_str.lower()
                    if (list_name_lower in name_l or 
                        any(kw in name_l for kw in ["reminder", "promemoria", "task", "casa", "lavoro", "famiglia", "personale"]) or
                        any(kw in url_l for kw in ["reminder", "task", "home", "work", "family"])):
                        target_cals.append(cal)
                except: continue
            
            if not target_cals:
                target_cals = [c for c in calendars if c is not None]

            all_reminders = []
            for target_cal in target_cals:
                try:
                    all_objs = []
                    try:
                        all_objs = target_cal.objects()
                    except Exception: continue

                    for obj in all_objs:
                        try:
                            # Lazy load content
                            if not hasattr(obj, 'data') or not obj.data:
                                obj.load()
                                
                            raw_data = obj.data
                            if not raw_data or "VTODO" not in raw_data.upper():
                                continue
                            
                            # Estrazione SUMMARY
                            summary = "Senza titolo"
                            s_match = re.search(r'SUMMARY(?:;[^:]*)?:(.*)', raw_data, re.IGNORECASE)
                            if s_match:
                                summary = s_match.group(1).strip().replace('\\', '')
                            
                            # Filtro completati (STATUS o PERCENT-COMPLETE)
                            raw_upper = raw_data.upper()
                            is_completed = "STATUS:COMPLETED" in raw_upper or "PERCENT-COMPLETE:100" in raw_upper
                            
                            if not is_completed:
                                all_reminders.append({
                                    "summary": summary,
                                    "status": "pending",
                                    "due": None
                                })
                        except: continue
                except: continue
                
            log("ICLOUD_SYNC_SUCCESS", count=len(all_reminders), user=self.username)
            return all_reminders
                
        except Exception as e:
            log("ICLOUD_CALDAV_FETCH_ERROR", user=self.username, error=str(e), level="ERROR")
            return []

# Istanza per compatibilità (fallback su env se non specificato)
icloud_service = ICloudService()
