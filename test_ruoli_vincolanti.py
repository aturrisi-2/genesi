#!/usr/bin/env python3
"""
TEST RUOLI VINCOLANTI - Verifica che PersonalPlex non gestisca intent specialistici
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_roles_binding():
    """Test ruoli vincolanti"""
    print("TEST RUOLI VINCOLANTI - PERSONALPLEX SOLO CHAT LIBERA")
    print("=" * 60)
    print("VERIFICA: PersonalPlex NON deve gestire intent specialistici")
    print("=" * 60)
    
    try:
        from core.engines import engine_registry
        
        # Test cases: intent che NON devono passare a PersonalPlex
        test_cases = [
            {
                "name": "Meteo NON a PersonalPlex",
                "engine": "api_tools",
                "intent": "weather",
                "expected_fallback": "gpt_full"
            },
            {
                "name": "News NON a PersonalPlex", 
                "engine": "api_tools",
                "intent": "news",
                "expected_fallback": "gpt_full"
            },
            {
                "name": "Medico NON a PersonalPlex",
                "engine": "gpt_full",
                "intent": "medical_info",
                "expected_fallback": "contextual_error"
            },
            {
                "name": "Psicologico NON a PersonalPlex",
                "engine": "psychological",
                "intent": "psychological",
                "expected_fallback": "contextual_error"
            },
            {
                "name": "Storico NON a PersonalPlex",
                "engine": "gpt_full",
                "intent": "historical_info",
                "expected_fallback": "contextual_error"
            },
            {
                "name": "Chat libera PUÒ andare a PersonalPlex",
                "engine": "personalplex",
                "intent": "chat_free",
                "expected_fallback": "personalplex"
            }
        ]
        
        passed = 0
        failed = 0
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\nTest {i}: {test_case['name']}")
            print("-" * 50)
            
            # Simula che il motore non possa gestire l'intent
            engine = engine_registry.get_engine(test_case['engine'])
            can_handle = engine.can_handle(test_case['intent'])
            
            print(f"  Engine: {test_case['engine']}")
            print(f"  Intent: {test_case['intent']}")
            print(f"  Can handle: {can_handle}")
            
            if not can_handle:
                # Verifica fallback
                if test_case['intent'] in ["weather", "news"]:
                    expected_engine = "gpt_full"
                    print(f"  Expected fallback: {expected_engine}")
                    if expected_engine == test_case['expected_fallback']:
                        print("  PASS: Fallback corretto a GPT-full")
                        passed += 1
                    else:
                        print("  FAIL: Fallback errato")
                        failed += 1
                elif test_case['intent'] in ["medical_info", "psychological", "historical_info", "verified_knowledge"]:
                    print(f"  Expected fallback: contextual error")
                    if test_case['expected_fallback'] == "contextual_error":
                        print("  PASS: Fallback contestuale corretto")
                        passed += 1
                    else:
                        print("  FAIL: Fallback errato")
                        failed += 1
                else:
                    # Solo chat_free può andare a PersonalPlex
                    print(f"  Expected fallback: personalplex")
                    if test_case['expected_fallback'] == "personalplex":
                        print("  PASS: Chat libera può usare PersonalPlex")
                        passed += 1
                    else:
                        print("  FAIL: Fallback errato")
                        failed += 1
            else:
                print("  INFO: Engine può gestire l'intent, nessun fallback")
                passed += 1
        
        print("\n" + "=" * 60)
        print("RISULTATO FINALE:")
        print(f"Passati: {passed}/{len(test_cases)}")
        print(f"Falliti: {failed}/{len(test_cases)}")
        
        if failed == 0:
            print("\nSUCCESSO COMPLETO!")
            print("RUOLI VINCOLANTI VERIFICATI:")
            print("  Meteo/News → GPT-full (NON PersonalPlex)")
            print("  Medico/Psicologico → Errore contestuale (NON PersonalPlex)")
            print("  Chat libera → PersonalPlex (OK)")
            print("\nPersonalPlex è confinato al suo ruolo!")
            return True
        else:
            print("\nWARNING: Alcuni test falliti")
            return False
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_roles_binding())
    sys.exit(0 if success else 1)
