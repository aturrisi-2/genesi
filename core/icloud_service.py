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
    def __init__(self):
        self.username = os.environ.get("ICLOUD_USER")
        self.password = os.environ.get("ICLOUD_PASSWORD")
        self.url = "https://caldav.icloud.com"
        self._client = None
        self._principal = None
        log("ICLOUD_SERVICE_INIT")

    def _get_client(self):
        """Lazy-init del client CalDAV."""
        if not self._client:
            # Refresh credentials if not set at init (handle late load_dotenv)
            if not self.username:
                self.username = os.environ.get("ICLOUD_USER")
            if not self.password:
                self.password = os.environ.get("ICLOUD_PASSWORD")

            if not self.username or not self.password:
                log("ICLOUD_AUTH_MISSING", level="ERROR")
                return None
            try:
                self._client = caldav.DAVClient(
                    url=self.url,
                    username=self.username,
                    password=self.password
                )
                self._principal = self._client.principal()
                log("ICLOUD_AUTH_SUCCESS")
            except Exception as e:
                log("ICLOUD_AUTH_ERROR", error=str(e), level="ERROR")
                return None
        return self._client

    def get_reminders_lists(self) -> List[Dict[str, Any]]:
        """Recupera le liste di promemoria disponibili."""
        client = self._get_client()
        if not client or not self._principal:
            return []

        try:
            calendars = self._principal.calendars()
            lists = []
            for cal in calendars:
                # Aggiungiamo tutte le liste, poi filtreremo nell'uso
                lists.append({
                    "id": str(cal.url),
                    "name": cal.name or "Senza nome",
                })
            
            log("ICLOUD_LISTS_FOUND", count=len(lists))
            return lists
        except Exception as e:
            log("ICLOUD_LIST_FETCH_ERROR", error=str(e), level="ERROR")
            return []

    def get_reminders(self, list_name: str = "Reminders") -> List[Dict[str, Any]]:
        """Recupera i promemoria da una lista specifica con fallback intelligente."""
        client = self._get_client()
        if not client or not self._principal:
            return []

        try:
            calendars = self._principal.calendars()
            target_list = None
            
            # 1. Cerca per nome esatto (case insensitive)
            for cal in calendars:
                if cal.name and cal.name.lower() == list_name.lower():
                    target_list = cal
                    break
            
            # 2. Fallback: Cerca per keyword nel nome (se list_name è Reminders/Promemoria)
            if not target_list and list_name.lower() in ["reminders", "promemoria"]:
                for cal in calendars:
                    name = (cal.name or "").lower()
                    if "promemoria" in name or "reminders" in name:
                        target_list = cal
                        break
            
            # 3. Fallback estremo: cerca "tasks" nell'URL
            if not target_list:
                for cal in calendars:
                    if "/tasks/" in str(cal.url).lower():
                        target_list = cal
                        break

            if not target_list:
                log("ICLOUD_LIST_NOT_FOUND", list_name=list_name)
                return []

            log("ICLOUD_LIST_SELECTED", name=target_list.name)
            
            # Prova diversi metodi di fetch perché i server Apple possono dare 500 su query massive
            todos = []
            try:
                # Metodo 1: Search (spesso più stabile su iCloud)
                todos = target_list.search(todo=True)
                log("ICLOUD_FETCH_METHOD", method="search")
            except Exception as e:
                log("ICLOUD_SEARCH_ERROR", error=str(e), level="WARNING")
                try:
                    # Metodo 2: todos() (fallback classico)
                    todos = target_list.todos()
                    log("ICLOUD_FETCH_METHOD", method="todos")
                except Exception as e2:
                    log("ICLOUD_TODOS_ERROR", error=str(e2), level="ERROR")
                    return []

            reminders = []
            for todo in todos:
                try:
                    # Carica i dati del task
                    # Alcune versioni di caldav richiedono .load() se search non ha caricato tutto
                    if not hasattr(todo, 'vobject_instance'):
                        todo.load()
                    
                    vobj = todo.vobject_instance.vtodo
                    reminders.append({
                        "summary": vobj.summary.value if hasattr(vobj, 'summary') else "Senza titolo",
                        "status": vobj.status.value if hasattr(vobj, 'status') else "unknown",
                        "due": vobj.due.value.isoformat() if hasattr(vobj, 'due') else None,
                    })
                except Exception as e:
                    # Salta eventuali task corrotti
                    continue
            
            log("ICLOUD_REMINDERS_FETCH", count=len(reminders), list=target_list.name)
            return reminders
        except Exception as e:
            log("ICLOUD_REMINDERS_FETCH_ERROR", error=str(e), level="ERROR")
            return []

# Istanza globale
icloud_service = ICloudService()
