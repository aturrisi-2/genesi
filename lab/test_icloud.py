"""
TEST ICLOUD CONNECTION
Usa questo script per verificare se Genesi riesce a parlare con il tuo iCloud.
Assicurati di aver configurato ICLOUD_USER e ICLOUD_PASSWORD nel file .env (usa una App-Specific Password).
"""

import os
import sys
from pathlib import Path

# Aggiungi la root del progetto al path per trovare il modulo 'core'
root_dir = Path(__file__).parent.parent
sys.path.append(str(root_dir))

from dotenv import load_dotenv

# Carica variabili d'ambiente PRIMA di importare il servizio
load_dotenv()

from core.icloud_service import icloud_service

def test_connection():
    print("🔍 Controllo credenziali...")
    user = os.environ.get("ICLOUD_USER")
    if not user or user == "your_apple_id@icloud.com":
        print("❌ ICLOUD_USER non configurato nel .env")
        return

    print(f"🚀 Tentativo di connessione per: {user}...")
    
    # 1. Recupera liste
    lists = icloud_service.get_reminders_lists()
    if not lists:
        print("❌ Nessuna lista trovata o errore di autenticazione.")
        return

    print(f"✅ Connessione riuscita! Trovate {len(lists)} liste/calendari:")
    for l in lists:
        print(f"   - {l['name']} (ID: {l['id']})")

    # 2. Prova a leggere i promemoria (da 'Promemoria', 'Reminders' o prima lista disponibile)
    default_list = "Promemoria"
    print(f"\n📥 Recupero promemoria dalla lista '{default_list}'...")
    reminders = icloud_service.get_reminders(default_list)
    
    if reminders:
        print(f"✅ Trovati {len(reminders)} promemoria (Metodo Discovery):")
    else:
        print("ℹ️ Fallito metodo discovery. Tentativo accesso DIRETTO all'URL...")
        # Proviamo ad accedere direttamente all'URL che abbiamo visto prima
        try:
            client = icloud_service._get_client()
            # Usiamo l'ID esatto visto nel log precedente
            direct_url = "https://p112-caldav.icloud.com:443/10668443658/calendars/tasks/"
            print(f"🔗 Tentativo su: {direct_url}")
            calendar = client.calendar(url=direct_url)
            
            # Proviamo a leggere
            todos = calendar.search(todo=True, include_completed=False)
            if todos:
                print(f"✅ FUNZIONA! Trovati {len(todos)} promemoria via URL diretto.")
            else:
                print("ℹ️ Lista vuota anche via URL diretto.")
        except Exception as e:
            print(f"❌ Errore accesso diretto: {e}")

if __name__ == "__main__":
    test_connection()
