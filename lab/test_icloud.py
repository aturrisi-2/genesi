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
    if not user:
        print("❌ ICLOUD_USER non configurato nel .env")
        return

    print(f"🚀 Tentativo di connessione per: {user}...")
    
    # 1. Recupera liste
    lists = icloud_service.get_reminders_lists()
    if not lists:
        print("❌ Nessuna lista trovata o errore di autenticazione.")
        return

    print(f"✅ Connessione riuscita! Trovate {len(lists)} liste:")
    for l in lists:
        print(f"   - {l['name']} (ID: {l['id']})")

    # 2. Prova a leggere i promemoria da TUTTE le liste usando l'ID (GUID)
    print("\n📥 Scansione liste per trovare promemoria...")
    found_any = False
    for l in lists:
        name = l['name']
        list_id = l['id']
        reminders = icloud_service.get_reminders(list_id) # Usiamo ID invece del nome
        if reminders:
            found_any = True
            print(f"✅ Trovati {len(reminders)} promemoria in '{name}' (ID: {list_id}):")
            for r in reminders[:5]:
                print(f"   - {r['summary']}")
        else:
            print(f"ℹ️ Lista '{name}' vuota.")
            
    if not found_any:
        print("\n❌ Nessun promemoria trovato in nessuna lista.")

if __name__ == "__main__":
    test_connection()
