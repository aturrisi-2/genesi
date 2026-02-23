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
        """Stabilisce la connessione CalDAV."""
        try:
            # Endpoint ufficiale CalDAV di Apple
            url = f"https://caldav.icloud.com"
            self.client = caldav.DAVClient(
                url=url,
                username=self.username,
                password=self.password
            )
            log("ICLOUD_CALDAV_CONNECT", user=self.username)
            return True
        except Exception as e:
            log("ICLOUD_CALDAV_CONNECT_ERROR", user=self.username, error=str(e), level="ERROR")
            return False

    def validate_credentials(self) -> bool:
        """Verifica se le credenziali (App-Specific Password) sono corrette."""
        try:
            if not self.client:
                if not self._connect(): return False
            
            # Tenta di recuperare il principal in modo resiliente
            try:
                principal = self.client.principal()
                return principal is not None
            except Exception as e:
                # Se il principal fallisce, proviamo almeno a vedere se l'autenticazione passa
                # facendo una richiesta PROPFIND di base sulla root
                try:
                    self.client.propfind("", props=[caldav.elements.dav.CurrentUserPrincipal()], depth=0)
                    return True
                except:
                    return False
        except Exception:
            return False

    def get_reminders(self, list_name: str = "Reminders") -> List[Dict[str, Any]]:
        """
        Recupera i promemoria da tutte le liste di iCloud usando CalDAV.
        Usa una strategia di discovery più robusta per evitare errori 500 di Apple.
        """
        if not self.client:
            if not self._connect(): return []

        all_reminders = []
        try:
            principal = self.client.principal()
            
            # Strategia 1: Proviamo a recuperare i calendari tramite principal
            # Se fallisce (comune su iCloud), proviamo a interrogare direttamente il home set
            calendars = []
            try:
                calendars = principal.calendars()
            except Exception as e:
                logger.debug(f"CalDAV standard discovery failed: {e}. Trying manual discovery...")
                # Molte implementazioni di iCloud richiedono di interrogare esplicitamente il home set
                try:
                    # Spesso il discovery fallisce se non specifichiamo bene il path.
                    # Proviamo a forzare la ricerca nel calendar-home-set
                    home_set = principal.get_properties([caldav.elements.ical.CalendarHomeSet()])
                    home_url = home_set.get(caldav.elements.ical.CalendarHomeSet.tag)
                    if home_url:
                        # Se abbiamo un home_url, cerchiamo lì dentro
                        calendars = self.client.calendar(url=home_url).children()
                except Exception as e2:
                    log("ICLOUD_CALDAV_DISCOVERY_FATAL", error=str(e2), level="ERROR")
                    return []

            for calendar in calendars:
                try:
                    # Nome della lista
                    current_list_name = getattr(calendar, 'name', 'Senza nome')
                    logger.debug(f"Checking CalDAV calendar: {current_list_name}")
                    
                    # Filtriamo: vogliamo solo calendari che supportano VTODO (Promemoria)
                    try:
                        todos = calendar.todos(include_completed=False)
                        logger.debug(f"Found {len(todos)} items in {current_list_name}")
                    except Exception as e:
                        # Se il calendario non supporta TODO, saltiamo
                        logger.debug(f"Calendar {current_list_name} does not support items: {e}")
                        continue
                    
                    for todo in todos:
                        try:
                            # Parsing data iCalendar
                            v = readOne(todo.data)
                            task = getattr(v, 'vtodo', None)
                            if not task: continue
                            
                            summary = str(task.summary.value) if hasattr(task, 'summary') else "Senza titolo"
                            guid = str(task.uid.value) if hasattr(task, 'uid') else None
                            
                            # Data scadenza
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
                                "list": current_list_name
                            })
                        except Exception as e:
                            logger.debug(f"Error parsing task in {current_list_name}: {e}")
                            continue
                except Exception as cal_err:
                    log("ICLOUD_CALDAV_CAL_ERROR", calendar=str(calendar), error=str(cal_err), level="DEBUG")
                    continue

            log("ICLOUD_CALDAV_SYNC_SUCCESS", count=len(all_reminders), user=self.username)
            return all_reminders

        except Exception as e:
            log("ICLOUD_CALDAV_FETCH_ERROR", user=self.username, error=str(e), level="ERROR")
            return []

# Istanza globale
icloud_service = ICloudService()
