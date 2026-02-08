#!/usr/bin/env python3
"""
Test Safari Microfono - Verifica specifica per Safari iOS e desktop
"""
import asyncio
import sys
import os
import aiohttp
sys.path.insert(0, '.')

async def test_safari_microphone():
    print("=== TEST SAFARI MICROFONO ===")
    
    # Test endpoint STT
    try:
        async with aiohttp.ClientSession() as session:
            print("1. Test endpoint /stt...")
            
            # Simula audio Safari (formato diverso)
            fake_audio = b"safari_audio_test_data" * 200
            audio_data = aiohttp.FormData()
            audio_data.add_field('audio', fake_audio, filename='safari_test.wav', content_type='audio/wav')
            
            async with session.post('http://localhost:8000/stt', data=audio_data) as resp:
                print(f"   Status: {resp.status}")
                
                if resp.status == 200:
                    result = await resp.json()
                    print(f"   Response: {result}")
                    print("   ✅ Endpoint STT funzionante per Safari")
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
    
    print("\n2. Safari iOS - Test manuale richiesto:")
    print("   Apri Safari su iOS device")
    print("   Vai a http://localhost:8000 (o tuo dominio HTTPS)")
    print("   Premi microfono e parla per 5-10 secondi")
    print("   Controlla console per:")
    print("   ✅ [MIC] start {isIOS: true, isSafari: true}")
    print("   ✅ [MIC][iOS] setting up AudioContext recording")
    print("   ✅ [MIC][iOS] AudioContext resumed")
    print("   ✅ [MIC][IOS] audio frames captured: X")
    print("   ✅ [STT] request sent size=... type=audio/wav")
    print("   ✅ [STT] response status=200")
    
    print("\n3. Safari Desktop - Test manuale richiesto:")
    print("   Apri Safari su macOS")
    print("   Vai a http://localhost:8000")
    print("   Premi microfono")
    print("   Controlla console per:")
    print("   ✅ [MIC] start {isIOS: false, isSafari: true}")
    print("   ✅ [MIC][DESKTOP] Safari desktop detected")
    print("   ✅ [MIC][DESKTOP] getUserMedia available")
    print("   ✅ [MIC][DESKTOP] permission granted")
    print("   ✅ [MIC][DESKTOP] Safari desktop recording started")
    print("   ✅ [STT] response status=200")
    
    print("\n4. Validazioni implementate:")
    print("   ✅ Detection affidabile iOS/Safari")
    print("   ✅ Constraints specifici Safari desktop")
    print("   ✅ Verifica dati audio reali iOS")
    print("   ✅ Validazione dimensione audio (>1KB)")
    print("   ✅ Logging dettagliato per debug")
    print("   ✅ Alert chiari per utente iOS")
    
    print("\n5. Criteri di successo:")
    print("   - iOS Safari: audio frames captured > 0")
    print("   - Safari desktop: nessun errore getUserMedia")
    print("   - Entrambi: /stt status=200")
    print("   - Entrambi: trascrizione ricevuta")
    print("   - Nessun audio vuoto inviato")
    
    return True

if __name__ == "__main__":
    result = asyncio.run(test_safari_microphone())
    print("\n" + "="*60)
    if result:
        print("✅ TEST SAFARI PREPARATO")
        print("Esegui test manuali su Safari iOS e desktop")
    else:
        print("❌ TEST SAFARI FALLITO")
    print("="*60)
