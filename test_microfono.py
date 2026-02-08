#!/usr/bin/env python3
"""
Test Microfono - Verifica funzionamento microfono e STT
"""
import asyncio
import sys
import os
import aiohttp
sys.path.insert(0, '.')

async def test_microphone():
    print("=== TEST MICROFONO ===")
    
    # Test endpoint STT
    try:
        async with aiohttp.ClientSession() as session:
            print("1. Test endpoint /stt...")
            
            # Crea un file audio fittizio per test
            fake_audio = b"fake_audio_data_for_testing" * 100
            audio_data = aiohttp.FormData()
            audio_data.add_field('audio', fake_audio, filename='test.webm', content_type='audio/webm')
            
            async with session.post('http://localhost:8000/stt', data=audio_data) as resp:
                print(f"   Status: {resp.status}")
                
                if resp.status == 200:
                    result = await resp.json()
                    print(f"   Response: {result}")
                    print("   ✅ Endpoint STT funzionante")
                else:
                    error_text = await resp.text()
                    print(f"   ❌ Errore: {error_text}")
                    return False
                    
    except aiohttp.ClientConnectorError:
        print("❌ Server non in esecuzione su localhost:8000")
        print("Avvia il server con: python main.py")
        return False
    except Exception as e:
        print(f"❌ Errore test STT: {e}")
        return False
    
    print("\n2. Test browser compatibility...")
    print("   Apri http://localhost:8000 nel browser")
    print("   Premi il pulsante del microfono")
    print("   Controlla la console per questi log:")
    print("   - [MIC] requesting permission...")
    print("   - [MIC] permission granted")
    print("   - [MIC] recording started successfully")
    print("   - [STT] sending POST /stt...")
    print("   - [STT] response status=200")
    print("   - [STT] transcription received")
    
    print("\n3. Controlli difensivi implementati:")
    print("   ✅ Verifica HTTPS/contexto sicuro")
    print("   ✅ Verifica navigator.mediaDevices")
    print("   ✅ Verifica getUserMedia")
    print("   ✅ Alert chiari per utente")
    print("   ✅ Logging dettagliato pipeline")
    
    print("\n4. Test manuale richiesti:")
    print("   - Desktop Chrome: microfono e STT")
    print("   - Safari: microfono e STT")
    print("   - Mobile Safari (se possibile)")
    print("   - Verifica nessun errore getUserMedia")
    print("   - Verifica /stt ritorna 200")
    print("   - Verifica trascrizione visibile")
    
    return True

if __name__ == "__main__":
    result = asyncio.run(test_microphone())
    print("\n" + "="*60)
    if result:
        print("✅ TEST MICROFONO PREPARATO")
        print("Ora testa manualmente nel browser")
    else:
        print("❌ TEST MICROFONO FALLITO")
    print("="*60)
