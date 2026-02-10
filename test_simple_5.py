#!/usr/bin/env python3
"""
TEST SEMPLIFICATO 5 SCENARI
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_simple():
    """Test semplice 5 scenari"""
    print("TEST 5 SCENARI - ARCHITETTURA CORRETTA")
    print("=" * 50)
    
    try:
        from core.proactor import proactor
        
        # Test 1: ciao -> personalplex
        decision = proactor.decide_engine("chat_free", "ciao")
        engine1 = decision['engine'].value
        print(f"Test 1 - ciao: {engine1} (expected: personalplex)")
        
        # Test 2: meteo -> api_tools
        decision = proactor.decide_engine("chat_free", "che tempo fa a Roma")
        engine2 = decision['engine'].value
        print(f"Test 2 - meteo: {engine2} (expected: api_tools)")
        
        # Test 3: notizie -> api_tools
        decision = proactor.decide_engine("chat_free", "dimmi le notizie su Roma")
        engine3 = decision['engine'].value
        print(f"Test 3 - notizie: {engine3} (expected: api_tools)")
        
        # Test 4: medico -> gpt_full
        decision = proactor.decide_engine("chat_free", "ho mal di testa")
        engine4 = decision['engine'].value
        print(f"Test 4 - medico: {engine4} (expected: gpt_full)")
        
        # Test 5: psicologico -> psychological
        decision = proactor.decide_engine("chat_free", "mi sento depresso")
        engine5 = decision['engine'].value
        print(f"Test 5 - psicologico: {engine5} (expected: psychological)")
        
        # Verifiche
        tests = [
            (engine1 == "personalplex", "ciao"),
            (engine2 == "api_tools", "meteo"),
            (engine3 == "api_tools", "notizie"),
            (engine4 == "gpt_full", "medico"),
            (engine5 == "psychological", "psicologico")
        ]
        
        passed = sum(1 for test, _ in tests if test)
        failed = len(tests) - passed
        
        print(f"\nRisultato: {passed}/{len(tests)} passati")
        
        if passed == 5:
            print("SUCCESSO: Architettura corretta!")
            print("PersonalPlex solo per chat, specialistici per servizi")
            return True
        else:
            print(f"WARNING: {failed} test falliti")
            return False
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_simple())
    sys.exit(0 if success else 1)
