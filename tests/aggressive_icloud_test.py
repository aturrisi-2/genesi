
import os
import sys
import datetime
import uuid
import vobject
from pathlib import Path

# Aggiungi il path della root del progetto
sys.path.append(str(Path(__file__).parent.parent))

from core.icloud_service import icloud_service
from core.log import log

def log_print(msg, **kwargs):
    print(f"[{datetime.datetime.now().isoformat()}] {msg} {kwargs if kwargs else ''}")

async def run_diagnostic():
    log_print("Starting Aggressive iCloud Diagnostic...")
    
    # 1. Caricamento credenziali
    user = os.environ.get("ICLOUD_USER")
    password = os.environ.get("ICLOUD_PASSWORD") or os.environ.get("ICLOUD_PASS")
    
    if not user or not password:
        # Tenta di caricarle dallo storage se mancano
        from core.storage import storage
        profile = await storage.load('profile:6028d92a-94f2-4e2f-bcb7-012c861e3ab2')
        user = profile.get('icloud_user')
        password = profile.get('icloud_password')
        icloud_service.username = user
        icloud_service.password = password
        log_print("Credentials loaded from storage", user=user)
    else:
        icloud_service.username = user
        icloud_service.password = password
        log_print("Credentials loaded from env", user=user)

    # 2. Connessione
    log_print("Connecting to iCloud...")
    if not icloud_service._connect():
        log_print("CRITICAL: Failed to connect to iCloud")
        return

    # 3. Elenco calendari e contenuto
    principal = icloud_service.client.principal()
    calendars = principal.calendars()
    log_print(f"Found {len(calendars)} calendars")
    
    target_cal = None
    
    for cal in calendars:
        name = getattr(cal, 'name', 'Unknown')
        log_print(f"Examining Calendar: {name}")
        
        # Prova a leggere TUTTO da questo calendario (senza filtri)
        try:
            objs = cal.objects()
            log_print(f"  - Item count: {len(objs)}")
            # Mostra i primi 3 per verifica
            for i, obj in enumerate(objs[:3]):
                try:
                    obj.load()
                    data = obj.data
                    if isinstance(data, bytes): data = data.decode('utf-8')
                    if 'VTODO' in data:
                        v = vobject.readOne(data)
                        summary = getattr(v.vtodo, 'summary', 'No Summary').value
                        log_print(f"    - [TODO] {summary}")
                    elif 'VEVENT' in data:
                        v = vobject.readOne(data)
                        summary = getattr(v.vevent, 'summary', 'No Summary').value
                        log_print(f"    - [EVENT] {summary}")
                except Exception as e:
                    log_print(f"    - Error reading item: {e}")
        except Exception as e:
            log_print(f"  - Error listing objects: {e}")
            
        # Identifica il target per la scrittura
        if any(x in name.lower() for x in ["promemoria", "tasks", "reminders"]):
            target_cal = cal
            log_print(f"  - Identified as TARGET for write test")

    if not target_cal and calendars:
        target_cal = calendars[0]
        log_print(f"No explicit Reminders list found, using fallback: {target_cal.name}")

    if target_cal:
        # 4. Prova di scrittura MIRATA
        test_title = f"GENESI_TEST_{uuid.uuid4().hex[:6]}"
        test_dt = datetime.datetime.now() + datetime.timedelta(minutes=10)
        
        log_print(f"Attempting WRITE TEST to '{target_cal.name}'...")
        log_print(f"Title: {test_title}")
        
        success = icloud_service.create_event(test_title, test_dt, is_todo=True)
        
        if success:
            log_print("WRITE TEST returned SUCCESS")
            
            # 5. Verifica immediata della lettura
            log_print("Verifying write by reading back...")
            objs = target_cal.objects()
            found = False
            for obj in objs:
                try:
                    obj.load()
                    data = obj.data
                    if isinstance(data, bytes): data = data.decode('utf-8')
                    if test_title in data:
                        log_print("VERIFICATION SUCCESS: Found the test item in the calendar!")
                        found = True
                        break
                except: continue
            
            if not found:
                log_print("VERIFICATION FAILED: Test item not found in calendar after successful creation!")
        else:
            log_print("WRITE TEST returned FAILURE")

if __name__ == "__main__":
    import asyncio
    asyncio.run(run_diagnostic())
