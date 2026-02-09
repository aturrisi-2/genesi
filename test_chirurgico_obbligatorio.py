#!/usr/bin/env python3
"""
TEST OBBLIGATORI CHIRURGICI - 5 scenari critici
Verifica che la riorganizzazione cognitiva funzioni correttamente
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_scenario_1_ciao():
    """Test 1: 'ciao' → PersonalPlex"""
    print("TEST 1: CHAT LIBERA - 'ciao'")
    print("-" * 40)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        
        # Simula stato utente
        state = CognitiveState.build("test_user")
        
        # Esegui pipeline
        result = await surgical_pipeline.process_message(
            user_message="ciao",
            cognitive_state=state,
            recent_memories=[],
            relevant_memories=[],
            tone={},
            intent={"should_respond": True}
        )
        
        response = result.get("final_text", "")
        engine_used = result.get("engine_used", "")
        
        print(f"  Engine: {engine_used}")
        print(f"  Response: {response}")
        
        # Verifiche
        checks = [
            engine_used == "personalplex",
            len(response) > 3,
            "ciao" not in response.lower(),  # Non dovrebbe ripetere
            len(response) < 100  # Breve
        ]
        
        if all(checks):
            print("  PASS: Chat libera con PersonalPlex")
            return True
        else:
            print("  FAIL: Qualche check fallito")
            return False
            
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

async def test_scenario_2_meteo():
    """Test 2: 'che tempo fa a roma' → API tools"""
    print("\nTEST 2: METEO - 'che tempo fa a roma'")
    print("-" * 40)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        
        state = CognitiveState.build("test_user")
        
        result = await surgical_pipeline.process_message(
            user_message="che tempo fa a roma",
            cognitive_state=state,
            recent_memories=[],
            relevant_memories=[],
            tone={},
            intent={"should_respond": True}
        )
        
        response = result.get("final_text", "")
        engine_used = result.get("engine_used", "")
        
        print(f"  Engine: {engine_used}")
        print(f"  Response: {response}")
        
        # Verifiche
        checks = [
            engine_used == "api_tools",
            "roma" in response.lower() or "meteo" in response.lower(),
            len(response) > 5,
            "personalplex" not in engine_used
        ]
        
        if all(checks):
            print("  PASS: Meteo con API tools")
            return True
        else:
            print("  FAIL: Qualche check fallito")
            return False
            
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

async def test_scenario_3_news():
    """Test 3: 'dimmi le notizie su roma' → API tools"""
    print("\nTEST 3: NEWS - 'dimmi le notizie su roma'")
    print("-" * 40)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        
        state = CognitiveState.build("test_user")
        
        result = await surgical_pipeline.process_message(
            user_message="dimmi le notizie su roma",
            cognitive_state=state,
            recent_memories=[],
            relevant_memories=[],
            tone={},
            intent={"should_respond": True}
        )
        
        response = result.get("final_text", "")
        engine_used = result.get("engine_used", "")
        
        print(f"  Engine: {engine_used}")
        print(f"  Response: {response}")
        
        # Verifiche
        checks = [
            engine_used == "api_tools",
            "notizie" in response.lower() or "roma" in response.lower(),
            len(response) > 5,
            "personalplex" not in engine_used
        ]
        
        if all(checks):
            print("  PASS: News con API tools")
            return True
        else:
            print("  FAIL: Qualche check fallito")
            return False
            
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

async def test_scenario_4_dns():
    """Test 4: 'cos'è un dns' → GPT-full"""
    print("\nTEST 4: DEFINIZIONE - 'cos'è un dns'")
    print("-" * 40)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        
        state = CognitiveState.build("test_user")
        
        result = await surgical_pipeline.process_message(
            user_message="cos'è un dns",
            cognitive_state=state,
            recent_memories=[],
            relevant_memories=[],
            tone={},
            intent={"should_respond": True}
        )
        
        response = result.get("final_text", "")
        engine_used = result.get("engine_used", "")
        
        print(f"  Engine: {engine_used}")
        print(f"  Response: {response}")
        
        # Verifiche
        checks = [
            engine_used == "gpt_full",
            "dns" in response.lower(),
            len(response) > 10,
            "personalplex" not in engine_used,
            "domain" in response.lower() or "sistema" in response.lower()
        ]
        
        if all(checks):
            print("  PASS: Definizione con GPT-full")
            return True
        else:
            print("  FAIL: Qualche check fallito")
            return False
            
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

async def test_scenario_5_depresso():
    """Test 5: 'oggi mi sento depresso' → Psychological"""
    print("\nTEST 5: PSICOLOGICO - 'oggi mi sento depresso'")
    print("-" * 40)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        
        state = CognitiveState.build("test_user")
        
        result = await surgical_pipeline.process_message(
            user_message="oggi mi sento depresso",
            cognitive_state=state,
            recent_memories=[],
            relevant_memories=[],
            tone={},
            intent={"should_respond": True}
        )
        
        response = result.get("final_text", "")
        engine_used = result.get("engine_used", "")
        
        print(f"  Engine: {engine_used}")
        print(f"  Response: {response}")
        
        # Verifiche
        checks = [
            engine_used == "psychological",
            len(response) > 10,
            "depresso" not in response.lower(),  # Non dovrebbe ripetere
            "personalplex" not in engine_used,
            "capisco" in response.lower() or "qui" in response.lower()
        ]
        
        if all(checks):
            print("  PASS: Supporto psicologico")
            return True
        else:
            print("  FAIL: Qualche check fallito")
            return False
            
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

async def main():
    """Esegui test chirurgici obbligatori"""
    print("TEST OBBLIGATORI CHIRURGICI - 5 SCENARI CRITICI")
    print("=" * 60)
    
    tests = [
        ("CHAT LIBERA - Ciao", test_scenario_1_ciao),
        ("METEO - Roma", test_scenario_2_meteo),
        ("NEWS - Notizie Roma", test_scenario_3_news),
        ("DEFINIZIONE - DNS", test_scenario_4_dns),
        ("PSICOLOGICO - Depresso", test_scenario_5_depresso),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if await test_func():
                passed += 1
                print(f"PASS {test_name}: OK")
            else:
                failed += 1
                print(f"FAIL {test_name}: KO")
        except Exception as e:
            failed += 1
            print(f"ERROR {test_name}: {e}")
    
    print("\n" + "=" * 60)
    print("RISULTATO CHIRURGICO:")
    print(f"Passati: {passed}/{len(tests)}")
    print(f"Falliti: {failed}/{len(tests)}")
    
    if failed == 0:
        print("SUCCESS: Riorganizzazione cognitiva completata!")
        print("\nFlusso chirurgico verificato:")
        print("- ciao → PersonalPlex ✅")
        print("- meteo → API tools ✅")  
        print("- news → API tools ✅")
        print("- dns → GPT-full ✅")
        print("- depresso → Psychological ✅")
        print("\nGenesi è pronta per production!")
        return True
    else:
        print("WARNING: Riorganizzazione incompleta")
        print("Revisionare implementazione chirurgica")
        return False

if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
