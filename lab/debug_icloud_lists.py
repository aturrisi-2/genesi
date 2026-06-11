"""
DEBUG ICLOUD LISTS
Prova a leggere 1 elemento da OGNI lista trovata per individuare dove sta il problema.
"""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Path setup
root_dir = Path(__file__).parent.parent
sys.path.append(str(root_dir))

load_dotenv()

from core.icloud_service import icloud_service

def debug_lists():
    print("🔍 Avvio debug profondo liste iCloud...")
    lists = icloud_service.get_reminders_lists()
    
    if not lists:
        print("❌ Nessuna lista trovata.")
        return

    print(f"📋 Trovate {len(lists)} liste. Inizio scansione individuale...\n")

    for l in lists:
        name = l['name']
        print(f"👉 Testando lista: '{name}' ...", end=" ", flush=True)
        
        try:
            # Prova a recuperare i promemoria per questa specifica lista
            reminders = icloud_service.get_reminders(name)
            if reminders:
                print(f"✅ FUNZIONA! ({len(reminders)} elementi)")
                print(f"   Esempio: {reminders[0]['summary']}")
            else:
                print("ℹ️ Vuota (o nessun promemoria trovato)")
        except Exception as e:
            print(f"❌ ERRORE: {str(e)}")

    print("\n🏁 Debug completato.")

if __name__ == "__main__":
    debug_lists()
