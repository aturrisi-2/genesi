"""
TEST ICLOUD RAW WEB API
Bypassa i bug della libreria pyicloud leggendo i dati grezzi JSON.
"""
import os
import sys
import json
from pathlib import Path
from dotenv import load_dotenv

# Path setup
root_dir = Path(__file__).parent.parent
sys.path.append(str(root_dir))
load_dotenv()

from pyicloud import PyiCloudService

def test_raw_web():
    user = os.environ.get("ICLOUD_USER")
    password = os.environ.get("ICLOUD_PASSWORD")
    
    print(f"🚀 Connessione Raw Web API per: {user}...")
    api = PyiCloudService(user, password)

    if api.requires_2fa:
        print("⚠️  2FA richiesta.")
        code = input("Inserisci codice 2FA: ")
        if not api.validate_2fa_code(code):
            print("❌ 2FA Fallito.")
            return

    print("✅ Autenticato.")

    try:
        # Recuperiamo l'URL della webservice 'reminders' SENZA inizializzare il servizio (che crasherebbe)
        reminders_service = api.webservices.get('reminders')
        if not reminders_service:
            print("❌ Servizio 'reminders' non trovato nelle webservices di Apple.")
            return
            
        host = reminders_service.get('url')
        print(f"🔗 Reminders Host: {host}")
        
        url = f"{host}/rd/startup"
        params = dict(api.params)
        params.update({
            "clientVersion": "4.0",
            "lang": "it-it",
        })

        print(f"📥 Richiesta dati grezzi a Apple (Bypassando RemindersService)...")
        response = api.session.get(url, params=params)
        
        if response.status_code != 200:
            print(f"❌ Errore Apple: {response.status_code} - {response.text}")
            return

        data = response.json()
        
        # Analizziamo le collezioni (liste)
        collections = data.get('Collections', [])
        reminders = data.get('Reminders', [])
        
        print(f"✅ Ricevuti dati! {len(collections)} liste e {len(reminders)} promemoria totali.\n")

        # Mappa per i nomi delle liste
        list_map = {c['guid']: c.get('title', 'Senza nome') for c in collections}

        # Mostriamo i risultati
        for r in reminders[:20]: # Mostra i primi 20
            p_list = list_map.get(r.get('pGuid'), 'Sconosciuta')
            title = r.get('title', 'Senza titolo')
            # Ignoriamo le date per ora per evitare il crash
            print(f"📌 [{p_list}] {title}")

    except Exception as e:
        print(f"💥 Errore durante il recupero raw: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_raw_web()
