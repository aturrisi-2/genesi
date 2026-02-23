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

# --- MONKEYPATCH DATETIME ---
# Apple a volte manda date come YYYYMMDD in un campo che la libreria legge come 'anno'.
# Intercettiamo queste chiamate e ripariamo la data al volo per evitare "year out of range".
original_datetime = datetime.datetime
original_date = datetime.date

class PatchedDatetime(original_datetime):
    def __new__(cls, *args, **kwargs):
        new_args = list(args)
        if new_args:
            year = new_args[0]
            if year > 9999: # Caso YYYYMMDD impaccato
                y = year // 10000
                m = (year % 10000) // 100
                d = year % 100
                if len(new_args) > 1:
                    new_args[0] = y
                    if len(new_args) > 1: new_args[1] = m
                    if len(new_args) > 2: new_args[2] = d
                else:
                    new_args = [y, m, d]
            
            # Clamping per ore/minuti/secondi fuori range
            if len(new_args) > 3 and (new_args[3] < 0 or new_args[3] > 23): new_args[3] = 0
            if len(new_args) > 4 and (new_args[4] < 0 or new_args[4] > 59): new_args[4] = 0
            if len(new_args) > 5 and (new_args[5] < 0 or new_args[5] > 59): new_args[5] = 0

        try:
            # IMPORTANTE: Ritorniamo un'istanza della classe ORIGINALE
            # Questo evita errori di tipo in librerie come SQLAlchemy/SQLite
            return original_datetime.__new__(original_datetime, *tuple(new_args), **kwargs)
        except:
            return original_datetime.__new__(original_datetime, 2024, 1, 1)

class PatchedDate(original_date):
    def __new__(cls, *args, **kwargs):
        new_args = list(args)
        if new_args:
            year = new_args[0]
            if year > 9999:
                y = year // 10000
                m = (year % 10000) // 100
                d = year % 100
                if len(new_args) > 1:
                    new_args[0] = y
                    if len(new_args) > 1: new_args[1] = m
                    if len(new_args) > 2: new_args[2] = d
                else:
                    new_args = [y, m, d]
        try:
            return original_date.__new__(original_date, *tuple(new_args), **kwargs)
        except:
            return original_date.__new__(original_date, 2024, 1, 1)

# Applica la patch globale all'interno del processo Genesi
datetime.datetime = PatchedDatetime
datetime.date = PatchedDate
# --- FINE PATCH ---

