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
        new_args = list(args)
        if new_args:
            year = new_args[0]
            # Caso 1: Anno impaccato YYYYMMDD
            if year > 9999:
                y = year // 10000
                m = (year % 10000) // 100
                d = year % 100
                # Se abbiamo altri argomenti, dobbiamo stare attenti a non shiftarli male
                # Se la chiamata era datetime(20191203, 1, 1), pyicloud probabilmente voleva 2019-12-03
                # e i successivi 1, 1 erano fittizi o duplicati
                if len(new_args) > 1:
                    # Sostituiamo i primi 3 con y, m, d se possibile
                    new_args[0] = y
                    if len(new_args) > 1: new_args[1] = m
                    if len(new_args) > 2: new_args[2] = d
                else:
                    new_args = [y, m, d]
            
            # Caso 2: Hour/Minute/Second fuori range (clamping)
            if len(new_args) > 3: # Hour
                if new_args[3] < 0 or new_args[3] > 23:
                    print(f"⚠️  Fixing invalid hour: {new_args[3]} -> 0")
                    new_args[3] = 0
            if len(new_args) > 4: # Minute
                if new_args[4] < 0 or new_args[4] > 59:
                    new_args[4] = 0
            if len(new_args) > 5: # Second
                if new_args[5] < 0 or new_args[5] > 59:
                    new_args[5] = 0

        return original_datetime.__new__(cls, *tuple(new_args), **kwargs)

class PatchedDate(original_date):
    def __new__(cls, *args, **kwargs):
        new_args = list(args)
        if new_args:
            year = new_args[0]
            if year > 9999:
                y = year // 10000
                m = (year % 10000) // 100
                d = year % 100
                if len(new_args) > 1:
                    new_args[0] = y
                    if len(new_args) > 1: new_args[1] = m
                    if len(new_args) > 2: new_args[2] = d
                else:
                    new_args = [y, m, d]
        return original_date.__new__(cls, *tuple(new_args), **kwargs)

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
            # Debug: cosa c'è dentro coll?
            # print(f"   Debug keys: {coll.keys()}")
            
            reminders = coll.get('reminders', [])
            if not reminders:
                # Prova a cercare in altre chiavi se 'reminders' è vuoto
                # Alcune versioni usano 'tasks' o simili
                print("   (vuota)")
            else:
                print(f"   ✅ Trovati {len(reminders)} promemoria.")
                for r in reminders[:5]:
                    title = r.get('title') or r.get('summary') or "Senza titolo"
                    due = r.get('due') or "Nessuna data"
                    print(f"   - {title} (Scadenza: {due})")

    except Exception as e:
        print(f"💥 Errore residuo: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_pyicloud_patched()
