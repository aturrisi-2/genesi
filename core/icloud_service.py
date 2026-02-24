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
        self.password = password or os.environ.get("ICLOUD_PASSWORD")
        self.client = None
        
        if self.username and self.password:
            self._connect()

    def _connect(self):
        """Stabilisce la connessione CalDAV usando l'endpoint ufficiale e un User-Agent credibile."""
        try:
            url = "https://caldav.icloud.com"
            # Importante: Apple blocca o limita i client che non sembrano 'ufficiali' 
            # o che non dichiarano un User-Agent standard di un dispositivo Apple.
            self.client = caldav.DAVClient(
                url=url,
                username=self.username,
                password=self.password,
                timeout=30
            )
            # Simuliamo un client iOS/macOS per maggiore stabilità
            self.client.session.headers.update({
                'User-Agent': 'iOS/17.0 (21A329) Reminders/1.0',
                'Accept': 'text/xml',
                'Prefer': 'return=minimal'
            })
            log("ICLOUD_CALDAV_CONNECT", user=self.username, endpoint="standard_masqueraded")
            return True
        except Exception as e:
            log("ICLOUD_CALDAV_CONNECT_ERROR", user=self.username, error=str(e), level="ERROR")
            return False

    def validate_credentials(self) -> bool:
        """Verifica se le credenziali (App-Specific Password) sono corrette."""
        try:
            if not self.client:
                if not self._connect(): return False
            try:
                principal = self.client.principal()
                return principal is not None
            except Exception:
                return False
        except Exception:
            return False

    def get_events(self, days: int = 7) -> List[Dict[str, Any]]:
        """
        Recupera gli eventi (VEVENT) da tutte le liste di iCloud usando CalDAV.
        iCloud supporta VEVENT in modo molto più stabile rispetto a VTODO su alcuni endpoint.
        """
        if not self.client:
            if not self._connect(): return []

        all_events = []
        try:
            principal = self.client.principal()
            calendars = principal.calendars()
            
            now = datetime.datetime.now()
            start_dt = now - datetime.timedelta(hours=1) # Leggera tolleranza
            end_dt = now + datetime.timedelta(days=days)
            
            scanned_count = 0
            for calendar in calendars:
                try:
                    name = getattr(calendar, 'name', 'Senza nome')
                    url = str(calendar.url).lower()
                    
                    if any(x in url for x in ["inbox", "outbox", "notification"]):
                        continue

                    scanned_count += 1
                    log("ICLOUD_CALDAV_LIST_CHECK", name=name)
                    
                    # Recupera eventi (VEVENT) - RANGE FILTERED
                    events = []
                    try:
                        # iCloud supporta date_search per filtrare lato server
                        events = calendar.date_search(start=start_dt, end=end_dt)
                    except Exception as e:
                        log("ICLOUD_CALDAV_EVENTS_ERR", name=name, error=str(e))
                        # Fallback a all events se date_search fallisce
                        try: events = calendar.events()
                        except: continue

                    found_on_this_list = 0
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
                                # Saltiamo se l'evento è già passato (doppio controllo)
                                if isinstance(val, (datetime.datetime, datetime.date)):
                                    # Convert date to datetime if needed
                                    cmp_dt = val if isinstance(val, datetime.datetime) else datetime.datetime.combine(val, datetime.time())
                                    # Fix tz-naive vs tz-aware
                                    if cmp_dt.tzinfo is None:
                                        if cmp_dt < datetime.datetime.now(): continue
                                    else:
                                        if cmp_dt < datetime.datetime.now(cmp_dt.tzinfo): continue
                                        
                                    dtstart = val.isoformat()

                            if not dtstart: continue

                            all_events.append({
                                "guid": guid,
                                "summary": summary,
                                "status": "pending",
                                "due": dtstart,
                                "list": name,
                                "source": "icloud"
                            })
                            found_on_this_list += 1
                        except: continue
                    
                    if found_on_this_list > 0:
                        log("ICLOUD_CALDAV_EVENT_FOUND", name=name, count=found_on_this_list)

                    if scanned_count >= 10: break
                        
                except Exception as e: 
                    log("ICLOUD_CALDAV_LOOP_ERR", error=str(e))
                    continue

            log("ICLOUD_CALDAV_SYNC_SUCCESS", count=len(all_events), user=self.username)
            return all_events

        except Exception as e:
            log("ICLOUD_CALDAV_FETCH_ERROR", user=self.username, error=str(e), level="ERROR")
            return []

    def create_event(self, text: str, dt: datetime.datetime) -> bool:
        """Crea un nuovo evento (VEVENT) direttamente su iCloud."""
        if not self.client:
            if not self._connect(): return False
            
        try:
            principal = self.client.principal()
            calendars = principal.calendars()
            
            # Trova un calendario adatto (che non sia una lista di promemoria se possibile)
            target_cal = None
            for cal in calendars:
                name = getattr(cal, 'name', '').lower()
                if "promemoria" not in name and "reminders" not in name:
                    url = str(cal.url).lower()
                    if not any(x in url for x in ["inbox", "outbox", "notification"]):
                        target_cal = cal
                        break
            
            if not target_cal and calendars:
                target_cal = calendars[0]
                
            if not target_cal: return False

            import vobject
            cal = vobject.iCalendar()
            cal.add('prodid').value = "-//Apple Inc.//Mac OS X 10.15.7//EN"
            
            event = cal.add('vevent')
            event.add('uid').value = str(uuid.uuid4()).upper()
            event.add('summary').value = text
            
            now = datetime.datetime.utcnow()
            event.add('dtstamp').value = now
            event.add('dtstart').value = dt
            event.add('dtend').value = dt + datetime.timedelta(hours=1)
            
            ical_str = cal.serialize()
            
            log("ICLOUD_EVENT_SENDING", list=getattr(target_cal, 'name', 'Unknown'), text=text)
            target_cal.add_event(ical_str)
            log("ICLOUD_EVENT_CREATED", text=text, list=getattr(target_cal, 'name', 'Unknown'))
            return True
        except Exception as e:
            log("ICLOUD_EVENT_CREATE_ERROR", error=str(e), level="ERROR")
            return False

    # Manteniamo compatibilità per ora o facciamo alias
    def get_reminders(self, *args, **kwargs):
        return self.get_events()
    
    def create_reminder(self, text, dt, *args, **kwargs):
        return self.create_event(text, dt)

# Istanza globale
icloud_service = ICloudService()
