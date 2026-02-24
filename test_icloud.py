
import caldav
import os
import datetime
from dotenv import load_dotenv

# Carica variabili d'ambiente
load_dotenv()

def test_icloud():
    user = os.getenv('ICLOUD_USER')
    password = os.getenv('ICLOUD_PASSWORD')
    
    if not user or not password:
        print("❌ Errore: ICLOUD_USER o ICLOUD_PASSWORD non impostati nel file .env")
        return

    print(f"🚀 Test connessione iCloud per: {user}...")
    
    try:
        client = caldav.DAVClient(
            url="https://caldav.icloud.com",
            username=user,
            password=password
        )
        client.session.headers.update({
            'User-Agent': 'iOS/17.0 (21A329) Reminders/1.0',
            'Accept': 'text/xml',
            'Prefer': 'return=minimal'
        })
        principal = client.principal()
        calendars = principal.calendars()
        
        print(f"✅ Connesso! Calendari trovati: {len(calendars)}")
        
        for cal in calendars:
            name = getattr(cal, 'name', 'Senza nome')
            print(f"\n📅 Calendario: {name}")
            
            # Test eventi (VEVENT)
            try:
                events = cal.events()
                print(f"   Eventi trovati: {len(events)}")
                for event in list(events)[:3]:
                    # Estrazione base per debug
                    print(f"     - {event.url}")
            except Exception as e:
                print(f"   ❌ Errore lettura eventi: {e}")

            # Test reminders (VTODO) - solo per vedere se fallisce
            try:
                todos = cal.todos()
                print(f"   Reminder trovati: {len(todos)}")
            except Exception as e:
                print(f"   ⚠️ Nota: Todos (VTODO) falliti su questo calendario (previsto): {e}")

    except Exception as e:
        print(f"❌ Errore fatale durante il test: {e}")

if __name__ == "__main__":
    test_icloud()
