#!/usr/bin/env python3
"""
Test completo flusso TTS per identificare contaminazione
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

async def test_flusso_tts():
    print("=== TEST FLUSSO COMPLETO TTS ===")
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

    # TEST 1: Messaggio semplice
    print("\n1) Messaggio semplice")
    try:
        user = await get_test_user('test1@test.com')
        response = await chat_endpoint(MockChatRequest(user.id, 'ciao'), http_request=MockRequest())
        response_text = response.get('response', '')
        print(f"  Risposta: '{response_text[:100]}...'")
        
        # Verifica se ci sono contaminazioni
        if any(pattern in response_text for pattern in ['[', ']', 'T', ':', '-', 'Z']):
            print(f"  ATTENZIONE: possibile contaminazione nel testo")
            failed += 1
        else:
            print(f"  PASS: testo pulito")
            passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 2: Messaggio con richiesta lunga
    print("\n2) Messaggio lungo")
    try:
        user = await get_test_user('test2@test.com')
        long_msg = "raccontami qualcosa di lungo e dettagliato sulla natura umana"
        response = await chat_endpoint(MockChatRequest(user.id, long_msg), http_request=MockRequest())
        response_text = response.get('response', '')
        print(f"  Risposta: '{response_text[:100]}...'")
        
        if any(pattern in response_text for pattern in ['[', ']', 'T', ':', '-', 'Z']):
            print(f"  ATTENZIONE: possibile contaminazione nel testo")
            failed += 1
        else:
            print(f"  PASS: testo pulito")
            passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # RISULTATO
    print("\n" + "="*60)
    total = passed + failed
    print(f"RISULTATO: {passed}/{total} test passati")
    if failed > 0:
        print(f"ATTENZIONE: {failed} test mostrano contaminazione")
    else:
        print("TUTTI I TEST PASSATI")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_flusso_tts())
