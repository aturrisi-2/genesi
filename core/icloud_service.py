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
        log("ICLOUD_SERVICE_VERSION", version="5.0.4")
        self._cache_vtodo = []
        self._last_sync_vtodo = 0
        self._cache_events = []
        self._last_sync_events = 0
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
                timeout=15
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
        except Exception:
            return False

    def get_events(self, days: int = 7, force_sync: bool = False) -> List[Dict[str, Any]]:
        """Recupera gli eventi (VEVENT) dai calendari iCloud. Salta i calendari VTODO-only (Promemoria)."""
        if not self.client:
            if not self._connect(): return []

        now_ts = time.time()
        if not force_sync and (now_ts - self._last_sync_events) < 300 and self._cache_events:
            log("ICLOUD_EVENTS_CACHE_HIT", count=len(self._cache_events))
            return self._cache_events

        all_events = []
        try:
            principal = self.client.principal()
            calendars = principal.calendars()

            now = datetime.datetime.now()
            start_dt = now - datetime.timedelta(hours=1)
            end_dt = now + datetime.timedelta(days=days)

            log("ICLOUD_EVENTS_SYNC_START")
            for calendar in calendars:
                try:
                    name = getattr(calendar, 'name', 'Senza nome')
                    url = str(calendar.url).lower()
                    if any(x in url for x in ["inbox", "outbox", "notification"]): continue

                    # Skip calendari che supportano solo VTODO (Promemoria/Reminders)
                    try:
                        supported = calendar.get_supported_components()
                        if supported and 'VEVENT' not in supported:
                            log("ICLOUD_EVENTS_SKIP_CAL", name=name, reason="vtodo_only")
                            continue
                    except Exception:
                        pass  # Se non riesce a leggere i componenti, prova comunque

                    events = []
                    try:
                        events = calendar.date_search(start=start_dt, end=end_dt)
                    except Exception:
                        try: events = calendar.events()
                        except Exception: continue

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
                        except Exception: continue
                except Exception: continue
            self._cache_events = all_events
            self._last_sync_events = time.time()
            log("ICLOUD_EVENTS_SYNC_DONE", count=len(all_events))
            return all_events
        except Exception:
            return []

    def get_vtodo(self, days: int = 7, force_sync: bool = False) -> List[Dict[str, Any]]:
        """Fetch VTODOs con Delta Sync migliorato (v4.8)."""
        if not self.username or not self.password: return []

        now_ts = time.time()
        # Cache di 5 minuti per la lista rapida, ma forziamo se richiesto
        if not force_sync and (now_ts - self._last_sync_vtodo) < 300 and self._cache_vtodo:
            log("ICLOUD_CACHE_HIT", count=len(self._cache_vtodo))
            return self._cache_vtodo

        # Ogni 15 minuti forziamo un deep sync per beccare i cambiamenti di stato
        is_periodic_deep = (now_ts - self._last_sync_vtodo) > 900
        if is_periodic_deep:
            log("ICLOUD_PERIODIC_DEEP_SYNC")
            self._deep_sync_done = False

        all_todos = []
        if not self.client:
            if not self._connect(): return []
            
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

                    try:
                        supported = calendar.get_supported_components()
                        log("ICLOUD_SCANNING_LIST", name=name, url=str(calendar.url), supports=supported)
                        if supported and 'VTODO' not in supported:
                            log("ICLOUD_SKIP_CAL", name=name, reason="metadata_no_vtodo")
                            continue
                    except Exception:
                        log("ICLOUD_SCANNING_LIST", name=name, url=str(calendar.url), supports="unknown")

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
                        # OTTIMIZZAZIONE v4.9: Carichiamo tutto per ora per evitare item obsoleti
                        # (Il collo di bottiglia è lo stato COMPLETED che cambia sul cell)
                        to_load.append(t)
                    
                    def _safe_load(t):
                        try:
                            if not hasattr(t, 'data') or not t.data:
                                t.load()
                            return t
                        except Exception:
                            return None

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

    def get_all_items(self, days: int = 7, force_sync: bool = False) -> List[Dict[str, Any]]:
        """Ritorna solo eventi del Calendario (VEVENT). I Promemoria (VTODO) non vengono più sincronizzati."""
        return self.get_events(days, force_sync)

    def create_event(self, text: str, dt: datetime.datetime, is_todo: bool = False) -> bool:
        """Crea un nuovo elemento iCloud con Auto-Reconnect (v4.3)."""
        for attempt in range(2):
            try:
                if not self.client or attempt > 0:
                    if not self._connect(): continue
                
                principal = self.client.principal()
                calendars = principal.calendars()
                target_cal = None
                target_name = "None"
                matching_component = 'VTODO' if is_todo else 'VEVENT'
                
                best_match = None
                all_cals_info = []
                for cal in calendars:
                    try:
                        supported = cal.get_supported_components()
                        if not supported: continue
                        
                        can_do = matching_component in supported
                        name = getattr(cal, 'name', 'Unnamed').lower()
                        all_cals_info.append(f"{name}({supported})")
                        
                        if can_do:
                            # Priorità per nome
                            keywords = ["promemoria", "tasks", "reminders"] if is_todo else ["calendar", "calendario", "home", "casa", "lavoro", "work"]
                            if any(x in name for x in keywords):
                                if not best_match or any(x in name for x in ["home", "casa", "promemoria"]): # Prio alta
                                    best_match = cal
                                    target_name = name
                            if not best_match:
                                best_match = cal
                                target_name = name
                    except Exception: pass

                log("ICLOUD_AVAILABLE_CALENDARS", count=len(calendars), lists=all_cals_info)
                
                target_cal = best_match
                if not target_cal and calendars: 
                    target_cal = calendars[0]
                    target_name = getattr(target_cal, 'name', 'Default')
                
                if not target_cal: return False
                log("ICLOUD_TARGET_CALENDAR", name=target_name, type=matching_component, url=str(target_cal.url))

                import vobject
                cal_v = vobject.iCalendar()
                
                if is_todo:
                    item = cal_v.add('vtodo')
                    item.add('summary').value = text
                    
                    # iCloud fix: vobject e tz aware 
                    if dt:
                        if hasattr(dt, 'tzinfo') and dt.tzinfo:
                            dt = dt.replace(tzinfo=None)

                        item.add('due').value = dt
                        item.add('dtstart').value = dt
                        
                    item.add('priority').value = '5' 
                    item.add('status').value = 'NEEDS-ACTION'
                    
                    # Metadata per Apple Reminders
                    now_utc = datetime.datetime.utcnow()
                    item.add('created').value = now_utc
                    item.add('last-modified').value = now_utc
                    item.add('description').value = text
                    
                    alarm = item.add('valarm')
                    alarm.add('action').value = 'DISPLAY'
                    alarm.add('description').value = text
                    alarm.add('trigger').value = datetime.timedelta(minutes=0)
                else:
                    item = cal_v.add('vevent')
                    item.add('summary').value = text
                    
                    # VEVENT richiede date obbligatorie
                    event_dt = dt or datetime.datetime.now()
                    if hasattr(event_dt, 'tzinfo') and event_dt.tzinfo:
                        event_dt = event_dt.replace(tzinfo=None)
                        
                        
                    item.add('dtstart').value = event_dt
                    item.add('dtend').value = event_dt + datetime.timedelta(hours=1)
                    item.add('status').value = 'CONFIRMED'
                    item.add('transp').value = 'OPAQUE'
                    item.add('priority').value = '5'
                    
                # Generazione ID unico per Apple
                uid = str(uuid.uuid4()).lower()
                item.add('uid').value = uid
                item.add('dtstamp').value = datetime.datetime.utcnow()
                if not hasattr(cal_v, 'prodid'):
                    cal_v.add('prodid').value = '-//Genesi Assistant//Official//IT'

                # Apple Reminders preferisce VCALENDAR 2.0 pulito
                v_str = cal_v.serialize()
                if isinstance(v_str, bytes): v_str = v_str.decode('utf-8')
                
                resp = target_cal.add_event(v_str)
                log("ICLOUD_CREATE_RESULT", uid=uid, success=bool(resp))
                
                # Cache Injection immediata per reattività (v4.9)
                new_item = {
                    "guid": uid,
                    "summary": text,
                    "status": "NEEDS-ACTION",
                    "due": dt.isoformat() if dt else None, # Use dt.isoformat() if dt is not None
                    "list": target_name,
                    "source": "icloud",
                    "type": "todo" if is_todo else "event",
                    "updated_at": datetime.datetime.now().isoformat()
                }
                if is_todo: self._cache_vtodo.append(new_item)
                else: self._cache_events.append(new_item)
                
                calendar_history.add_item(uid, new_item)
                calendar_history.save()

                log("ICLOUD_ITEM_CREATED", type="todo" if is_todo else "event", text=text, uid=uid)
                return uid  # ritorna UID (stringa) — retrocompatibile con bool check
            except Exception as e:
                log("ICLOUD_CREATE_RETRY", attempt=attempt+1, error=str(e))
                if attempt == 1:
                    log("ICLOUD_CREATE_ERROR", error=str(e), level="ERROR")
                    return None
        return None

    def delete_item_by_uid(self, uid: str, is_todo: bool = False) -> bool:
        """
        Elimina un evento/VTODO da iCloud CalDAV per UID.
        Itera tutti i calendari finché non trova e cancella l'oggetto.
        """
        try:
            self._connect()
            principal = self.client.principal()
            for calendar in principal.calendars():
                try:
                    if is_todo:
                        obj = calendar.todo_by_uid(uid)
                    else:
                        obj = calendar.event_by_uid(uid)
                    obj.delete()
                    # Rimuovi dalla cache
                    self._cache_vtodo = [x for x in self._cache_vtodo if x.get("guid") != uid]
                    self._cache_events = [x for x in self._cache_events if x.get("guid") != uid]
                    log("ICLOUD_ITEM_DELETED", uid=uid, type="todo" if is_todo else "event")
                    return True
                except Exception:
                    continue
            log("ICLOUD_ITEM_DELETE_NOT_FOUND", uid=uid)
            return False
        except Exception as e:
            log("ICLOUD_DELETE_ERROR", uid=uid, error=str(e))
            return False

    def delete_items_by_text(self, text: str, is_todo: bool = True) -> int:
        """
        Cerca e cancella VTODO/VEVENT il cui SUMMARY contiene `text`.
        Ritorna il numero di elementi cancellati.
        """
        if not text or not text.strip():
            return 0
        search = text.strip().lower()
        deleted_count = 0
        try:
            self._connect()
            principal = self.client.principal()
            for calendar in principal.calendars():
                try:
                    objs = calendar.todos() if is_todo else calendar.events()
                    for obj in objs:
                        try:
                            summary = ""
                            try:
                                vc = readOne(obj.data)
                                comp = vc.vtodo if is_todo else vc.vevent
                                summary = str(comp.summary.value)
                            except Exception:
                                pass
                            if search in summary.lower():
                                obj.delete()
                                deleted_count += 1
                                log("ICLOUD_ITEM_DELETED_BY_TEXT", text=text, summary=summary, type="todo" if is_todo else "event")
                        except Exception:
                            continue
                except Exception:
                    continue
            return deleted_count
        except Exception as e:
            log("ICLOUD_DELETE_BY_TEXT_ERROR", text=text, error=str(e))
            return 0

    def get_reminders(self, days: int = 7): return self.get_all_items(days)
    def create_reminder(self, text, dt): return self.create_event(text, dt, is_todo=True)

icloud_service = ICloudService()
