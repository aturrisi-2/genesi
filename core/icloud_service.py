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
        """Stabilisce la connessione CalDAV usando l'endpoint specifico per i Promemoria."""
        try:
            # Endpoint dedicato ai promemoria (più stabile per la nuova architettura iOS 13+)
            url = "https://reminders.icloud.com"
            self.client = caldav.DAVClient(
                url=url,
                username=self.username,
                password=self.password,
                timeout=30 # Apple a volte è lenta
            )
            log("ICLOUD_CALDAV_CONNECT", user=self.username, endpoint="reminders")
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
            calendars = []
            try:
                calendars = principal.calendars()
                log("ICLOUD_CALDAV_DISCOVERY", count=len(calendars), method="standard")
            except Exception as e:
                log("ICLOUD_CALDAV_DISCOVERY_WARN", error=str(e), method="standard")
                # Strategia 2: Manual discovery via home set
                try:
                    home_set = principal.get_properties([caldav.elements.ical.CalendarHomeSet()])
                    home_url = home_set.get(caldav.elements.ical.CalendarHomeSet.tag)
                    if home_url:
                        calendars = self.client.calendar(url=home_url).children()
                        log("ICLOUD_CALDAV_DISCOVERY", count=len(calendars), method="manual_home")
                except Exception as e2:
                    log("ICLOUD_CALDAV_DISCOVERY_FATAL", error=str(e2), level="ERROR")
                    return []

            for calendar in calendars:
                try:
                    current_list_name = getattr(calendar, 'name', 'Senza nome')
                    # Logghiamo ogni lista che proviamo a scansionare
                    log("ICLOUD_CALDAV_LIST_CHECK", name=current_list_name)
                    
                    try:
                        # Alcuni server Apple richiedono un fetch esplicito
                        todos = calendar.todos(include_completed=False)
                        
                        # Se è vuoto, proviamo a chiedere genericamente tutti gli oggetti 
                        # del calendario per vedere se ci sono VTODO "nascosti"
                        if not todos:
                            objs = calendar.objects_by_filters(components=['VTODO'])
                            if objs:
                                todos = objs
                                log("ICLOUD_CALDAV_VTODO_FALLBACK", name=current_list_name, count=len(todos))
                        
                        if len(todos) > 0:
                            log("ICLOUD_CALDAV_LIST_FOUND", name=current_list_name, items=len(todos))
                        else:
                            # Logghiamo anche quando è vuota, per conferma
                            log("ICLOUD_CALDAV_LIST_EMPTY", name=current_list_name)
                    except Exception as e:
                        log("ICLOUD_CALDAV_LIST_ERROR", name=current_list_name, error=str(e))
                        continue
                    
                    for todo in todos:
                        try:
                            v = readOne(todo.data)
                            task = getattr(v, 'vtodo', None)
                            if not task: continue
                            
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
                                "list": current_list_name
                            })
                        except Exception as e:
                            log("ICLOUD_CALDAV_TASK_PARSE_ERROR", error=str(e), level="DEBUG")
                            continue
                except Exception as cal_err:
                    log("ICLOUD_CALDAV_CAL_ERROR", error=str(cal_err), level="DEBUG")
                    continue

            log("ICLOUD_CALDAV_SYNC_SUCCESS", count=len(all_reminders), user=self.username)
            return all_reminders

        except Exception as e:
            log("ICLOUD_CALDAV_FETCH_ERROR", user=self.username, error=str(e), level="ERROR")
            return []

# Istanza globale
icloud_service = ICloudService()
