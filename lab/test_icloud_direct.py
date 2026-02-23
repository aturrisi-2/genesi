"""
TEST ICLOUD DIRECT
Tenta l'accesso diretto all'URL dei task per bypassare l'errore 500 di Apple.
"""
import os
import sys
import caldav
from pathlib import Path
from dotenv import load_dotenv

# Path setup
root_dir = Path(__file__).parent.parent
sys.path.append(str(root_dir))
load_dotenv()

def test_direct():
    user = os.environ.get("ICLOUD_USER")
    password = os.environ.get("ICLOUD_PASSWORD")
    
    # URL diretto scoperto dai log precedenti
    # NOTA: L'ID '10668443658' sembra essere il tuo DSID interno di iCloud
    direct_url = "https://p112-caldav.icloud.com:443/10668443658/calendars/tasks/"
    
    print(f"🔗 Tentativo di connessione DIRETTA a: {direct_url}")
    print(f"👤 Utente: {user}")
    print(f"🔑 Password tipo: {'Specifica per app' if '-' in (password or '') else 'POSSIBILE PASSWORD REALE (ERRORE!)'}")
    
    try:
        client = caldav.DAVClient(
            url="https://caldav.icloud.com", # Base URL
            username=user,
            password=password
        )
        
        # Invece di fare l'auto-discovery, forziamo il calendario
        calendar = client.calendar(url=direct_url)
        
        print("\n📥 Recupero promemoria in corso...")
        # Proviamo a usare search che è più leggero
        todos = calendar.search(todo=True, include_completed=False)
        
        if not todos:
            print("ℹ️ La lista sembra vuota (o il server non risponde correttamente).")
        else:
            print(f"✅ SUCCESSO! Trovati {len(todos)} promemoria:")
            for t in todos[:10]:
                try:
                    # Caricamento manuale per evitare errori di parsing
                    vobj = t.vobject_instance.vtodo
                    summary = vobj.summary.value if hasattr(vobj, 'summary') else "Senza titolo"
                    print(f"   - {summary}")
                except:
                    continue
                    
    except Exception as e:
        print(f"❌ Errore durante il test diretto: {e}")

if __name__ == "__main__":
    test_direct()
