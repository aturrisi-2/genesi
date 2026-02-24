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
        self.password = password or os.environ.get("ICLOUD_PASSWORD") or os.environ.get("ICLOUD_PASS")
        self.client = None
        
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
            # Simuliamo un client iOS/macOS per maggiore stabilità
            self.client.session.headers.update({
                'User-Agent': 'iOS/17.0 (21A329) Reminders/1.0',
                'Accept': 'text/xml',
                'Prefer': 'return=minimal',
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

        all_todos = []
        try:
            principal = self.client.principal()
            calendars = principal.calendars()
            now = datetime.datetime.now()
            
            log("ICLOUD_SYNC_START", calendars_count=len(calendars))
            
            for calendar in calendars:
                try:
                    name = getattr(calendar, 'name', 'Senza nome')
                    # Logghiamo ogni calendario per debug
                    log("ICLOUD_SCANNING_LIST", name=name)
                    
                    todos = []
                    try:
                        todos = calendar.todos()
                    except:
                        # Molti calendari (es: quelli degli eventi) non supportano .todos()
                        continue
                        
                    if not todos:
                        log("ICLOUD_LIST_EMPTY", name=name)
                        continue
                    
                    found_in_cal = 0
                    for todo in todos:
                        try:
                            v = readOne(todo.data)
                            # Supporta sia vtodo che VTODO
                            item = getattr(v, 'vtodo', getattr(v, 'VTODO', None))
                            if not item: continue
                            
                            # Filtro completati
                            status = getattr(item, 'status', None)
                            if status and str(status.value).upper() in ['COMPLETED', 'CANCELLED']: 
                                continue
                            
                            summary = str(item.summary.value) if hasattr(item, 'summary') else "Senza titolo"
                            guid = str(item.uid.value) if hasattr(item, 'uid') else None
                            
                            due_dt = None
                            if hasattr(item, 'due'): due_dt = item.due.value
                            elif hasattr(item, 'dtstart'): due_dt = item.dtstart.value
                            
                            if due_dt:
                                # Filtro temporale (7 giorni default)
                                cmp_dt = due_dt if isinstance(due_dt, datetime.datetime) else datetime.datetime.combine(due_dt, datetime.time())
                                if cmp_dt.tzinfo is None:
                                    if cmp_dt < now - datetime.timedelta(days=1): continue
                                else:
                                    now_tz = now.astimezone(cmp_dt.tzinfo)
                                    if cmp_dt < now_tz - datetime.timedelta(days=1): continue
                                due_str = due_dt.isoformat()
                            else:
                                due_str = None

                            all_todos.append({
                                "guid": guid,
                                "summary": summary,
                                "status": "pending",
                                "due": due_str,
                                "list": name,
                                "source": "icloud",
                                "type": "todo"
                            })
                            found_in_cal += 1
                        except Exception as e:
                            log("ICLOUD_TODO_PARSE_ERR", error=str(e), level="DEBUG")
                            continue
                    
                    if found_in_cal > 0:
                        log("ICLOUD_CAL_SYNCED", name=name, count=found_in_cal)
                        
                except Exception as e:
                    # Molti calendari non supportano VTODO, ignoriamo silenziosamente
                    continue
                    
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
