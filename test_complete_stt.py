#!/usr/bin/env python3
"""
Test Completo STT - Verifica Safari macOS e iOS
"""
import asyncio
import sys
import os
import aiohttp
sys.path.insert(0, '.')

async def test_complete_stt():
    print("=== TEST COMPLETO STT - SAFARI MAC + iOS ===")
    
    # Test endpoint STT con diversi input
    try:
        async with aiohttp.ClientSession() as session:
            print("1. Test endpoint /stt con audio reale...")
            
            test_cases = [
                (b"audio_reale_test" * 2000, "Safari macOS simulation"),
                (b"audio_ios_test" * 100, "iOS simulation"),
                (b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00@\x1f\x00\x00\x80\x3e\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00", "iOS 44 bytes")
            ]
            
            for audio_data, description in test_cases:
                audio_form = aiohttp.FormData()
                filename = 'test.wav' if description == "iOS 44 bytes" else 'test.webm'
                audio_form.add_field('audio', audio_data, filename=filename, content_type='audio/wav')
                
                async with session.post('http://localhost:8000/stt', data=audio_form) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        print(f"   ✅ {description} ({len(audio_data)} bytes): '{result['text']}'")
                        
                        # Verifica che non sia un messaggio di test
                        if "audio" in result['text'] and "ricevuto" in result['text']:
                            print(f"      ❌ ANCORA MESSAGGIO DI TEST!")
                    else:
                        print(f"   ❌ {description}: HTTP {resp.status}")
                        return False
                        
    except aiohttp.ClientConnectorError:
        print("❌ Server non in esecuzione su localhost:8000")
        return False
    except Exception as e:
        print(f"❌ Errore test STT: {e}")
        return False
    
    print("\n2. PROBLEMA IDENTIFICATO:")
    print("   ❌ Safari macOS: riceve 'audio breve ricevuto correttamente' invece di trascrizione")
    print("   ❌ iOS Safari: probabilmente 44 bytes vuoti")
    print("   ❌ Backend: usa fallback test invece di trascrizione reale")
    
    print("\n3. SOLUZIONE NECESSARIA:")
    print("   - Implementare vero STT (Whisper o altro)")
    print("   - Rimuovere completamente fallback test")
    print("   - Processare audio reale e trascrivere")
    print("   - iOS: risolvere problema AudioContext")
    
    print("\n4. AZIONI OBBLIGATORIE:")
    print("   1. Installare Whisper o alternativa")
    print("   2. Implementare trascrizione reale")
    print("   3. Testare Safari macOS")
    print("   4. Testare iOS Safari")
    print("   5. Verificare trascrizioni reali")
    
    print("\n5. CRITERI DI SUCCESSO:")
    print("   ✅ Safari macOS: 'ciao mondo' → trascrizione 'ciao mondo'")
    print("   ✅ iOS Safari: audio registrato → trascrizione reale")
    print("   ✅ Nessun messaggio 'audio ... ricevuto correttamente'")
    print("   ✅ Backend processa audio reali")
    
    return True

if __name__ == "__main__":
    result = asyncio.run(test_complete_stt())
    print("\n" + "="*60)
    if result:
        print("✅ TEST PREPARATO")
        print("Ora implementare vero STT")
    else:
        print("❌ TEST FALLITO")
    print("="*60)
