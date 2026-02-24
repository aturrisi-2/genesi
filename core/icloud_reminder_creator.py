import caldav, vobject
from datetime import datetime
import logging, os
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
                if "promemoria" in name or "reminders" in name:
                    reminder_cal = cal
                    break
            
            if not reminder_cal:
                # Fallback to the first calendar if "Promemoria" not found
                if calendars:
                    reminder_cal = calendars[0]
                else:
                    logger.error("Nessun calendario trovato")
                    return False
            
            # Crea VTODO
            cal_vobj = vobject.iCalendar()
            vtodo = cal_vobj.add('vtodo')
            vtodo.add('summary').value = title
            
            # Formattazione data
            if due_date:
                vtodo.add('due').value = due_date
                vtodo.add('dtstart').value = due_date
            
            vtodo.add('dtstamp').value = datetime.utcnow()
            
            if notes:
                vtodo.add('description').value = notes
            
            # Salva su iCloud
            log("ICLOUD_REMINDER_SENDING", title=title, list=getattr(reminder_cal, 'name', 'Unknown'))
            reminder_cal.add_todo(cal_vobj.serialize())
            
            log("ICLOUD_REMINDER_CREATED", title=title)
            return True
            
        except Exception as e:
            log("ICLOUD_REMINDER_CREATE_FAILED", error=str(e), level="ERROR")
            return False
