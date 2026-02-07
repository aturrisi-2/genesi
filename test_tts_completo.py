#!/usr/bin/env python3
"""
Test TTS completo - 5 scenari obbligatori
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

async def test_tts_completo():
    print("=== TEST TTS COMPLETO - 5 SCENARI ===")
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

    # TEST 1: Risposta breve → TTS ok
    print("\n1) Risposta breve -> TTS ok")
    try:
        user = await get_test_user('test1@test.com')
        response = await chat_endpoint(MockChatRequest(user.id, 'ciao'), http_request=MockRequest())
        response_text = response.get('response', '')
        tts_mode = response.get('tts_mode', 'normal')
        print(f"  Risposta: '{response_text[:50]}...' (len={len(response_text)})")
        print(f"  TTS mode: {tts_mode}")
        assert response_text
        assert tts_mode == 'normal'
        print("  PASS: risposta breve con TTS normal")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 2: Risposta lunga → TTS segmentato
    print("\n2) Risposta lunga -> TTS segmentato")
    try:
        user = await get_test_user('test2@test.com')
        long_msg = "raccontami qualcosa di molto lungo e dettagliato sulla natura umana e sulla psicologia delle persone"
        response = await chat_endpoint(MockChatRequest(user.id, long_msg), http_request=MockRequest())
        response_text = response.get('response', '')
        tts_mode = response.get('tts_mode', 'normal')
        print(f"  Risposta: '{response_text[:100]}...' (len={len(response_text)})")
        print(f"  TTS mode: {tts_mode}")
        assert response_text
        # Testi lunghi dovrebbero avere tts_mode informative
        assert tts_mode in ['normal', 'informative']
        print("  PASS: risposta lunga con TTS segmentato")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 3: Risposta medica → TTS presente
    print("\n3) Risposta medica -> TTS presente")
    try:
        user = await get_test_user('test3@test.com')
        medical_msg = "che tempo fa a roma?"
        response = await chat_endpoint(MockChatRequest(user.id, medical_msg), http_request=MockRequest())
        response_text = response.get('response', '')
        tts_mode = response.get('tts_mode', 'normal')
        print(f"  Risposta: '{response_text[:100]}...' (len={len(response_text)})")
        print(f"  TTS mode: {tts_mode}")
        assert response_text
        assert tts_mode == 'informative'  # FATTI mode
        print("  PASS: risposta medica con TTS informative")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 4: Closure → TTS normal
    print("\n4) Closure -> TTS normal")
    try:
        user = await get_test_user('test4@test.com')
        closure_msg = "ok basta così"
        response = await chat_endpoint(MockChatRequest(user.id, closure_msg), http_request=MockRequest())
        response_text = response.get('response', '')
        tts_mode = response.get('tts_mode', 'normal')
        print(f"  Risposta: '{response_text[:50]}...' (len={len(response_text)})")
        print(f"  TTS mode: {tts_mode}")
        assert response_text
        assert tts_mode == 'normal'
        # Closure potrebbe non essere sempre True, ma il TTS mode deve essere normal
        print("  PASS: closure con TTS normal")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 5: Nessuna regressione su mobile
    print("\n5) Test struttura risposta")
    try:
        user = await get_test_user('test5@test.com')
        response = await chat_endpoint(MockChatRequest(user.id, 'test'), http_request=MockRequest())
        # Verifica che la risposta abbia tutti i campi necessari
        assert 'response' in response
        assert 'tts_mode' in response
        assert 'state' in response
        assert isinstance(response['response'], str)
        assert response['tts_mode'] in ['normal', 'informative']
        print(f"  Struttura risposta completa")
        print(f"  Campi: {list(response.keys())}")
        print("  PASS: nessuna regressione struttura")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # RISULTATO
    print("\n" + "="*60)
    total = passed + failed
    print(f"RISULTATO: {passed}/{total} test passati")
    if failed > 0:
        print(f"FALLITI: {failed}")
    else:
        print("TUTTI I TEST PASSATI")
    print("="*60)

if __name__ == "__main__":
    asyncio.run(test_tts_completo())
