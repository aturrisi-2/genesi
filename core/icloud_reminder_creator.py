import caldav, vobject
from datetime import datetime
import logging, os, uuid
from core.log import log

logger = logging.getLogger(__name__)

class ICloudReminderCreator:
    def __init__(self, user: str, password: str):
        self.client = caldav.DAVClient(
            url="https://caldav.icloud.com",
            username=user, 
            password=password
        )
    
    async def create_reminder(self, title: str, due_date: datetime, notes: str = ""):
        """Crea VTODO su calendario Promemoria"""
        try:
            principal = self.client.principal()
            calendars = principal.calendars()
            
            # Trova calendario "Promemoria"
            reminder_cal = None
            for cal in calendars:
                name = getattr(cal, 'name', '').lower()
                if any(x in name for x in ["promemoria", "reminders"]):
                    reminder_cal = cal
                    break
            
            if not reminder_cal:
                # Fallback: cerca il primo che supporta VTODO se possibile
                # o semplicemente usa il primo calendario disponibile
                if calendars:
                    reminder_cal = list(calendars.values())[0] if isinstance(calendars, dict) else calendars[0]
            
            if not reminder_cal:
                log("ICLOUD_REMINDER_NO_CAL", level="ERROR")
                return False
            
            # Crea VTODO
            cal_vobj = vobject.iCalendar()
            vtodo = cal_vobj.add('vtodo')
            vtodo.add('summary').value = title
            vtodo.add('uid').value = str(uuid.uuid4()).upper()
            vtodo.add('dtstamp').value = datetime.utcnow()
            
            if due_date:
                # Per Apple Reminders, la data di scadenza è 'due'
                vtodo.add('due').value = due_date
                # Alcuni server vogliono anche dtstart
                vtodo.add('dtstart').value = due_date
            
            if notes:
                vtodo.add('description').value = notes
            
            # Serialization
            ics_data = cal_vobj.serialize()
            
            # Salva su iCloud
            log("ICLOUD_REMINDER_SENDING", title=title, list=getattr(reminder_cal, 'name', 'Unknown'))
            
            # add_event è il metodo universale per iniettare ICS (VEVENT o VTODO)
            reminder_cal.add_event(ics_data)
            
            log("ICLOUD_REMINDER_CREATED", title=title)
            return True
            
        except Exception as e:
            log("ICLOUD_REMINDER_CREATE_FAILED", error=str(e), level="ERROR")
            return False
