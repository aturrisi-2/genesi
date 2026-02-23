"""
TEST ICLOUD V4 (MONKEYPATCHED PYICLOUD)
Ripara l'errore "year is out of range" intercettando le date malformate di Apple.
"""
import os
import sys
import datetime
from pathlib import Path
from dotenv import load_dotenv

# --- MONKEYPATCH DATETIME ---
# Apple a volte manda date come YYYYMMDD in un campo che la libreria legge come 'anno'.
# Intercettiamo queste chiamate e ripariamo la data al volo.

original_datetime = datetime.datetime
original_date = datetime.date

class PatchedDatetime(original_datetime):
    def __new__(cls, *args, **kwargs):
        if args and len(args) >= 1:
            year = args[0]
            if year > 9999:
                # Ripara YYYYMMDD -> YYYY, MM, DD
                y = year // 10000
                m = (year % 10000) // 100
                d = year % 100
                args = (y, m, d) + args[1:]
        return original_datetime.__new__(cls, *args, **kwargs)

class PatchedDate(original_date):
    def __new__(cls, *args, **kwargs):
        if args and len(args) >= 1:
            year = args[0]
            if year > 9999:
                y = year // 10000
                m = (year % 10000) // 100
                d = year % 100
                args = (y, m, d) + args[1:]
        return original_date.__new__(cls, *args, **kwargs)

# Applica la patch globale
datetime.datetime = PatchedDatetime
datetime.date = PatchedDate

# --- FINE PATCH ---

# Path setup
root_dir = Path(__file__).parent.parent
sys.path.append(str(root_dir))
load_dotenv()

from pyicloud import PyiCloudService

def test_pyicloud_patched():
    user = os.environ.get("ICLOUD_USER")
    password = os.environ.get("ICLOUD_PASSWORD")
    
    print(f"🚀 Connessione con Patch per: {user}...")
    api = PyiCloudService(user, password)

    if api.requires_2fa:
        # Se la sessione è scaduta o non trovata
        print("⚠️ 2FA richiesta.")
        code = input("Inserisci codice 2FA: ")
        if not api.validate_2fa_code(code):
            print("❌ 2FA Fallito.")
            return

    print("✅ Autenticato (Sessione Riparata).")

    try:
        print("\n📥 Recupero promemoria...")
        # Il refresh() ora non dovrebbe più crashare grazie alla patch
        api.reminders.refresh()
        
        collections = api.reminders.collections
        if not collections:
            print("ℹ️ Nessuna lista trovata (ma la connessione è OK).")
            
        for name, coll in collections.items():
            print(f"📂 Lista: '{name}'")
            reminders = coll.get('reminders', [])
            if not reminders:
                print("   (vuota)")
            for r in reminders[:5]:
                title = r.get('title', 'Senza titolo')
                print(f"   - {title}")

    except Exception as e:
        print(f"💥 Errore residuo: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_pyicloud_patched()
