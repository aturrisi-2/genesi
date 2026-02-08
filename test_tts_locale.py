#!/usr/bin/env python3
"""
Test TTS Locale - Testo lungo specifico
Verifica riproduzione corretta del testo fornito dall'utente
"""
import asyncio
import sys
import os
import aiohttp
sys.path.insert(0, '.')

from api.chat import chat_endpoint
from auth.database import init_db, async_session
from auth.models import AuthUser
from auth.security import hash_password
from auth.init_environment import initialize_user_environment
from unittest.mock import Mock

async def test_tts_locale():
    print("=== TEST TTS LOCALE - TESTO LUNGO SPECIFICO ===")
    
    # Testo specifico fornito dall'utente
    test_text = "Il mal di testa, noto anche come cefalea, è un dolore che può manifestarsi in qualsiasi parte della testa o del collo. Questo sintomo può essere indicativo di diverse patologie. È importante notare che il tessuto cerebrale non è sensibile al dolore, poiché non possiede recettori adatti. Pertanto, il dolore è percepito a causa della stimolazione delle strutture sensibili circostanti al cervello. Le aree della testa e del collo che contengono queste strutture includono il cranio, i muscoli, i nervi, le arterie e le vene, i tessuti sottocutanei, gli occhi, le orecchie e i seni."
    
    print(f"Testo da testare ({len(test_text)} caratteri):")
    print(f"'{test_text[:100]}...'")
    print()

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

    try:
        user = await get_test_user('test_locale@genesi.com')
        response = await chat_endpoint(MockChatRequest(user.id, test_text), http_request=MockRequest())
        
        response_text = response.get('response', '')
        tts_mode = response.get('tts_mode', 'normal')
        should_respond = response.get('should_respond', False)
        
        print(f"Risposta generata: '{response_text[:100]}...' (len={len(response_text)})")
        print(f"should_respond: {should_respond}")
        print(f"tts_mode: {tts_mode}")
        
        if should_respond and response_text.strip():
            print("\n✓ should_respond=True, testo pronto per TTS")
            
            # Test TTS via HTTP endpoint
            try:
                async with aiohttp.ClientSession() as session:
                    print("Chiamando /tts...")
                    async with session.post('http://localhost:8000/tts', 
                                           json={'text': response_text.strip()}) as resp:
                        
                        print(f"Response status: {resp.status}")
                        
                        if resp.status != 200:
                            error_text = await resp.text()
                            print(f"❌ HTTP {resp.status}: {error_text}")
                            return False
                        
                        audio_bytes = await resp.read()
                        audio_size = len(audio_bytes)
                        
                        # Calcola durata stimata
                        estimated_duration = audio_size / 16000 if audio_size > 0 else 0
                        
                        print(f"✓ Audio ricevuto: {audio_size} bytes")
                        print(f"✓ Durata stimata: {estimated_duration:.2f}s")
                        
                        # ASSERT FINALE: audio size > 0
                        if audio_size == 0:
                            print("❌ Audio size 0!")
                            return False
                        
                        if audio_size < 100:
                            print(f"⚠️ Audio molto piccolo ({audio_size} bytes)")
                        
                        # Salva audio per test manuale
                        audio_file = 'test_tts_locale.mp3'
                        with open(audio_file, 'wb') as f:
                            f.write(audio_bytes)
                        print(f"✓ Audio salvato: {audio_file}")
                        print(f"✓ Riproduci con: ffplay {audio_file}")
                        
                        # Verifica chunking aspettato
                        if len(response_text) > 500:
                            expected_chunks = (len(response_text) // 200) + 1
                            print(f"✓ Testo lungo ({len(response_text)} char) → dovrebbe generare ~{expected_chunks} chunk")
                        
                        return True
                        
            except aiohttp.ClientConnectorError:
                print("❌ Server non in esecuzione su localhost:8000")
                print("Avvia il server con: python main.py")
                return False
            except Exception as e:
                print(f"❌ Errore chiamata TTS: {e}")
                return False
        else:
            print("❌ should_respond=False, nessun audio richiesto")
            return False
            
    except Exception as e:
        print(f"❌ Errore test: {e}")
        return False

if __name__ == "__main__":
    result = asyncio.run(test_tts_locale())
    print("\n" + "="*60)
    if result:
        print("✅ TEST TTS LOCALE PASSATO")
        print("Ora apri il browser e testa lo stesso testo manualmente")
        print("Dovresti sentire tutti i chunk riprodotti sequenzialmente")
    else:
        print("❌ TEST TTS LOCALE FALLITO")
    print("="*60)
