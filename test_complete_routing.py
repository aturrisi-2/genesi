#!/usr/bin/env python3
"""
TEST ROUTING COMPLETO - Verifica che il routing blocchi LLM creativo
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.intent_router import intent_router

def test_complete_routing():
    """Testa tutti i casi critici di routing"""
    
    test_cases = [
        # Chat libera - DEVE usare PersonalPlex
        {
            "input": "ciao come stai",
            "expected_intent": "chat_free",
            "should_block_creative": False,
            "description": "Chat libera -> PersonalPlex"
        },
        
        # Medico - DEVE bloccare LLM creativo
        {
            "input": "ho un gran mal di testa",
            "expected_intent": "medical_info",
            "should_block_creative": True,
            "description": "Medico -> Fonti verificate, BLOCCO LLM"
        },
        
        # Tempo - DEVE bloccare LLM creativo
        {
            "input": "che giorno è oggi",
            "expected_intent": "other",
            "should_block_creative": True,
            "description": "Tempo -> Sistema, BLOCCO LLM"
        },
        
        {
            "input": "che ore sono",
            "expected_intent": "other",
            "should_block_creative": True,
            "description": "Ore -> Sistema, BLOCCO LLM"
        },
        
        # Storico - DEVE bloccare LLM creativo
        {
            "input": "chi era Leonardo da Vinci",
            "expected_intent": "historical_info",
            "should_block_creative": True,
            "description": "Storico -> Wikipedia, BLOCCO LLM"
        },
        
        # Meteo - DEVE bloccare LLM creativo
        {
            "input": "che tempo fa a Roma",
            "expected_intent": "weather",
            "should_block_creative": True,
            "description": "Meteo -> API, BLOCCO LLM"
        },
        
        # News - DEVE bloccare LLM creativo
        {
            "input": "quali sono le notizie di oggi",
            "expected_intent": "news",
            "should_block_creative": True,
            "description": "News -> API, BLOCCO LLM"
        },
        
        # Emotivo - NON deve bloccare (usa ramo psicologico)
        {
            "input": "sono triste",
            "expected_intent": "emotional_support",
            "should_block_creative": False,
            "description": "Emotivo -> Ramo psicologico"
        }
    ]
    
    print("TEST ROUTING COMPLETO - BLOCCO LLM CREATIVO")
    print("=" * 60)
    
    passed = 0
    failed = 0
    
    for i, test in enumerate(test_cases, 1):
        input_text = test["input"]
        expected_intent = test["expected_intent"]
        should_block = test["should_block_creative"]
        description = test["description"]
        
        # Applica intent router
        routing_info = intent_router.get_routing_info(input_text)
        
        # Verifica
        intent_ok = routing_info["intent"] == expected_intent
        block_ok = routing_info["block_creative_llm"] == should_block
        
        success = intent_ok and block_ok
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
        print(f"Block Creative: {routing_info['block_creative_llm']} (expected: {should_block}) {'OK' if block_ok else 'FAIL'}")
        
        if should_block:
            print(f"LLM CREATIVO BLOCCATO - risposta affidabile")
        else:
            print(f"LLM CREATIVO CONSENTITO - risposta naturale")
        
        if not success:
            print(f"ERRORE: Routing non corretto!")
    
    print("\n" + "=" * 60)
    print(f"RISULTATI: {passed} passati, {failed} falliti")
    
    if failed == 0:
        print("TUTTI I TEST PASSATI!")
        print("PersonalPlex bloccato per domande sensibili")
        print("Solo fonti verificate per medicina/storia/tempo")
        print("Creatività solo per chat libera")
        return True
    else:
        print(f"{failed} TEST FALLITI!")
        return False

if __name__ == "__main__":
    success = test_complete_routing()
    sys.exit(0 if success else 1)
