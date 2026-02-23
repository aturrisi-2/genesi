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
        if not client:
            return []

        try:
            calendars = self._principal.calendars()
            lists = []
            for cal in calendars:
                # Filtra per calendari che supportano i task (VTODO)
                props = cal.get_properties([caldav.elements.dav.SupportedComponentSet()])
                # Note: properties access can vary, some servers use different methods
                # Simple check for reminders often involves 'task' in metadata or just listing all
                lists.append({
                    "id": str(cal.url),
                    "name": cal.name,
                })
            return lists
        except Exception as e:
            log("ICLOUD_LIST_FETCH_ERROR", error=str(e), level="ERROR")
            return []

    def get_reminders(self, list_name: str = "Reminders") -> List[Dict[str, Any]]:
        """Recupera i promemoria da una lista specifica."""
        client = self._get_client()
        if not client or not self._principal:
            return []

        try:
            # Trova la lista specifica
            target_list = None
            for cal in self._principal.calendars():
                if cal.name.lower() == list_name.lower():
                    target_list = cal
                    break
            
            if not target_list:
                log("ICLOUD_LIST_NOT_FOUND", list_name=list_name)
                return []

            todos = target_list.todos()
            reminders = []
            for todo in todos:
                vobj = todo.vobject_instance.vtodo
                reminders.append({
                    "summary": vobj.summary.value if hasattr(vobj, 'summary') else "Senza titolo",
                    "status": vobj.status.value if hasattr(vobj, 'status') else "unknown",
                    "due": vobj.due.value.isoformat() if hasattr(vobj, 'due') else None,
                })
            
            log("ICLOUD_REMINDERS_FETCH", count=len(reminders), list=list_name)
            return reminders
        except Exception as e:
            log("ICLOUD_REMINDERS_FETCH_ERROR", error=str(e), level="ERROR")
            return []

# Istanza globale
icloud_service = ICloudService()
