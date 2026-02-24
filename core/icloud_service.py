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

    def get_reminders(self, list_name: str = "Reminders") -> List[Dict[str, Any]]:
        """
        Recupera i promemoria da tutte le liste di iCloud usando CalDAV.
        Tenta il metodo veloce 'todos()' prima di passare alla scansione manuale.
        """
        if not self.client:
            if not self._connect(): return []

        all_reminders = []
        try:
            principal = self.client.principal()
            calendars = principal.calendars()
            
            # PERFORMANCE BOOST: Cerca prima la lista principale
            priority_calendars = []
            other_calendars = []
            for cal in calendars:
                name = getattr(cal, 'name', '').lower()
                if any(x in name for x in ["promemoria", "reminders"]):
                    priority_calendars.append(cal)
                else:
                    other_calendars.append(cal)
            
            # Processa prima le prioritarie, poi le altre (limitando la scansione totale)
            ordered_cals = priority_calendars + other_calendars
            scanned_count = 0

            for calendar in ordered_cals:
                try:
                    name = getattr(calendar, 'name', 'Senza nome')
                    url = str(calendar.url).lower()
                    
                    if any(x in url for x in ["inbox", "outbox", "notification"]):
                        continue

                    scanned_count += 1
                    log("ICLOUD_CALDAV_LIST_CHECK", name=name)
                    
                    # REPORT query limitata per prestazioni
                    todos = calendar.todos(include_completed=False)
                    found_on_this_list = 0
                    for todo in todos:
                        try:
                            v = readOne(todo.data)
                            task = getattr(v, 'vtodo', None)
                            if not task: continue
                            
                            status = str(getattr(task, 'status', '')).upper()
                            if status in ['COMPLETED', 'CANCELLED'] or hasattr(task, 'completed'):
                                continue
                            
                            summary = str(task.summary.value) if hasattr(task, 'summary') else "Senza titolo"
                            guid = str(task.uid.value) if hasattr(task, 'uid') else None
                            
                            due_iso = None
                            # Fallback chain for due date: DUE -> DTSTART -> created
                            for attr in ['due', 'dtstart', 'created']:
                                if hasattr(task, attr):
                                    val = getattr(task, attr).value
                                    if isinstance(val, (datetime.datetime, datetime.date)):
                                        due_iso = val.isoformat()
                                        break

                            all_reminders.append({
                                "guid": guid,
                                "summary": summary,
                                "status": "pending",
                                "due": due_iso,
                                "list": name
                            })
                            found_on_this_list += 1
                        except: continue
                    
                    # PERFORMANCE EXIT: Se abbiamo trovato dati nella lista prioritaria, fermati subito
                    if any(x in name.lower() for x in ["promemoria", "reminders"]) and found_on_this_list > 0:
                        log("ICLOUD_CALDAV_PRIORITY_EXIT", name=name, count=found_on_this_list)
                        break
                    
                    if scanned_count >= 5: # Massimo 5 liste totali se non prioritarie
                        break
                        
                except: continue

            log("ICLOUD_CALDAV_SYNC_SUCCESS", count=len(all_reminders), user=self.username)
            return all_reminders

        except Exception as e:
            log("ICLOUD_CALDAV_FETCH_ERROR", user=self.username, error=str(e), level="ERROR")
            return []

    def create_reminder(self, text: str, due_dt: Optional[datetime.datetime] = None, list_name: str = "Promemoria") -> bool:
        """Crea un nuovo promemoria direttamente su iCloud."""
        if not self.client:
            if not self._connect(): return False
            
        try:
            principal = self.client.principal()
            calendars = principal.calendars()
            
            # Trova la lista giusta (default: 'Promemoria')
            target_cal = None
            for cal in calendars:
                cal_name = getattr(cal, 'name', '').lower()
                if list_name.lower() in cal_name:
                    target_cal = cal
                    break
            
            if not target_cal and calendars:
                # Cerca una lista generica che non sia di sistema
                for cal in calendars:
                    url = str(cal.url).lower()
                    if not any(x in url for x in ["inbox", "outbox", "notification"]):
                        target_cal = cal
                        break
                
            if not target_cal: return False

            # Genera UID e timestamp (FORMATO ICAL CORRETTO)
            uid = str(uuid.uuid4()).upper()
            now_utc = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            
            # Formatta iCalendar
            ical = [
                "BEGIN:VCALENDAR",
                "VERSION:2.0",
                "PRODID:-//Genesi AI//NONSGML v1.0//EN",
                "BEGIN:VTODO",
                f"UID:{uid}",
                f"DTSTAMP:{now_utc}",
                f"SUMMARY:{text}"
            ]
            
            if due_dt:
                # Per iCloud, se non specifichiamo TZID, usiamo UTC (Z)
                # Oppure usiamo floating time (senza Z) se vogliamo che appaia all'ora locale del dispositivo
                dt_str = due_dt.strftime("%Y%m%dT%H%M%S")
                # iCloud preferisce DTSTART e DUE coerenti
                ical.append(f"DTSTART:{dt_str}")
                ical.append(f"DUE:{dt_str}")
            else:
                ical.append(f"DTSTART:{now_utc}")
                
            ical.append("END:VTODO")
            ical.append("END:VCALENDAR")
            
            target_cal.add_todo("\n".join(ical))
            log("ICLOUD_REMINDER_CREATED", text=text, list=getattr(target_cal, 'name', 'Unknown'))
            return True
        except Exception as e:
            log("ICLOUD_REMINDER_CREATE_ERROR", error=str(e), level="ERROR")
            return False

# Istanza globale
icloud_service = ICloudService()
