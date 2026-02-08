#!/usr/bin/env python3
"""
Test TTS Confini - Verifica punto esatto di interruzione
"""
import asyncio
import sys
import os
sys.path.insert(0, '.')

from api.chat import chat_endpoint
from auth.database import init_db, async_session
from auth.models import AuthUser
from auth.security import hash_password
from auth.init_environment import initialize_user_environment
from unittest.mock import Mock

async def test_tts_confini():
    print("=== TEST TTS CONFINI - VERIFICA PUNTO INTERRUZIONE ===")
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

    async def test_scenario(msg, test_name):
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
            
            # Verifica che il testo sia della lunghezza attesa per il test
            if should_respond and response_text.strip():
                print(f"  PASS: should_respond=True, testo pronto per TTS")
                
                # Verifica se il testo supera i limiti noti
                if len(response_text) > 500:
                    print(f"  INFO: Testo lungo ({len(response_text)} char) → dovrebbe attivare segmentazione")
                elif len(response_text) > 200:
                    print(f"  INFO: Testo medio ({len(response_text)} char)")
                else:
                    print(f"  INFO: Testo breve ({len(response_text)} char)")
                
                return True
            else:
                print(f"  PASS: should_respond=False, nessun TTS richiesto")
                return True
                
        except Exception as e:
            print(f"  FAIL: {e}")
            return False

    # TEST 1: Testo 50 char
    msg1 = "ciao"
    result1 = await test_scenario(msg1, "1) Testo 50 char")
    if result1: passed += 1
    else: failed += 1

    # TEST 2: Testo 200 char
    msg2 = "spiegami brevemente come funzionano le reti neurali e le loro applicazioni principali"
    result2 = await test_scenario(msg2, "2) Testo 200 char")
    if result2: passed += 1
    else: failed += 1

    # TEST 3: Testo 400 char
    msg3 = "spiegami in dettaglio il funzionamento delle reti neurali transformer, includendo l'architettura del meccanismo di attenzione e il processo di encoding"
    result3 = await test_scenario(msg3, "3) Testo 400 char")
    if result3: passed += 1
    else: failed += 1

    # TEST 4: Testo 600+ char
    msg4 = "spiegami in dettaglio il funzionamento delle reti neurali transformer, includendo l'architettura del meccanismo di attenzione, il processo di encoding e decoding, il ruolo dei positional embeddings, e come questi modelli vengono addestrati su grandi quantità di dati testuali per il processamento del linguaggio naturale con applicazioni moderne"
    result4 = await test_scenario(msg4, "4) Testo 600+ char")
    if result4: passed += 1
    else: failed += 1

    # RISULTATO
    print("\n" + "="*60)
    total = passed + failed
    print(f"RISULTATO: {passed}/{total} test passati")
    if failed > 0:
        print(f"FALLITI: {failed}")
    else:
        print("TUTTI I TEST PASSATI")
    
    print("\nPROSSIMO PASSO:")
    print("1. Avvia il server: python main.py")
    print("2. Apri il browser e testa i 4 scenari")
    print("3. Controlla i log per:")
    print("   - [TTS_MANDATORY] (deve apparire sempre)")
    print("   - [TTS_PRE] len=... (deve apparire sempre)")
    print("   - [TTS] sanitized text (deve apparire sempre)")
    print("   - [TTS] OUTPUT (deve apparire sempre)")
    print("4. Se manca anche un solo log → BUG TROVATO")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_tts_confini())
