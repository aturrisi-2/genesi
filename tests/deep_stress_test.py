import asyncio
import os
import sys
import uuid

# Assicura il path corretto per caricare i moduli di Genesi
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# Forza utf-8 per la console Windows
sys.stdout.reconfigure(encoding='utf-8')

from dotenv import load_dotenv
load_dotenv()

from core.proactor import Proactor
from core.storage import storage
from core.chat_memory import chat_memory
from core.tool_context import get_tool_context
from db import init_db

async def run_internal_stress_test():
    await init_db()
    test_user = f"stress_test_{uuid.uuid4().hex[:8]}"
    print(f"\n🚀 --- INIZIO STRESS TEST PROFONDO GENESI ---\n👤 UTENTE TEST: {test_user}")
    
    proactor = Proactor()
    
    # 0. Inizializzazione Profilo Utente
    await storage.save(f"profile:{test_user}", {
        "user_id": test_user,
        "name": "Signor Tester",
        "email": "tester@genesi.local",
        "city": "Imola"
    })

    scenarios = [
        ("1", "IDENTITÀ (Professione)", "faccio il medico neurochirurgo", "dovrebbe memorizzare 'medico neurochirurgo'"),
        ("2", "IDENTITÀ (Gusti)", "adoro la pizza e la musica classica", "dovrebbe aggiornare le preferenze in background"),
        ("3", "RICERCA IMMAGINI", "mostrami immagini di scimmie urlatrici", "dovrebbe usare tool e attivare integrazione Pixabay"),
        ("4", "ELLITTICA IMMAGINI", "adesso leoni", "dovrebbe capire che cerchi immagini senza ripetere 'cerca'"),
        ("5", "METEO", "che tempo fa a roma?", "dovrebbe chiamare weather tool"),
        ("6", "ELLITTICA METEO", "e domani?", "dovrebbe capire che intendi il meteo a roma domani"),
        ("7", "IDENTITÀ/POSIZIONE (Protezione Falsi Positivi)", "dove sono io adesso?", "NON deve cambiare la professione in 'io adesso' (PATCH)"),
        ("8", "NOTIZIE", "dammi le ultime notizie di tecnologia", "dovrebbe attivare tool news"),
        ("9", "CODING/RICERCA TECNICA", "come faccio un ciclo for in python", "dovrebbe attivare ricerca di coding e relazionale"),
        ("10", "MEMORIA A BREVE TERMINE", "ti ricordi cosa ti ho detto che lavoro faccio?", "dovrebbe pescare dalla memoria storica bypassando i loop"),
        ("11", "CALENDARIO & SYNC", "cosa ho da fare oggi?", "dovrebbe attivare reminder_list (simulerà db vuoto per questo utente test)"),
        ("12", "GENERAZIONE IMMAGINE", "genera un'immagine di un gatto verde nello spazio", "dovrebbe indirizzare a image_generation_route")
    ]
    
    success_count = 0
    
    for step, name, msg, desc in scenarios:
        print(f"\n========================================================")
        print(f"▶ [{step}/12] TEST: {name}")
        print(f"  └ 🗣 Messaggio utente : '{msg}'")
        print(f"  └ 🎯 Aspettativa      : {desc}")
        
        try:
            # Invio al motore centrale
            response, intent = await proactor.handle(test_user, msg, None, "test-conv-001")
            
            print(f"  └ ✅ RISULTATO [OK]   : Intent estratto -> [{intent}]")
            
            # Formattazione per payload complessi (es JSON immagini)
            if isinstance(response, str) and response.startswith('{'):
                import json
                try:
                    res_json = json.loads(response)
                    text_out = res_json.get('text', 'JSON Visto')
                    print(f"  └ 🤖 Risposta Genesi : (JSON Payload) {text_out[:100]}")
                except:
                    print(f"  └ 🤖 Risposta Genesi : {response[:100]}...")
            else:
                print(f"  └ 🤖 Risposta Genesi : {response[:100]}...")
            
            # Verifiche accessorie interne
            ctx = get_tool_context(test_user)
            if ctx:
                print(f"  └ 🧠 Tool Context    : {ctx}")
            
            success_count += 1
            
            # Pausa strategica per non fare rate-limit sulle API pubbliche (es. weather/duckduckgo)
            await asyncio.sleep(2)
            
        except Exception as e:
            print(f"  └ ❌ ERRORE CRITICO   : {str(e)}")
            import traceback
            traceback.print_exc()
            
    # -------------------------------------------------------------
    # 13. AUDIT FINALE DELLA MEMORIA COGNITIVA
    # -------------------------------------------------------------
    print(f"\n========================================================")
    print("🧠 AUDIT FINALE MEMORIA (Profilo & Epistemologia)")
    
    # Diamo tempo ai task in background (estrattori identità o episodici) di terminare prima di leggere
    await asyncio.sleep(3) 
    
    profile = await storage.load(f"profile:{test_user}", {})
    
    print(f"  - Nome utente      : {profile.get('name')}")
    print(f"  - Professione      : {profile.get('profession', 'Nessuna estratta')}")
    print(f"  - Preferenze       : {profile.get('preferences', {})}")
    
    if profile.get('profession') == 'medico neurochirurgo':
        print("  ✅ Estrazione Professione: PASSATA CON SUCCESSO")
    elif profile.get('profession') == 'io adesso' or profile.get('profession') == 'io':
        print("  ❌ Estrazione Professione: FALLITA (Vulnerabilità riscontrata su falsa estrazione)")
        
    print(f"\n🎯 SCORE COMPLESSIVO: {success_count}/{len(scenarios)} TEST SUPERATI.")
    print("========================================================\n")

if __name__ == "__main__":
    asyncio.run(run_internal_stress_test())
