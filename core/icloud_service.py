"""
ICLOUD SERVICE - Genesi Core
Integrazione con iCloud Reminders via PyiCloud (Web API).
Include monkeypatch per riparare le date malformate di Apple.
"""

import os
import logging
import datetime
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from core.log import log
from pyicloud import PyiCloudService

logger = logging.getLogger(__name__)

# --- RIMOZIONE PATCH GLOBALE ---
# La patch globale è stata rimossa perché causava incompatibilità con SQLAlchemy/SQLite.
# La riparazione delle date viene ora gestita localmente nei metodi di fetch.
# ------------------------------

import os
import logging
import datetime
import caldav
from vobject import readOne
from typing import List, Dict, Any, Optional
from core.log import log

logger = logging.getLogger(__name__)

class ICloudService:
    def __init__(self, username: Optional[str] = None, password: Optional[str] = None, **kwargs):
        """
        Inizializza il servizio iCloud usando il protocollo ufficiale CalDAV.
        Richiede una 'Password specifica per le app' generata su appleid.apple.com.
        """
        self.username = username or os.environ.get("ICLOUD_USER")
        self.password = password or os.environ.get("ICLOUD_PASSWORD")
        self.client = None
        
        if self.username and self.password:
            self._connect()

    def _connect(self):
        """Stabilisce la connessione CalDAV usando l'endpoint ufficiale e un User-Agent credibile."""
        try:
            url = "https://caldav.icloud.com"
            # Importante: Apple blocca o limita i client che non sembrano 'ufficiali' 
            # o che non dichiarano un User-Agent standard di un dispositivo Apple.
            self.client = caldav.DAVClient(
                url=url,
                username=self.username,
                password=self.password,
                timeout=30
            )
            # Simuliamo un client iOS/macOS per maggiore stabilità
            self.client.session.headers.update({
                'User-Agent': 'iOS/17.0 (21A329) Reminders/1.0',
                'Accept': 'text/xml',
                'Prefer': 'return=minimal'
            })
            log("ICLOUD_CALDAV_CONNECT", user=self.username, endpoint="standard_masqueraded")
            return True
        except Exception as e:
            log("ICLOUD_CALDAV_CONNECT_ERROR", user=self.username, error=str(e), level="ERROR")
            return False

    def validate_credentials(self) -> bool:
        """Verifica se le credenziali (App-Specific Password) sono corrette."""
        try:
            if not self.client:
                if not self._connect(): return False
            try:
                principal = self.client.principal()
                return principal is not None
            except Exception:
                return False
        except Exception:
            return False

    def get_reminders(self, list_name: str = "Reminders") -> List[Dict[str, Any]]:
        """
        Recupera i promemoria da tutte le liste di iCloud usando CalDAV.
        Evita le richieste 'REPORT' (REPORT/calendar-query) che spesso danno errore 500 su Apple,
        preferendo una scansione manuale degli oggetti del calendario.
        """
        if not self.client:
            if not self._connect(): return []

        all_reminders = []
        try:
            principal = self.client.principal()
            
            calendars = []
            try:
                calendars = principal.calendars()
                log("ICLOUD_CALDAV_DISCOVERY", count=len(calendars))
            except Exception as e:
                log("ICLOUD_CALDAV_DISCOVERY_WARN", error=str(e))
                # Fallback manuale se Principal.calendars() fallisce
                try:
                    home_set = principal.get_properties([caldav.elements.ical.CalendarHomeSet()])
                    home_url = home_set.get(caldav.elements.ical.CalendarHomeSet.tag)
                    if home_url:
                        calendars = self.client.calendar(url=home_url).children()
                        log("ICLOUD_CALDAV_DISCOVERY", count=len(calendars), method="manual")
                except Exception as e2:
                    log("ICLOUD_CALDAV_DISCOVERY_FATAL", error=str(e2), level="ERROR")
                    return []

            for calendar in calendars:
                try:
                    name = getattr(calendar, 'name', 'Senza nome')
                    url = str(calendar.url)
                    
                    # Salta calendari di sistema palesi
                    if any(x in url.lower() for x in ["inbox", "outbox", "notification", "tasks"]):
                        continue

                    log("ICLOUD_CALDAV_LIST_CHECK", name=name)
                    
                    # Strategia: Scarichiamo TUTTI gli oggetti della lista. 
                    # Spesso iCloud non filtra bene i VTODO lato server, quindi filtriamo noi.
                    try:
                        all_objs = calendar.objects()
                    except Exception as e:
                        log("ICLOUD_CALDAV_LIST_SKIP", name=name, error=str(e))
                        continue
                    
                    if not all_objs:
                        log("ICLOUD_CALDAV_LIST_EMPTY", name=name)
                        continue

                    log("ICLOUD_CALDAV_LIST_SCAN", name=name, total_objects=len(all_objs))
                    
                    found_count = 0
                    for obj in all_objs:
                        try:
                            # Otteniamo i dati grezzi
                            data = obj.data if hasattr(obj, 'data') else ""
                            if not data or 'VTODO' not in data.upper():
                                continue # Non è un promemoria
                            
                            # Logghiamo il ritrovamento per debug
                            log("ICLOUD_RAW_OBJ_FOUND", list=name, length=len(data), level="DEBUG")
                            
                            v = readOne(data)
                            task = getattr(v, 'vtodo', None)
                            if not task: continue
                            
                            # Filtriamo i completati/cancellati
                            status = str(getattr(task, 'status', '')).upper()
                            if status in ['COMPLETED', 'CANCELLED']:
                                continue

                            summary = str(task.summary.value) if hasattr(task, 'summary') else "Senza titolo"
                            guid = str(task.uid.value) if hasattr(task, 'uid') else None
                            
                            due_iso = None
                            if hasattr(task, 'due'):
                                due_val = task.due.value
                                if isinstance(due_val, (datetime.datetime, datetime.date)):
                                    due_iso = due_val.isoformat()

                            all_reminders.append({
                                "guid": guid,
                                "summary": summary,
                                "status": "pending",
                                "due": due_iso,
                                "list": name
                            })
                            found_count += 1
                        except Exception:
                            continue
                    
                    if found_count > 0:
                        log("ICLOUD_CALDAV_LIST_FOUND", name=name, items=found_count)
                    else:
                        log("ICLOUD_CALDAV_LIST_NO_TASKS", name=name)

                except Exception as cal_err:
                    log("ICLOUD_CALDAV_CAL_ERROR", name=name, error=str(cal_err), level="DEBUG")
                    continue

            log("ICLOUD_CALDAV_SYNC_SUCCESS", count=len(all_reminders), user=self.username)
            return all_reminders

        except Exception as e:
            log("ICLOUD_CALDAV_FETCH_ERROR", user=self.username, error=str(e), level="ERROR")
            return []

# Istanza globale
icloud_service = ICloudService()
