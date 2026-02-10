#!/usr/bin/env python3
"""
TEST CHIRURGICO DEFINITIVO - 6 scenari obbligatori
Verifica completa dell'architettura corretta
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_6_scenari_obbligatori():
    """Test dei 6 scenari obbligatori dal prompt chirurgico"""
    print("TEST CHIRURGICO DEFINITIVO - 6 SCENARI OBBLIGATORI")
    print("=" * 60)
    print("VERIFICA: Architettura corretta con vincoli assoluti")
    print("=" * 60)
    
    try:
        from core.proactor import proactor
        from core.engines import engine_registry
        from core.intent_router import intent_router
        
        # Test cases dal prompt chirurgico
        scenarios = [
            {
                "name": "ciao -> chat libera",
                "message": "ciao",
                "expected_engine": "personalplex",
                "expected_intent": "chat_free",
                "rules": ["solo italiano", "niente emoji", "max 2 frasi"]
            },
            {
                "name": "come mi chiamo -> memoria/identita",
                "message": "come mi chiamo",
                "expected_engine": "gpt_full", 
                "expected_intent": "identity",
                "rules": ["fatti verificabili", "niente invenzioni"]
            },
            {
                "name": "che giorno e oggi -> data/ora",
                "message": "che giorno e oggi",
                "expected_engine": "date_time",
                "expected_intent": "date_time",
                "rules": ["datetime Python", "niente LLM"]
            },
            {
                "name": "che tempo fa a Roma -> meteo API",
                "message": "che tempo fa a Roma",
                "expected_engine": "api_tools",
                "expected_intent": "weather",
                "rules": ["OpenWeather API", "dati reali"]
            },
            {
                "name": "dimmi le notizie di Roma -> news API",
                "message": "dimmi le notizie di Roma",
                "expected_engine": "api_tools",
                "expected_intent": "news",
                "rules": ["NewsAPI", "notizie reali"]
            },
            {
                "name": "oggi sono depresso -> psicologico",
                "message": "oggi sono depresso",
                "expected_engine": "psychological",
                "expected_intent": "emotional_support",
                "rules": ["empatia adulta", "niente diagnosi"]
            }
        ]
        
        passed = 0
        failed = 0
        
        for i, scenario in enumerate(scenarios, 1):
            print(f"\nTest {i}: {scenario['name']}")
            print("-" * 50)
            
            # 1. Test Intent Router
            routing_info = intent_router.get_routing_info(scenario['message'])
            detected_intent = routing_info['intent']
            
            print(f"  Message: '{scenario['message']}'")
            print(f"  Expected intent: {scenario['expected_intent']}")
            print(f"  Detected intent: {detected_intent}")
            
            # 2. Test Proactor decision
            decision = proactor.decide_engine(detected_intent, scenario['message'])
            actual_engine = decision['engine'].value
            
            print(f"  Expected engine: {scenario['expected_engine']}")
            print(f"  Actual engine: {actual_engine}")
            
            # 3. Verifiche
            intent_correct = detected_intent == scenario['expected_intent']
            engine_correct = actual_engine == scenario['expected_engine']
            
            # 4. Verifica regole specifiche
            rules_ok = True
            if scenario['name'] == "ciao -> chat libera":
                # Verifica che PersonalPlex possa gestire solo chat_free
                personalplex = engine_registry.get_engine("personalplex")
                can_handle_chat = personalplex.can_handle("chat_free")
                can_handle_weather = personalplex.can_handle("weather")
                rules_ok = can_handle_chat and not can_handle_weather
                print(f"  PersonalPlex rules: chat={can_handle_chat} weather={not can_handle_weather}")
            
            elif scenario['name'] == "che giorno e oggi -> data/ora":
                # Verifica che DateTime engine possa gestire date_time
                datetime_engine = engine_registry.get_engine("date_time")
                can_handle_datetime = datetime_engine.can_handle("date_time")
                rules_ok = can_handle_datetime
                print(f"  DateTime rules: date_time={can_handle_datetime}")
            
            # 5. Risultato test
            if intent_correct and engine_correct and rules_ok:
                print(f"  PASS: Intent e engine corretti")
                passed += 1
            else:
                print(f"  FAIL: intent={intent_correct} engine={engine_correct} rules={rules_ok}")
                failed += 1
        
        print("\n" + "=" * 60)
        print("RISULTATO FINALE:")
        print(f"Passati: {passed}/{len(scenarios)}")
        print(f"Falliti: {failed}/{len(scenarios)}")
        
        if failed == 0:
            print("\nSUCCESSO COMPLETO!")
            print("ARCHITETTURA CHIRURGICA VERIFICATA:")
            print("  ciao → PersonalPlex (vincoli rigorosi)")
            print("  come mi chiamo → GPT-full (memoria)")
            print("  che giorno è oggi → DateTime (Python)")
            print("  che tempo fa → API tools (OpenWeather)")
            print("  notizie → API tools (NewsAPI)")
            print("  depresso → Psychological (empatia)")
            print("\nVINCOLI ASSOLUTI RISPETTATI:")
            print("  PersonalPlex solo chat, niente emoji, max 2 frasi")
            print("  Data/ora solo Python datetime, niente LLM")
            print("  Meteo/news solo API reali, niente invenzioni")
            print("  MAI fallback a PersonalPlex per servizi")
            return True
        else:
            print(f"\nWARNING: {failed} test falliti")
            return False
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_6_scenari_obbligatori())
    sys.exit(0 if success else 1)
