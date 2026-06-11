"""
TEST ICLOUD V3 (DEEP PYICLOUD)
Tenta il fetch granulare per superare l'errore delle date (year out of range).
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

def test_pyicloud_deep():
    user = os.environ.get("ICLOUD_USER")
    password = os.environ.get("ICLOUD_PASSWORD")
    
    print(f"🚀 Connessione per: {user}...")
    api = PyiCloudService(user, password)

    if api.requires_2fa:
        print("⚠️ 2FA richiesta.")
        # Assumiamo che la sessione sia già valida se lanciato dopo il v2
        # o chiediamo di nuovo se necessario (ma solitamente pyicloud salva la sessione)
        if not api.validate_2fa_code(input("Codice 2FA (se richiesto): ")):
            return

    print("✅ Autenticato.")

    try:
        # Tenta di accedere alle collezioni una ad una
        print("\n🔍 Analisi liste promemoria (metodo granulare)...")
        
        # Invece di usare api.reminders.collections (che crasha tutto se una data è errata)
        # Proviamo a forzare il refresh e intercettare l'errore
        try:
            api.reminders.refresh()
        except Exception as e:
            print(f"⚠️ Errore durante il refresh globale: {e}")
            print("Tentativo di recupero manuale dei dati grezzi...")

        # Proviamo a vedere cosa c'è dentro api.reminders
        # Spesso i dati sono in api.reminders.data
        if hasattr(api.reminders, 'collections'):
            for name in list(api.reminders.collections.keys()):
                print(f"📂 Lista trovata: '{name}'")
                try:
                    coll = api.reminders.collections[name]
                    reminders = coll.get('reminders', [])
                    print(f"   ✅ OK: {len(reminders)} promemoria.")
                    for r in reminders[:2]:
                        print(f"      - {r.get('title')}")
                except Exception as e:
                    print(f"   ❌ Errore sulla lista '{name}': {e}")
        else:
            print("❌ Impossibile accedere alle collezioni.")

    except Exception as e:
        print(f"💥 Errore fatale: {e}")

if __name__ == "__main__":
    test_pyicloud_deep()
