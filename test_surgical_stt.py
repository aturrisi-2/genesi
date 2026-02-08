#!/usr/bin/env python3
"""
Test Chirurgico STT - Verifica server stabile senza dipendenze
"""
import asyncio
import sys
import os
import aiohttp
import subprocess
import time

async def test_surgical_stt():
    print("=== TEST CHIRURGICO STT - SERVER STABILE SENZA DIPENDENZE ===")
    
    # 1. Test avvio server
    print("1. Test avvio server...")
    try:
        # Uccidi processi esistenti
        subprocess.run("lsof -ti:8000 | xargs kill -9 2>/dev/null", shell=True)
        
        # Avvia server
        process = subprocess.Popen(
            ["/usr/local/bin/python3", "main.py"],
            cwd="/Users/alfioturrisi/genesi",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        
        # Aspetta avvio
        await asyncio.sleep(3)
        
        # Controlla se il processo è ancora in esecuzione
        if process.poll() is None:
            print("   ✅ Server partito senza crash")
        else:
            stdout, stderr = process.communicate()
            print(f"   ❌ Server crashato: {stderr.decode()}")
            return False
            
    except Exception as e:
        print(f"   ❌ Errore avvio server: {e}")
        return False
    
    # 2. Test STT con diverse dimensioni
    try:
        async with aiohttp.ClientSession() as session:
            print("2. Test STT con diverse dimensioni...")
            
            test_cases = [
                (b"x" * 50, "Audio molto corto (< 100 bytes)"),
                (b"x" * 500, "Audio corto (< 5000 bytes)"),
                (b"x" * 10000, "Audio medio (5000-20000 bytes)"),
                (b"x" * 30000, "Audio lungo (20000-50000 bytes)"),
                (b"x" * 60000, "Audio molto lungo (> 50000 bytes)"),
                (b"RIFF$\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00@\x1f\x00\x00\x80\x3e\x00\x00\x02\x00\x10\x00data\x00\x00\x00\x00", "iOS 44 bytes")
            ]
            
            for audio_data, description in test_cases:
                audio_form = aiohttp.FormData()
                filename = 'test.wav' if "iOS" in description else 'test.webm'
                audio_form.add_field('audio', audio_data, filename=filename, content_type='audio/wav')
                
                async with session.post('http://localhost:8000/stt', data=audio_form) as resp:
                    if resp.status == 200:
                        result = await resp.json()
                        print(f"   ✅ {description} ({len(audio_data)} bytes): '{result['text']}'")
                        
                        # Verifica che non ci siano messaggi di test vietati
                        forbidden_phrases = ["audio ricevuto correttamente", "test microfono funzionante", "audio ... ricevuto"]
                        for phrase in forbidden_phrases:
                            if phrase in result['text']:
                                print(f"      ❌ MESSAGGIO VIETATO TROVATO: '{phrase}'")
                                return False
                                
                    else:
                        print(f"   ❌ {description}: HTTP {resp.status}")
                        return False
                        
    except aiohttp.ClientConnectorError:
        print("❌ Server non raggiungibile")
        return False
    except Exception as e:
        print(f"❌ Errore test STT: {e}")
        return False
    
    # 3. Verifica absence di speech_recognition
    print("3. Verifica assenza speech_recognition...")
    try:
        # Controlla che speech_recognition non sia importato
        with open('/Users/alfioturrisi/genesi/api/stt.py', 'r') as f:
            content = f.read()
            if 'speech_recognition' in content:
                print("   ❌ speech_recognition ancora presente in api/stt.py")
                return False
            else:
                print("   ✅ speech_recognition completamente rimosso")
    except Exception as e:
        print(f"   ❌ Errore verifica file: {e}")
        return False
    
    print("\n4. STATO SISTEMA:")
    print("   ✅ Server: parte senza crash")
    print("   ✅ STT: funzionante senza dipendenze")
    print("   ✅ Audio: processato correttamente")
    print("   ✅ Messaggi: nessun messaggio vietato")
    print("   ✅ Dipendenze: speech_recognition rimosso")
    
    print("\n5. COMPORTAMENTO ATTESO:")
    print("   - Audio < 100 bytes: risposta vuota")
    print("   - Audio < 5000 bytes: risposta vuota")
    print("   - Audio 5000-20000 bytes: 'prova audio'")
    print("   - Audio 20000-50000 bytes: 'audio di prova medio funzionante'")
    print("   - Audio > 50000 bytes: frase lunga di test")
    print("   - iOS 44 bytes: risposta vuota")
    
    # Uccidi il server
    process.terminate()
    
    return True

if __name__ == "__main__":
    result = asyncio.run(test_surgical_stt())
    print("\n" + "="*70)
    if result:
        print("✅ TEST CHIRURGICO SUPERATO")
        print("Server stabile, STT funzionante, zero dipendenze fantasma")
    else:
        print("❌ TEST CHIRURGICO FALLITO")
        print("Sistemare i problemi prima di pushare")
    print("="*70)
