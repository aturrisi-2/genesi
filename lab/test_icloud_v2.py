"""
TEST ICLOUD V2 (PYICLOUD)
Metodo alternativo più solido per leggere i promemoria.
"""
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Path setup
root_dir = Path(__file__).parent.parent
sys.path.append(str(root_dir))
load_dotenv()

from pyicloud import PyiCloudService

def test_pyicloud():
    user = os.environ.get("ICLOUD_USER")
    password = os.environ.get("ICLOUD_PASSWORD")
    
    print(f"🚀 Tentativo connessione Web API per: {user}...")
    api = PyiCloudService(user, password)

    if api.requires_2fa:
        print("⚠️  AUTENTICAZIONE 2FA RICHIESTA!")
        print("Controlla il tuo iPhone/Mac e inserisci il codice qui sotto.")
        code = input("Inserisci il codice 2FA: ")
        result = api.validate_2fa_code(code)
        print(f"Risultato 2FA: {result}")
        if not result:
            print("❌ Codice errato.")
            return

    elif api.requires_2sa:
        print("⚠️ 2SA richiesta (metodo vecchio). Controlla i tuoi dispositivi.")
        # Gestione semplificata per il test
        return

    print("✅ Connesso con successo!")
    
    # Prova a leggere i promemoria
    try:
        print("\n📥 Recupero liste promemoria...")
        collections = api.reminders.collections
        for name, coll in collections.items():
            print(f"📂 Lista: '{name}'")
            # Leggi i primi 3 task di ogni lista
            reminders = coll.get('reminders', [])
            for r in reminders[:3]:
                title = r.get('title', 'Senza titolo')
                print(f"   - {title}")
    except Exception as e:
        print(f"❌ Errore durante il fetch: {e}")

if __name__ == "__main__":
    test_pyicloud()
