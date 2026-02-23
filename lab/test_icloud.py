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
        print(f"✅ Trovati {len(reminders)} promemoria:")
        for r in reminders[:5]:  # Mostra primi 5
            print(f"   - [{r['status']}] {r['summary']} (Scadenza: {r['due']})")
        if len(reminders) > 5:
            print(f"   ...e altri {len(reminders) - 5}")
    else:
        print("ℹ️ Nessun promemoria trovato o lista vuota.")

if __name__ == "__main__":
    test_connection()
