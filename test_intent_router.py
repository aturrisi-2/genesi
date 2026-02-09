#!/usr/bin/env python3
"""
TEST INTENT ROUTER DETERMINISTICO
Verifica che il routing classifichi correttamente i messaggi
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.intent_router import intent_router

def test_intent_router():
    """Testa tutti i casi di routing"""
    
    test_cases = [
        # Chat libera
        {
            "input": "ciao come stai",
            "expected_intent": "chat_free",
            "expected_source": "personalplex",
            "should_block_creative": False,
            "description": "Saluto normale"
        },
        
        # Medico
        {
            "input": "ho un gran mal di testa",
            "expected_intent": "medical_info",
            "expected_source": "verified_knowledge",
            "should_block_creative": True,
            "description": "Sintomo medico"
        },
        
        {
            "input": "mi fa male la pancia",
            "expected_intent": "medical_info",
            "expected_source": "verified_knowledge",
            "should_block_creative": True,
            "description": "Dolore medico"
        },
        
        # Storico
        {
            "input": "chi era Napoleone",
            "expected_intent": "historical_info",
            "expected_source": "verified_knowledge",
            "should_block_creative": True,
            "description": "Persona storica"
        },
        
        # Meteo
        {
            "input": "che tempo fa a Roma",
            "expected_intent": "weather",
            "expected_source": "weather_api",
            "should_block_creative": True,
            "description": "Meteo"
        },
        
        # News
        {
            "input": "quali sono le notizie di oggi",
            "expected_intent": "news",
            "expected_source": "news_api",
            "should_block_creative": True,
            "description": "Notizie"
        },
        
        # Emotivo
        {
            "input": "sono triste oggi",
            "expected_intent": "emotional_support",
            "expected_source": "psychological_branch",
            "should_block_creative": False,
            "description": "Supporto emotivo"
        }
    ]
    
    print("TEST INTENT ROUTER DETERMINISTICO")
    print("=" * 50)
    
    passed = 0
    failed = 0
    
    for i, test in enumerate(test_cases, 1):
        input_text = test["input"]
        expected_intent = test["expected_intent"]
        expected_source = test["expected_source"]
        should_block = test["should_block_creative"]
        description = test["description"]
        
        # Applica intent router
        routing_info = intent_router.get_routing_info(input_text)
        
        # Verifica
        intent_ok = routing_info["intent"] == expected_intent
        source_ok = routing_info["source"] == expected_source
        block_ok = routing_info["block_creative_llm"] == should_block
        
        success = intent_ok and source_ok and block_ok
        if success:
            passed += 1
            status = "PASS"
        else:
            failed += 1
            status = "FAIL"
        
        print(f"\nTest {i}: {description}")
        print(f"Status: {status}")
        print(f"Input: '{input_text}'")
        print(f"Intent: {routing_info['intent']} (expected: {expected_intent}) {'OK' if intent_ok else 'FAIL'}")
        print(f"Source: {routing_info['source']} (expected: {expected_source}) {'OK' if source_ok else 'FAIL'}")
        print(f"Block Creative: {routing_info['block_creative_llm']} (expected: {should_block}) {'OK' if block_ok else 'FAIL'}")
        
        if not success:
            print(f"ERRORE: Routing non corrispondente!")
    
    print("\n" + "=" * 50)
    print(f"RISULTATI: {passed} passati, {failed} falliti")
    
    if failed == 0:
        print("TUTTI I TEST PASSATI!")
        return True
    else:
        print(f"{failed} TEST FALLITI!")
        return False

if __name__ == "__main__":
    success = test_intent_router()
    sys.exit(0 if success else 1)
