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
        self._api = None
        log("ICLOUD_SERVICE_INIT")

    def _get_api(self):
        """Inizializza l'interfaccia pyicloud con gestione 2FA."""
        if self._api:
            return self._api
            
        if not self.username or not self.password:
            log("ICLOUD_AUTH_MISSING", level="ERROR")
            return None
            
        try:
            from pyicloud import PyiCloudService
            self._api = PyiCloudService(self.username, self.password)
            
            if self._api.requires_2fa:
                log("ICLOUD_2FA_REQUIRED", level="WARNING")
                # In un ambiente server, qui dovremmo avere un modo per iniettare il codice
                # Per ora logghiamo il problema
                return None
                
            log("ICLOUD_WEB_AUTH_SUCCESS")
            return self._api
        except Exception as e:
            log("ICLOUD_WEB_AUTH_ERROR", error=str(e), level="ERROR")
            return None

    def get_reminders_lists(self) -> List[Dict[str, Any]]:
        """Recupera le liste usando il metodo Raw Web."""
        api = self._get_api()
        if not api: return []
        
        try:
            # Bypass crash: fetch raw collections
            host = api._webservices.get('reminders', {}).get('url')
            if not host: return []
            
            url = f"{host}/rd/startup"
            response = api.session.get(url, params=api.params)
            if response.status_code != 200: return []
            
            data = response.json()
            collections = data.get('Collections', [])
            
            lists = []
            for c in collections:
                lists.append({
                    "id": c.get('guid'),
                    "name": c.get('title', 'Senza nome'),
                })
            
            log("ICLOUD_LISTS_FOUND", count=len(lists))
            return lists
        except Exception as e:
            log("ICLOUD_LIST_FETCH_ERROR", error=str(e), level="ERROR")
            return []

    def get_reminders(self, list_name: str = "Promemoria") -> List[Dict[str, Any]]:
        """Recupera promemoria bypassando i bug di parsing delle date di Apple."""
        api = self._get_api()
        if not api: return []
        
        try:
            # Bypass crash: fetch raw data
            host = api._webservices.get('reminders', {}).get('url')
            if not host: return []
            
            url = f"{host}/rd/startup"
            response = api.session.get(url, params=api.params)
            if response.status_code != 200: return []
            
            data = response.json()
            collections = data.get('Collections', [])
            all_reminders = data.get('Reminders', [])
            
            # Trova GUID della lista target
            target_guid = None
            
            # 1. Tentativo: match esatto GUID (ID)
            for c in collections:
                if c.get('guid') == list_name:
                    target_guid = c.get('guid')
                    break
            
            # 2. Tentativo: fuzzy matching sul nome
            if not target_guid:
                list_name_lower = list_name.lower()
                for c in collections:
                    title = c.get('title', '').lower()
                    if list_name_lower in title or title in list_name_lower:
                        target_guid = c.get('guid')
                        break
            
            # 3. Fallback: Promemoria default
            if not target_guid and collections:
                for c in collections:
                    if "promemoria" in c.get('title', '').lower():
                        target_guid = c.get('guid')
                        break
                if not target_guid: target_guid = collections[0].get('guid')

            # Filtra i promemoria per questa lista
            reminders = []
            for r in all_reminders:
                if r.get('pGuid') == target_guid:
                    # Escludiamo i completati (se hanno una data di completamento)
                    if r.get('completedDate'): continue
                    
                    reminders.append({
                        "summary": r.get('title', 'Senza titolo'),
                        "status": "not_completed",
                        "due": None # Le date sono il problema, per ora le ignoriamo o le formattiamo con cautela
                    })
            
            log("ICLOUD_REMINDERS_FETCH", count=len(reminders), list=list_name)
            return reminders
        except Exception as e:
            log("ICLOUD_REMINDERS_FETCH_ERROR", error=str(e), level="ERROR")
            return []

# Istanza globale
icloud_service = ICloudService()