class ICloudService:
    def __init__(self, username: Optional[str] = None, password: Optional[str] = None, cookie_directory: Optional[str] = None):
        self.username = username or os.environ.get("ICLOUD_USER")
        self.password = password or os.environ.get("ICLOUD_PASSWORD")
        self.cookie_directory = cookie_directory or f"memory/icloud_sessions/default"
        self._api = None
        log("ICLOUD_SERVICE_INIT", user=self.username)

    def _get_client(self):
        """Inizializza il client PyiCloud con gestione sessione."""
        if self._api:
            return self._api

        if not self.username or not self.password:
            log("ICLOUD_AUTH_MISSING", user=self.username, level="ERROR")
            return None
            
        try:
            # Assicuriamoci che la cartella dei cookie esista
            os.makedirs(self.cookie_directory, exist_ok=True)
            
            try:
                api = PyiCloudService(self.username, self.password, cookie_directory=self.cookie_directory)
            except Exception as e:
                # Se fallisce con Service Unavailable o SRP error, proviamo a pulire i cookie e riprovare una volta
                err_str = str(e).lower()
                if "service" in err_str or "srp" in err_str or "unavailable" in err_str:
                    log("ICLOUD_SESSION_CLEANUP", user=self.username, reason="auth_failure_retry")
                    import shutil
                    if os.path.exists(self.cookie_directory):
                        for filename in os.listdir(self.cookie_directory):
                            file_path = os.path.join(self.cookie_directory, filename)
                            try:
                                if os.path.isfile(file_path): os.unlink(file_path)
                            except: pass
                    # Secondo tentativo
                    api = PyiCloudService(self.username, self.password, cookie_directory=self.cookie_directory)
                else:
                    raise e
            
            # Se richiede 2FA, logghiamo la necessità
            if api.requires_2fa:
                log("ICLOUD_2FA_REQUIRED", user=self.username, level="WARNING")
            
            self._api = api
            log("ICLOUD_API_CLIENT_INIT", user=self.username)
            return api
        except Exception as e:
            error_msg = str(e)
            if "Service Unavailable" in error_msg:
                error_msg = "Apple ha bloccato la richiesta (Service Unavailable). Riprova tra 5 minuti."
            log("ICLOUD_API_INIT_ERROR", user=self.username, error=error_msg, level="ERROR")
            raise Exception(error_msg)

    def validate_2fa(self, code: str) -> bool:
        """Valida il codice 2FA inviato dall'utente."""
        api = self._get_client()
        if not api: return False
        
        if not api.requires_2fa:
            return True
            
        try:
            result = api.validate_2fa_code(code)
            log("ICLOUD_2FA_VALIDATION", user=self.username, success=result)
            return result
        except Exception as e:
            log("ICLOUD_2FA_VALIDATION_ERROR", user=self.username, error=str(e), level="ERROR")
            return False

    def get_reminders_lists(self) -> List[Dict[str, Any]]:
        """Recupera le liste di promemoria disponibili."""
        api = self._get_client()
        if not api: return []
        
        try:
            collections = api.reminders.collections
            lists = []
            for name, coll in collections.items():
                lists.append({
                    "id": name,
                    "name": name
                })
            return lists
        except Exception as e:
            log("ICLOUD_LIST_FETCH_ERROR", user=self.username, error=str(e), level="ERROR")
            return []

    def get_reminders(self, list_name: str = "Promemoria") -> List[Dict[str, Any]]:
        """Recupera i promemoria filtrando quelli completati e riparando le date."""
        api = self._get_client()
        if not api: return []
        
        try:
            log("ICLOUD_SYNC_START", user=self.username, target_list=list_name)
            
            try:
                api.reminders.refresh()
            except Exception as refresh_err:
                log("ICLOUD_REFRESH_WARNING", error=str(refresh_err), level="WARNING")

            collections = api.reminders.collections
            all_reminders = []
            
            # Se viene indicata una lista specifica, cerchiamo solo quella
            target_names = [list_name] if list_name in collections else collections.keys()

            for name in target_names:
                coll = collections.get(name)
                if not coll: continue
                
                tasks = coll.get('reminders') or coll.get('tasks') or []
                
                for task in tasks:
                    try:
                        # 1. Filtro completati
                        status = (task.get('status') or 'NEEDS-ACTION').upper()
                        percent = task.get('percent_complete', 0)
                        is_completed = (status in ["COMPLETED", "CANCELLED"] or 
                                       percent == 100 or 
                                       task.get('completed_date') is not None)
                        
                        if is_completed:
                            continue

                        # 2. Estrazione dati
                        guid = task.get('guid')
                        title = task.get('title') or task.get('summary') or "Senza titolo"
                        
                        # 3. Gestione Data Scadenza
                        due = None
                        due_data = task.get('due_date')
                        
                        if due_data:
                            if isinstance(due_data, list) and len(due_data) >= 3:
                                try:
                                    dt_args = list(due_data[:6])
                                    while len(dt_args) < 6: dt_args.append(0)
                                    ts = datetime.datetime(*dt_args)
                                    due = ts.isoformat()
                                except: pass
                            elif isinstance(due_data, (int, float)):
                                try:
                                    ts = datetime.datetime.fromtimestamp(due_data/1000 if due_data > 10**10 else due_data)
                                    due = ts.isoformat()
                                except: pass

                        all_reminders.append({
                            "guid": guid,
                            "summary": title,
                            "status": "pending",
                            "due": due,
                            "list": name
                        })
                    except: continue

            log("ICLOUD_SYNC_SUCCESS", count=len(all_reminders), user=self.username)
            return all_reminders
                
        except Exception as e:
            log("ICLOUD_FETCH_ERROR", user=self.username, error=str(e), level="ERROR")
            return []

# Istanza per compatibilità
icloud_service = ICloudService()
