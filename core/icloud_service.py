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
        self._api = None
        log("ICLOUD_SERVICE_INIT", user=self.username)

    def _get_api(self):
        """Inizializza l'interfaccia pyicloud con gestione 2FA e sessione isolata."""
        if self._api:
            return self._api
            
        if not self.username or not self.password:
            log("ICLOUD_AUTH_MISSING", user=self.username, level="ERROR")
            return None
            
        try:
            from pyicloud import PyiCloudService
            # Uso directory dedicata per sessione (multi-utente)
            self._api = PyiCloudService(
                self.username, 
                self.password, 
                cookie_directory=self.cookie_directory
            )
            
            if self._api.requires_2fa:
                log("ICLOUD_2FA_REQUIRED", user=self.username, level="WARNING")
                return None
                
            log("ICLOUD_WEB_AUTH_SUCCESS", user=self.username)
            return self._api
        except Exception as e:
            log("ICLOUD_WEB_AUTH_ERROR", user=self.username, error=str(e), level="ERROR")
            return None

    def authenticate_with_2fa(self, code: str) -> bool:
        """Valida il codice 2FA per l'utente corrente."""
        api = self._get_api()
        if not api: return False
        
        try:
            result = api.validate_2fa_code(code)
            if result:
                log("ICLOUD_2FA_SUCCESS", user=self.username)
                return True
            else:
                log("ICLOUD_2FA_FAILED", user=self.username, level="ERROR")
                return False
        except Exception as e:
            log("ICLOUD_2FA_ERROR", user=self.username, error=str(e), level="ERROR")
            return False

    def get_reminders_lists(self) -> List[Dict[str, Any]]:
        """Recupera le liste usando il metodo Raw Web."""
        api = self._get_api()
        if not api: return []
        
        try:
            # Bypass crash: fetch raw collections
            host = None
            if hasattr(api, '_webservices'):
                host = api._webservices.get('reminders', {}).get('url')
            
            if not host:
                log("ICLOUD_SERVICE_URL_NOT_FOUND", user=self.username, level="ERROR")
                return []
            
            url = f"{host}/rd/startup"
            response = api.session.get(url, params=api.params)
            if response.status_code != 200: 
                log("ICLOUD_HTTP_ERROR", status=response.status_code, user=self.username)
                return []
            
            data = response.json()
            collections = data.get('Collections', [])
            
            lists = []
            for c in collections:
                lists.append({
                    "id": c.get('guid'),
                    "name": c.get('title', 'Senza nome'),
                })
            
            log("ICLOUD_LISTS_FOUND", count=len(lists), user=self.username)
            return lists
        except Exception as e:
            log("ICLOUD_LIST_FETCH_ERROR", user=self.username, error=str(e), level="ERROR")
            return []

    def get_reminders(self, list_name: str = "Promemoria") -> List[Dict[str, Any]]:
        """Recupera promemoria bypassando i bug di parsing delle date di Apple."""
        api = self._get_api()
        if not api: return []
        
        try:
            # Bypass crash: fetch raw data
            host = None
            if hasattr(api, '_webservices'):
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
                    title = (c.get('title') or '').lower()
                    if list_name_lower in title or title in list_name_lower:
                        target_guid = c.get('guid')
                        break
            
            # 3. Fallback: Promemoria default
            if not target_guid and collections:
                for c in collections:
                    if "promemoria" in (c.get('title') or '').lower():
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
                        "due": None 
                    })
            
            log("ICLOUD_REMINDERS_FETCH", count=len(reminders), list=list_name, user=self.username)
            return reminders
        except Exception as e:
            log("ICLOUD_REMINDERS_FETCH_ERROR", user=self.username, error=str(e), level="ERROR")
            return []

# Istanza per compatibilità (fallback su env se non specificato)
icloud_service = ICloudService()
