#!/usr/bin/env python3
"""
Test Audio Pipeline - 4 scenari reali
Verifica che l'audio venga generato e riprodotto correttamente
"""
import asyncio
import sys
import os
import time
sys.path.insert(0, '.')

from api.chat import chat_endpoint
from auth.database import init_db, async_session
from auth.models import AuthUser
from auth.security import hash_password
from auth.init_environment import initialize_user_environment
from unittest.mock import Mock

async def test_audio_pipeline():
    print("=== TEST AUDIO PIPELINE - 4 SCENARI ===")
    passed = 0
    failed = 0

    # Init DB
    db_path = 'data/auth/genesi_auth.db'
    if os.path.exists(db_path):
        os.remove(db_path)
    await init_db()

    # Helper per creare utente test
    async def get_test_user(email):
        async with async_session() as db:
            from sqlalchemy import select
            result = await db.execute(select(AuthUser).where(AuthUser.email == email))
            user = result.scalar_one_or_none()
            if not user:
                user = AuthUser(email=email, password_hash=hash_password('TestPass1'), is_verified=True)
                db.add(user); await db.commit(); await db.refresh(user)
                initialize_user_environment(user.id, {})
            return user

    class MockRequest:
        def __init__(self):
            self.client = Mock()
            self.client.host = '127.0.0.1'
            self.headers = {}

    class MockChatRequest:
        def __init__(self, user_id, message):
            self.user_id = user_id
            self.message = message

    async def test_audio_scenario(msg, test_name):
        print(f"\n{test_name}")
        try:
            user = await get_test_user(f'test_{test_name.replace(" ", "_")}@test.com')
            response = await chat_endpoint(MockChatRequest(user.id, msg), http_request=MockRequest())
            
            response_text = response.get('response', '')
            tts_mode = response.get('tts_mode', 'normal')
            should_respond = response.get('should_respond', False)
            
            print(f"  Messaggio: '{msg}'")
            print(f"  Risposta: '{response_text[:100]}...' (len={len(response_text)})")
            print(f"  should_respond: {should_respond}")
            print(f"  tts_mode: {tts_mode}")
            
            if should_respond and response_text.strip():
                # Test TTS via HTTP endpoint
                try:
                    import aiohttp
                    async with aiohttp.ClientSession() as session:
                        print(f"  Chiamando /tts...")
                        async with session.post('http://localhost:8000/tts', 
                                               json={'text': response_text.strip()}) as resp:
                            
                            print(f"  Response status: {resp.status}")
                            print(f"  Headers: {dict(resp.headers)}")
                            
                            if resp.status != 200:
                                error_text = await resp.text()
                                print(f"  FAIL: HTTP {resp.status}: {error_text}")
                                return False
                            
                            audio_bytes = await resp.read()
                            audio_size = len(audio_bytes)
                            
                            # Calcola durata stimata
                            estimated_duration = audio_size / 16000 if audio_size > 0 else 0
                            
                            print(f"  Audio ricevuto: {audio_size} bytes")
                            print(f"  Durata stimata: {estimated_duration:.2f}s")
                            
                            # ASSERT FINALE: audio size > 0
                            if audio_size == 0:
                                print(f"  FAIL: Audio size 0!")
                                return False
                            
                            if audio_size < 100:
                                print(f"  FAIL: Audio troppo piccolo ({audio_size} bytes)")
                                return False
                            
                            # Salva audio per test manuale
                            audio_file = f'test_audio_{test_name.replace(" ", "_")}.mp3'
                            with open(audio_file, 'wb') as f:
                                f.write(audio_bytes)
                            print(f"  Audio salvato: {audio_file}")
                            
                            print(f"  PASS: Audio valido")
                            return True
                            
                except aiohttp.ClientConnectorError:
                    print(f"  FAIL: Server non in esecuzione su localhost:8000")
                    return False
                except Exception as e:
                    print(f"  FAIL: Errore chiamata TTS: {e}")
                    return False
            else:
                print(f"  PASS: should_respond=False, nessun audio richiesto")
                return True
                
        except Exception as e:
            print(f"  FAIL: {e}")
            return False

    # TEST 1: Testo breve → audio OK
    result1 = await test_audio_scenario("ciao", "1) Testo breve → audio OK")
    if result1: passed += 1
    else: failed += 1

    # TEST 2: Testo medio → audio OK
    result2 = await test_audio_scenario("come stai oggi? spero che tu stia bene", "2) Testo medio → audio OK")
    if result2: passed += 1
    else: failed += 1

    # TEST 3: Testo lungo tecnico → audio OK
    result3 = await test_audio_scenario("spiegami in dettaglio il funzionamento delle reti neurali transformer e come vengono utilizzate nei moderni modelli di linguaggio come GPT per il processamento del linguaggio naturale", "3) Testo lungo tecnico → audio OK")
    if result3: passed += 1
    else: failed += 1

    # TEST 4: Testo lungo psicologico → audio OK
    result4 = await test_audio_scenario("mi sento molto triste e confuso ultimamente, non so più cosa fare nella mia vita, tutto sembra senza senso e non trovo più la motivazione per alzarmi la mattina", "4) Testo lungo psicologico → audio OK")
    if result4: passed += 1
    else: failed += 1

    # RISULTATO
    print("\n" + "="*60)
    total = passed + failed
    print(f"RISULTATO: {passed}/{total} test passati")
    if failed > 0:
        print(f"FALLITI: {failed}")
        print("CONTROLLA I FILE AUDIO GENERATI:")
        for f in os.listdir('.'):
            if f.startswith('test_audio_') and f.endswith('.mp3'):
                size = os.path.getsize(f)
                print(f"  {f}: {size} bytes")
    else:
        print("TUTTI I TEST PASSATI - AUDIO SEMPRE PRESENTE")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_audio_pipeline())
