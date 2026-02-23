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
        """Lazy-init del client CalDAV con User-Agent personalizzato."""
        if not self._client:
            if not self.username:
                self.username = os.environ.get("ICLOUD_USER")
            if not self.password:
                self.password = os.environ.get("ICLOUD_PASSWORD")

            if not self.username or not self.password:
                log("ICLOUD_AUTH_MISSING", level="ERROR")
                return None
            try:
                # Inizializza client (caldav 2.2.6 potrebbe non accettare requests_session nel costruttore)
                self._client = caldav.DAVClient(
                    url=self.url,
                    username=self.username,
                    password=self.password
                )
                
                # Imposta User-Agent per evitare blocchi da iCloud
                ua = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
                if hasattr(self._client, 'session'):
                    self._client.session.headers.update({'User-Agent': ua})
                elif hasattr(self._client, 'headers'):
                    self._client.headers.update({'User-Agent': ua})
                
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
        """Recupera i promemoria con massima resilienza per iCloud (evita 500)."""
        client = self._get_client()
        if not client or not self._principal:
            return []

        try:
            calendars = self._principal.calendars()
            target_list = None
            
            # Identificazione lista (come prima)
            for cal in calendars:
                if cal.name and cal.name.lower() == list_name.lower():
                    target_list = cal
                    break
            
            if not target_list and list_name.lower() in ["reminders", "promemoria"]:
                for cal in calendars:
                    name = (cal.name or "").lower()
                    if "promemoria" in name or "reminders" in name:
                        target_list = cal
                        break
            
            if not target_list:
                for cal in calendars:
                    if "/tasks/" in str(cal.url).lower():
                        target_list = cal
                        break

            if not target_list:
                log("ICLOUD_LIST_NOT_FOUND", list_name=list_name)
                return []

            log("ICLOUD_LIST_SELECTED", name=target_list.name)
            
            # FETCHING STRATEGY
            # iCloud 500 spesso capita su query troppo ampie.
            # Proviamo in ordine di "sicurezza"
            todos = []
            
            # Metodo A: fetch_todos (nuova API caldav)
            try:
                log("ICLOUD_FETCH_TRY", method="fetch_todos")
                todos = target_list.search(todo=True, include_completed=False)
            except Exception as e:
                log("ICLOUD_A_FAILED", error=str(e))
                # Metodo B: children (più grezzo, evita filtri lato server che crashano)
                try:
                    log("ICLOUD_FETCH_TRY", method="children")
                    # Recuperiamo tutti gli oggetti della lista
                    all_objects = target_list.children()
                    
                    # Filtriamo in locale per VTODO
                    todos = []
                    for obj in all_objects:
                        try:
                            # caldav objects usually have .data
                            data = obj.data if hasattr(obj, 'data') else ""
                            if "VTODO" in data:
                                todos.append(obj)
                        except:
                            continue
                    log("ICLOUD_B_SUCCESS", count=len(todos))
                except Exception as e2:
                    log("ICLOUD_B_FAILED", error=str(e2))
                    # Metodo C: todos() classico
                    try:
                        log("ICLOUD_FETCH_TRY", method="todos_legacy")
                        todos = target_list.todos()
                    except Exception as e3:
                        log("ICLOUD_C_FAILED", error=str(e3), level="ERROR")
                        return []

            reminders = []
            for todo in todos:
                try:
                    # Forza caricamento dati se necessario
                    if not hasattr(todo, 'vobject_instance') or todo.vobject_instance is None:
                        todo.load()
                    
                    vobj = todo.vobject_instance.vtodo
                    
                    # Filtro locale per escludere completati se non già filtrati
                    status = vobj.status.value.lower() if hasattr(vobj, 'status') else "unknown"
                    if status == "completed":
                        continue

                    reminders.append({
                        "summary": vobj.summary.value if hasattr(vobj, 'summary') else "Senza titolo",
                        "status": status,
                        "due": vobj.due.value.isoformat() if hasattr(vobj, 'due') else None,
                    })
                except Exception:
                    continue
            
            log("ICLOUD_REMINDERS_FETCH", count=len(reminders), list=target_list.name)
            return reminders
        except Exception as e:
            log("ICLOUD_REMINDERS_FETCH_ERROR", error=str(e), level="ERROR")
            return []

# Istanza globale
icloud_service = ICloudService()
