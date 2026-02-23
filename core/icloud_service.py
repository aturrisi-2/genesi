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
            
            # Tenta di recuperare il principal per confermare l'identità
            principal = self.client.principal()
            return principal is not None
        except Exception:
            return False

    def get_reminders(self, list_name: str = "Reminders") -> List[Dict[str, Any]]:
        """
        Recupera i promemoria da tutte le liste di iCloud usando CalDAV.
        Filtra automaticamente quelli completati.
        """
        if not self.client:
            if not self._connect(): return []

        all_reminders = []
        try:
            principal = self.client.principal()
            calendars = principal.calendars()

            for calendar in calendars:
                # In CalDAV, le liste di promemoria sono calendari che supportano VTODO
                comps = calendar.get_supported_components()
                if 'VTODO' not in comps:
                    continue
                
                # Nome della lista (calendario)
                current_list_name = calendar.name
                
                # Recuperiamo tutti i TODO (non completati di default nella query CalDAV)
                todos = calendar.todos(include_completed=False)
                
                for todo in todos:
                    try:
                        # Usiamo vobject per parsare i dati iCalendar (.ics)
                        v = readOne(todo.data)
                        task = v.vtodo
                        
                        summary = str(task.summary.value) if hasattr(task, 'summary') else "Senza titolo"
                        guid = str(task.uid.value) if hasattr(task, 'uid') else None
                        
                        # Gestione data di scadenza (due date)
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
                    except Exception as task_err:
                        logger.debug(f"Errore parsing task CalDAV: {task_err}")
                        continue

            log("ICLOUD_CALDAV_SYNC_SUCCESS", count=len(all_reminders), user=self.username)
            return all_reminders

        except Exception as e:
            log("ICLOUD_CALDAV_FETCH_ERROR", user=self.username, error=str(e), level="ERROR")
            return []

# Istanza globale
icloud_service = ICloudService()
