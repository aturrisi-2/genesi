"""
ICLOUD SERVICE - Genesi Core
Integrazione con iCloud Reminders via CalDAV protocol.
Supporta fetch ottimizzato e creazione promemoria.
"""

import os
import logging
import datetime
import caldav
import uuid
import time
from vobject import readOne
from typing import List, Dict, Any, Optional
from core.log import log
from core.calendar_history import calendar_history

logger = logging.getLogger(__name__)

class ICloudService:
    def __init__(self, username: Optional[str] = None, password: Optional[str] = None, **kwargs):
        """
        Inizializza il servizio iCloud usando il protocollo ufficiale CalDAV.
        Richiede una 'Password specifica per le app' generata su appleid.apple.com.
        """
        self.username = username or os.environ.get("ICLOUD_USER")
        self.password = password or os.environ.get("ICLOUD_PASSWORD") or os.environ.get("ICLOUD_PASS")
        self.client = None
        log("ICLOUD_SERVICE_VERSION", version="4.0")
        self._cache_vtodo = []
        self._last_sync_vtodo = 0
        self._vtodo_lists = set() 
        self._deep_sync_done = False
        
        if self.username and self.password:
            self._connect()

    def _connect(self):
        """Stabilisce la connessione CalDAV usando l'endpoint ufficiale e un User-Agent credibile."""
        try:
            url = "https://caldav.icloud.com"
            self.client = caldav.DAVClient(
                url=url,
                username=self.username,
                password=self.password,
                timeout=60
            )
            # Simuliamo un client iOS storico per massima compatibilità
            self.client.session.headers.update({
                'User-Agent': 'iOS/15.0 (19A344) Reminders/1.0',
                'Connection': 'keep-alive'
            })
            # Ottimizzazione sessione per evitare timeout su liste lunghe
            adapter = self.client.session.get_adapter('https://')
            adapter.pool_connections = 10
            adapter.pool_maxsize = 20
            log("ICLOUD_CALDAV_CONNECT", user=self.username, endpoint="standard_masqueraded")
            return True
        except Exception as e:
            log("ICLOUD_CALDAV_CONNECT_ERROR", user=self.username, error=str(e), level="ERROR")
            return False

    def validate_credentials(self) -> bool:
        """Verifica se le credenziali sono corrette."""
        try:
            if not self.client:
                if not self._connect(): return False
            principal = self.client.principal()
            return principal is not None
        except:
            return False

    def get_events(self, days: int = 7) -> List[Dict[str, Any]]:
        """Recupera gli eventi (VEVENT) da tutte le liste di iCloud."""
        if not self.client:
            if not self._connect(): return []

        all_events = []
        try:
            principal = self.client.principal()
            calendars = principal.calendars()
            
            now = datetime.datetime.now()
            start_dt = now - datetime.timedelta(hours=1)
            end_dt = now + datetime.timedelta(days=days)
            
            for calendar in calendars:
                try:
                    name = getattr(calendar, 'name', 'Senza nome')
                    url = str(calendar.url).lower()
                    if any(x in url for x in ["inbox", "outbox", "notification"]): continue

                    events = []
                    try:
                        events = calendar.date_search(start=start_dt, end=end_dt)
                    except:
                        try: events = calendar.events()
                        except: continue

                    for event in events:
                        try:
                            v = readOne(event.data)
                            item = getattr(v, 'vevent', None)
                            if not item: continue
                            
                            summary = str(item.summary.value) if hasattr(item, 'summary') else "Senza titolo"
                            guid = str(item.uid.value) if hasattr(item, 'uid') else None
                            
                            dtstart = None
                            if hasattr(item, 'dtstart'):
                                val = item.dtstart.value
                                cmp_dt = val if isinstance(val, datetime.datetime) else datetime.datetime.combine(val, datetime.time())
                                if cmp_dt.tzinfo is None:
                                    if cmp_dt < now: continue
                                else:
                                    if cmp_dt < now.astimezone(cmp_dt.tzinfo): continue
                                dtstart = val.isoformat()

                            if not dtstart: continue

                            all_events.append({
                                "guid": guid,
                                "summary": summary,
                                "status": "pending",
                                "due": dtstart,
                                "list": name,
                                "source": "icloud",
                                "type": "event"
                            })
                        except: continue
                except: continue
            return all_events
        except:
            return []

    def get_vtodo(self, days: int = 7) -> List[Dict[str, Any]]:
        """Recupera i promemoria (VTODO) da iCloud."""
        if not self.client:
            if not self._connect(): return []

        # Cache di 5 minuti per evitare attese lunghe ad ogni domanda
        now_ts = time.time()
        if (now_ts - self._last_sync_vtodo) < 300 and self._cache_vtodo:
            log("ICLOUD_CACHE_HIT", count=len(self._cache_vtodo))
            return self._cache_vtodo

        all_todos = []
        try:
            principal = self.client.principal()
            calendars = principal.calendars()
            now = datetime.datetime.now()
            
            log("ICLOUD_SYNC_START", calendars_count=len(calendars))
            
            for calendar in calendars:
                try:
                    name = getattr(calendar, 'name', 'Senza nome')
                    
                    # OTTIMIZZAZIONE 2.9: Se abbiamo già mappato le liste, vai dritto a quelle buone
                    if self._vtodo_lists and name not in self._vtodo_lists:
                        if name.lower() not in ['promemoria', 'tasks', 'reminders']:
                            continue
                    
                    # OTTIMIZZAZIONE 2.8: Salta il calendario principale "Calendar"
                    if name.lower() in ['calendar', 'calendario']:
                        continue

                    # Controllo metadati se supportato
                    try:
                        supported = calendar.get_supported_components()
                        if supported and 'VTODO' not in supported:
                            log("ICLOUD_SKIP_CAL", name=name, reason="metadata_no_vtodo")
                            continue
                    except: pass

                    log("ICLOUD_SCANNING_LIST", name=name)

                    todos = []
                    try:
                        # STRATEGIA 2.4: Fetch brutale di TUTTI gli oggetti per evitare errore 500 del filtraggio server
                        # Molto più stabile se il server è schizzinoso sui filtri
                        todos = calendar.objects()
                        if todos:
                            log("ICLOUD_RAW_FETCH", name=name, count=len(todos))
                    except Exception as te:
                        log("ICLOUD_FETCH_ERROR", name=name, error=str(te), level="DEBUG")
                        continue
                        
                    if not todos:
                        continue
                    
                    # OTTIMIZZAZIONE 3.0: Caricamento parallelo degli oggetti (Turbo-Fetch)
                    # OTTIMIZZAZIONE 4.0: Filtriamo cosa caricare (Delta Sync)
                    from concurrent.futures import ThreadPoolExecutor
                    
                    to_load = []
                    for t in todos:
                        guid = str(t.url)
                        if not self._deep_sync_done or not calendar_history.exists(guid):
                            to_load.append(t)
                    
                    def _safe_load(t):
                        try:
                            if not hasattr(t, 'data') or not t.data:
                                t.load()
                            return t
                        except: return None

                    if to_load:
                        log("ICLOUD_DELTA_LOAD", name=name, count=len(to_load))
                        with ThreadPoolExecutor(max_workers=10) as executor:
                            list(executor.map(_safe_load, to_load))

                    skipped_completed = 0
                    skipped_past = 0
                    
                    found_in_cal = 0
                    
                    for todo in todos:
                        try:
                            guid = str(todo.url)
                            raw_data = getattr(todo, 'data', None)
                            
                            # Se non abbiamo dati e non è in cache, passiamo (potrebbe essere già caricato o fallito)
                            if not raw_data:
                                if calendar_history.exists(guid):
                                    # Recuperiamo dallo storico locale per evitare fetch
                                    hist_item = calendar_history.history["items"][guid]
                                    if hist_item.get("status", "").upper() not in ['COMPLETED', 'CANCELLED']:
                                        all_todos.append(hist_item)
                                        found_in_cal += 1
                                    continue
                                else: continue

                            # Decodifica
                            data_str = raw_data.decode('utf-8', errors='ignore') if isinstance(raw_data, bytes) else str(raw_data)
                            
                            if 'VTODO' not in data_str.upper(): continue
                            
                            v = readOne(data_str)
                            item = getattr(v, 'vtodo', getattr(v, 'VTODO', None))
                            if not item: continue
                            
                            # Estrazione dati
                            summary = str(item.summary.value) if hasattr(item, 'summary') else "Senza titolo"
                            raw_uid = str(item.uid.value) if hasattr(item, 'uid') else guid
                            status_val = str(getattr(item, 'status', 'pending')).upper()
                            
                            due_dt = None
                            if hasattr(item, 'due'): due_dt = item.due.value
                            elif hasattr(item, 'dtstart'): due_dt = item.dtstart.value
                            due_str = due_dt.isoformat() if due_dt else None

                            todo_data = {
                                "guid": raw_uid,
                                "summary": summary,
                                "status": status_val,
                                "due": due_str,
                                "list": name,
                                "source": "icloud",
                                "type": "todo",
                                "updated_at": datetime.datetime.now().isoformat()
                            }
                            
                            # PERSISTENZA STORICA (Richiesta User)
                            calendar_history.add_item(guid, todo_data)

                            # Filtro per Agenda Attiva
                            is_completed = status_val in ['COMPLETED', 'CANCELLED']
                            if is_completed:
                                skipped_completed += 1
                            else:
                                all_todos.append(todo_data)
                                found_in_cal += 1

                        except Exception as e:
                            log("ICLOUD_TODO_PARSE_ERR", error=str(e), level="DEBUG")
                            continue
                    
                    if found_in_cal > 0:
                        self._vtodo_lists.add(name)
                    
                    log("ICLOUD_CAL_SYNC_RES", name=name, found=found_in_cal, skipped_completed=skipped_completed, skipped_past=skipped_past)
                        
                except Exception as e:
                    continue
            
            # Salvataggio storico su VPS
            calendar_history.save()
            self._deep_sync_done = True 
            
            self._cache_vtodo = all_todos
            self._last_sync_vtodo = time.time()
            return all_todos
        except Exception as e:
            log("ICLOUD_VTODO_FETCH_ERR", error=str(e), level="ERROR")
            return []

    def get_all_items(self, days: int = 7) -> List[Dict[str, Any]]:
        """Cerca tutto: Eventi + Promemoria."""
        return self.get_vtodo(days) + self.get_events(days)

    def create_event(self, text: str, dt: datetime.datetime, is_todo: bool = True) -> bool:
        """Crea un nuovo elemento iCloud."""
        if not self.client:
            if not self._connect(): return False
        try:
            principal = self.client.principal()
            calendars = principal.calendars()
            target_cal = None
            for cal in calendars:
                name = getattr(cal, 'name', '').lower()
                if any(x in name for x in ["promemoria", "reminders"]):
                    target_cal = cal
                    break
            if not target_cal and calendars: target_cal = calendars[0]
            if not target_cal: return False

            import vobject
            cal_v = vobject.iCalendar()
            if is_todo:
                item = cal_v.add('vtodo')
                item.add('summary').value = text
                item.add('due').value = dt
            else:
                item = cal_v.add('vevent')
                item.add('summary').value = text
                item.add('dtstart').value = dt
                item.add('dtend').value = dt + datetime.timedelta(hours=1)
                
            item.add('uid').value = str(uuid.uuid4()).upper()
            item.add('dtstamp').value = datetime.datetime.utcnow()
            target_cal.add_event(cal_v.serialize())
            log("ICLOUD_ITEM_CREATED", type="todo" if is_todo else "event", text=text)
            return True
        except Exception as e:
            log("ICLOUD_CREATE_ERROR", error=str(e))
            return False

    def get_reminders(self, days: int = 7): return self.get_all_items(days)
    def create_reminder(self, text, dt): return self.create_event(text, dt, is_todo=True)

icloud_service = ICloudService()
