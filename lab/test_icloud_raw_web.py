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
        # Tenta di recuperare l'host dei promemoria dai dati di sessione
        host = None
        if hasattr(api, 'webservices'): # Alcune versioni
            host = api.webservices.get('reminders', {}).get('url')
        
        if not host and hasattr(api, '_webservices'): # Versioni recenti
            host = api._webservices.get('reminders', {}).get('url')
            
        if not host:
            # Fallback: proviamo a cercarlo nei dati grezzi della sessione
            print("🔍 Ricerca host nelle webservices...")
            for name, svc in api.data.get('webservices', {}).items():
                if name == 'reminders':
                    host = svc.get('url')
                    break
        
        if not host:
            print("❌ Impossibile trovare l'URL del servizio Reminders.")
            # Stampiamo le chiavi disponibili per debug
            print(f"Chiavi API: {list(api.__dict__.keys())}")
            return
            
        print(f"🔗 Reminders Host: {host}")
        
        url = f"{host}/rd/startup"
        params = dict(api.params)
        params.update({
            "clientVersion": "4.0",
            "lang": "it-it",
        })

        print(f"📥 Richiesta dati grezzi a Apple (Total Bypass)...")
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
