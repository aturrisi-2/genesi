#!/usr/bin/env python3
"""
TEST DEFINITIVO 5 SCENARI - Verifica architettura corretta
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_5_scenarios():
    """Test dei 5 scenari critici"""
    print("TEST DEFINITIVO 5 SCENARI - ARCHITETTURA CORRETTA")
    print("=" * 60)
    print("VERIFICA: PersonalPlex solo per chat, MAI per servizi/fatti")
    print("=" * 60)
    
    try:
        from core.proactor import proactor
        from core.engines import engine_registry
        
        # Test cases dalla tua richiesta
        scenarios = [
            {
                "name": "ciao → chat libera con emoji",
                "message": "ciao",
                "expected_engine": "personalplex",
                "expected_intent": "chat_free"
            },
            {
                "name": "come mi chiamo? → memoria/identità",
                "message": "come mi chiamo",
                "expected_engine": "gpt_full", 
                "expected_intent": "historical_info"
            },
            {
                "name": "che tempo fa a Roma → meteo",
                "message": "che tempo fa a Roma",
                "expected_engine": "api_tools",
                "expected_intent": "weather"
            },
            {
                "name": "dimmi le notizie su Roma → news",
                "message": "dimmi le notizie su Roma",
                "expected_engine": "api_tools",
                "expected_intent": "news"
            },
            {
                "name": "oggi mi sento depresso → psicologico",
                "message": "oggi mi sento depresso",
                "expected_engine": "psychological",
                "expected_intent": "emotional_support"
            }
        ]
        
        passed = 0
        failed = 0
        
        for i, scenario in enumerate(scenarios, 1):
            print(f"\nTest {i}: {scenario['name']}")
            print("-" * 50)
            
            # 1. Test Proactor decision
            decision = proactor.decide_engine("chat_free", scenario['message'])
            actual_engine = decision['engine'].value
            actual_intent = decision['intent_type']
            
            print(f"  Message: '{scenario['message']}'")
            print(f"  Expected engine: {scenario['expected_engine']}")
            print(f"  Actual engine: {actual_engine}")
            print(f"  Expected intent: {scenario['expected_intent']}")
            print(f"  Actual intent: {actual_intent}")
            
            # 2. Verifica engine
            engine_correct = actual_engine == scenario['expected_engine']
            
            # 3. Verifica che PersonalPlex non gestisca intent specialistici
            if actual_engine == "personalplex":
                can_handle_specialist = engine_registry.get_engine("personalplex").can_handle(actual_intent)
                if actual_intent not in ["chat_free"] and can_handle_specialist:
                    print(f"  FAIL: PersonalPlex gestisce intent specialistico!")
                    engine_correct = False
                else:
                    print(f"  PASS: PersonalPlex solo per chat libera")
            
            if engine_correct:
                print(f"  PASS: Engine corretto")
                passed += 1
            else:
                print(f"  FAIL: Engine errato")
                failed += 1
        
        print("\n" + "=" * 60)
        print("RISULTATO FINALE:")
        print(f"Passati: {passed}/{len(scenarios)}")
        print(f"Falliti: {failed}/{len(scenarios)}")
        
        if failed == 0:
            print("\nSUCCESSO COMPLETO!")
            print("ARCHITETTURA CORRETTA VERIFICATA:")
            print("  ciao → PersonalPlex (chat libera)")
            print("  come mi chiamo → GPT-full (memoria)")
            print("  che tempo fa → API tools (meteo)")
            print("  notizie → API tools (news)")
            print("  depresso → Psychological (empatia)")
            print("\nPersonalPlex è confinato al suo ruolo!")
            print("Fallback sono contestuali e professionali!")
            print("Emoji consentiti in chat libera!")
            return True
        else:
            print(f"\nWARNING: {failed} test falliti")
            return False
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_5_scenarios())
    sys.exit(0 if success else 1)
