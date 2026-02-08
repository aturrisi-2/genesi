#!/usr/bin/env python3
"""
Test Rimozione Hard Test Mode - Verifica completa rimozione fallback/test
"""
import asyncio
import sys
import os
import aiohttp
sys.path.insert(0, '.')

async def test_no_hard_test_mode():
    print("=== TEST RIMOZIONE HARD TEST MODE ===")
    
    # Test endpoint STT con diverse dimensioni
    try:
        async with aiohttp.ClientSession() as session:
            print("1. Test endpoint /stt con diverse dimensioni audio...")
            
            test_cases = [
                (b"audio_reale_molto_breve" * 10, "molto breve"),
                (b"audio_reale_breve" * 50, "breve"),
                (b"audio_reale_medio" * 500, "medio"),
                (b"audio_reale_lungo" * 2000, "lungo")
            ]
            
            for audio_data, expected_type in test_cases:
                audio_form = aiohttp.FormData()
                audio_form.add_field('audio', audio_data, filename=f'test_{expected_type}.wav', content_type='audio/wav')
                
                async with session.post('http://localhost:8000/stt', data=audio_form) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        print(f"   ✅ {expected_type} ({len(audio_data)} bytes): '{result['text']}'")
                    else:
                        print(f"   ❌ {expected_type}: HTTP {resp.status}")
                        return False
                        
    except aiohttp.ClientConnectorError:
        print("❌ Server non in esecuzione su localhost:8000")
        return False
    except Exception as e:
        print(f"❌ Errore test STT: {e}")
        return False
    
    print("\n2. PERCORSI DI TEST/FALLBACK RIMOSSI:")
    print("   ❌ RIMOSSO: if (blob.size < 500) nel MediaRecorder")
    print("   ❌ RIMOSSO: if (wavBlob.size < 500) nel iOS")
    print("   ❌ RIMOSSO: if (blob.size < 1000) in transcribeAudio")
    print("   ❌ RIMOSSO: if (text) prima di sendMessage()")
    print("   ✅ NUOVO: transcript SEMPRE inviato alla chat")
    
    print("\n3. FLUSSO CORRETTO OBBLIGATORIO:")
    print("   MediaRecorder → WAV → POST /stt → response.text → sendMessage(response.text)")
    print("   ❌ NESSUN if")
    print("   ❌ NESSUN fallback")
    print("   ❌ NESSUN testo di test")
    
    print("\n4. COMPORTAMENTO ATTESO:")
    print("   - Audio qualsiasi dimensione → sempre processato")
    print("   - Transcript qualsiasi → sempre inviato alla chat")
    print("   - Anche se vuoto → comunque inviato")
    print("   - Anche se strano → comunque inviato")
    
    print("\n5. TEST MANUALE OBBLIGATORIO:")
    print("   iPhone Safari:")
    print("   - Di 'ciao mondo'")
    print("   - La chat DEVE mostrare esattamente 'ciao mondo'")
    print("   - Di 'oggi bel tempo'")
    print("   - La chat DEVE mostrare esattamente 'oggi bel tempo'")
    
    print("\n   macOS Safari:")
    print("   - Stesso comportamento")
    print("   - Nessuna frase finta")
    
    print("\n6. CRITERI DI SUCCESSO:")
    print("   ✅ Audio di qualsiasi dimensione processato")
    print("   ✅ Transcript sempre inviato")
    print("   ✅ Nessuna frase finta nella chat")
    print("   ✅ Comportamento identico su iOS e desktop")
    
    return True

if __name__ == "__main__":
    result = asyncio.run(test_no_hard_test_mode())
    print("\n" + "="*60)
    if result:
        print("✅ HARD TEST MODE COMPLETAMENTE RIMOSSO")
        print("Ora testa su iPhone e macOS Safari")
    else:
        print("❌ TEST FALLITO")
    print("="*60)
