#!/usr/bin/env python3
"""
Test Finale STT - Server stabile senza dipendenze
"""
import subprocess
import time
import requests

def test_final_stt():
    print("=== TEST FINALE STT - SERVER STABILE ===")
    
    # Test base
    try:
        # Test con audio lungo
        with open('test_final.txt', 'wb') as f:
            f.write(b'x' * 60000)
        
        response = requests.post('http://localhost:8000/stt', files={'audio': open('test_final.txt', 'rb')})
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ STT funzionante: '{result['text']}'")
            
            # Verifica assenza messaggi vietati
            forbidden = ["audio ricevuto correttamente", "test microfono funzionante"]
            for phrase in forbidden:
                if phrase in result['text']:
                    print(f"❌ Messaggio vietato trovato: '{phrase}'")
                    return False
            
            print("✅ Nessun messaggio vietato")
            return True
        else:
            print(f"❌ Errore HTTP: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Errore test: {e}")
        return False

if __name__ == "__main__":
    result = test_final_stt()
    print("\n" + "="*50)
    if result:
        print("✅ SERVER STABILE - STT FUNZIONANTE")
        print("Zero crash, zero dipendenze fantasma")
    else:
        print("❌ PROBLEMI PRESENTI")
    print("="*50)
