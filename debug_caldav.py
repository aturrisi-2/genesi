import caldav
import os
from core.log import log

def debug_icloud_caldav(username, password):
    url = "https://caldav.icloud.com"
    try:
        client = caldav.DAVClient(url=url, username=username, password=password)
        principal = client.principal()
        print(f"Principal found: {principal.url}")
        
        # Tentativo 1: Standard calendars()
        try:
            calendars = principal.calendars()
            print(f"Found {len(calendars)} calendars via standard discovery")
            for cal in calendars:
                print(f" - {cal.name} ({cal.url})")
        except Exception as e:
            print(f"Standard calendars() failed: {e}")
            
            # Tentativo 2: Manual discovery via PROPFIND
            print("Attempting manual discovery...")
            # Spesso Apple richiede di cercare esplicitamente le collezioni
            try:
                # Vediamo cosa c'è sotto il principal
                response = client.propfind(principal.url, props=[caldav.elements.dav.DisplayName()], depth=1)
                print("Manual PROPFIND response received")
            except Exception as e2:
                print(f"Manual PROPFIND failed: {e2}")

    except Exception as e:
        print(f"General error: {e}")

if __name__ == "__main__":
    user = os.environ.get("ICLOUD_USER") or "idappleturrisi@gmail.com"
    pw = os.environ.get("ICLOUD_PASSWORD") # Password specifica
    if not pw:
        pw = input(f"Inserisci la password SPECIFICA per {user}: ")
    debug_icloud_caldav(user, pw)
