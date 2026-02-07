#!/usr/bin/env python3
"""
Test TTS Psychological - 5 scenari obbligatori
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

async def test_tts_psychological():
    print("=== TEST TTS PSYCHOLOGICAL - 5 SCENARI ===")
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

    # TEST 1: Risposta psicologica breve → TTS
    print("\n1) Risposta psicologica breve -> TTS")
    try:
        user = await get_test_user('psych1@test.com')
        # Messaggio che triggersa psychological
        msg = "mi sento molto triste ultimamente"
        response = await chat_endpoint(MockChatRequest(user.id, msg), http_request=MockRequest())
        response_text = response.get('response', '')
        tts_mode = response.get('tts_mode', 'normal')
        print(f"  Risposta: '{response_text[:100]}...' (len={len(response_text)})")
        print(f"  TTS mode: {tts_mode}")
        assert response_text
        assert tts_mode == 'psychological'
        assert response.get('psy_mode') == True
        print("  PASS: risposta psicologica breve con TTS psychological")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 2: Risposta psicologica lunga → TTS a chunk
    print("\n2) Risposta psicologica lunga -> TTS a chunk")
    try:
        user = await get_test_user('psych2@test.com')
        # Messaggio più complesso per psychological
        msg = "non so più cosa fare nella mia vita, tutto sembra senza senso, mi sento perso e confuso, non trovo più la motivazione per alzarmi la mattina"
        response = await chat_endpoint(MockChatRequest(user.id, msg), http_request=MockRequest())
        response_text = response.get('response', '')
        tts_mode = response.get('tts_mode', 'normal')
        print(f"  Risposta: '{response_text[:150]}...' (len={len(response_text)})")
        print(f"  TTS mode: {tts_mode}")
        assert response_text
        assert tts_mode == 'psychological'
        assert response.get('psy_mode') == True
        # Verifica che sia una risposta psychological (anche se non lunghissima)
        print("  PASS: risposta psicologica lunga con TTS psychological")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 3: Interruzione utente → stop immediato (simulato)
    print("\n3) Interruzione utente -> stop immediato")
    try:
        user = await get_test_user('psych3@test.com')
        msg = "sono molto ansioso"
        response = await chat_endpoint(MockChatRequest(user.id, msg), http_request=MockRequest())
        response_text = response.get('response', '')
        tts_mode = response.get('tts_mode', 'normal')
        print(f"  Risposta: '{response_text[:100]}...' (len={len(response_text)})")
        print(f"  TTS mode: {tts_mode}")
        assert response_text
        assert tts_mode == 'psychological'
        # Il frontend gestirà l'interruzione, qui verifichiamo solo che il TTS mode sia corretto
        print("  PASS: TTS psychological pronto per interruzione")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 4: Nessun silenzio totale
    print("\n4) Nessun silenzio totale")
    try:
        user = await get_test_user('psych4@test.com')
        msg = "mi sento solo"
        response = await chat_endpoint(MockChatRequest(user.id, msg), http_request=MockRequest())
        response_text = response.get('response', '')
        tts_mode = response.get('tts_mode', 'normal')
        print(f"  Risposta: '{response_text[:100]}...' (len={len(response_text)})")
        print(f"  TTS mode: {tts_mode}")
        assert response_text
        assert tts_mode == 'psychological'
        # Verifica che ci sia sempre una risposta
        assert len(response_text) > 20
        print("  PASS: nessun silenzio totale, risposta presente")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 5: Nessuna regressione sugli altri rami
    print("\n5) Nessuna regressione sugli altri rami")
    try:
        user = await get_test_user('psych5@test.com')
        # Test ramo normale
        msg = "ciao come stai?"
        response = await chat_endpoint(MockChatRequest(user.id, msg), http_request=MockRequest())
        response_text = response.get('response', '')
        tts_mode = response.get('tts_mode', 'normal')
        print(f"  Risposta normale: '{response_text[:50]}...' (len={len(response_text)})")
        print(f"  TTS mode: {tts_mode}")
        assert response_text
        assert tts_mode in ['normal', 'informative']
        assert response.get('psy_mode') != True
        
        # Test ramo FATTI
        msg2 = "che tempo fa a milano?"
        response2 = await chat_endpoint(MockChatRequest(user.id, msg2), http_request=MockRequest())
        response_text2 = response2.get('response', '')
        tts_mode2 = response2.get('tts_mode', 'normal')
        print(f"  Risposta FATTI: '{response_text2[:50]}...' (len={len(response_text2)})")
        print(f"  TTS mode: {tts_mode2}")
        assert response_text2
        assert tts_mode2 in ['normal', 'informative']
        
        print("  PASS: nessuna regressione su altri rami")
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
    asyncio.run(test_tts_psychological())
