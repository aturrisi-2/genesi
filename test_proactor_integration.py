#!/usr/bin/env python3
"""
Test integrazione Proactor + Local LLM + ChatGPT
Verifica che la pipeline a tre livelli funzioni correttamente
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from core.intent_engine import IntentEngine
from core.response_generator import ResponseGenerator
from core.local_llm import local_llm

class MockUser:
    def __init__(self):
        self.profile = {}

class MockCognitiveState:
    pass

class MockTone:
    empathy = 0.5

def test_proactor_integration():
    """Test completo pipeline Proactor -> Local LLM -> ChatGPT"""
    
    print("🧪 TEST INTEGRAZIONE PROACTOR + LOCAL LLM + CHATGPT")
    print("=" * 60)
    
    proactor = IntentEngine()
    response_generator = ResponseGenerator()
    user = MockUser()
    cognitive_state = MockCognitiveState()
    tone = MockTone()
    
    test_cases = [
        # Input vuoto/minimo
        ("", "empty_input"),
        ("a", "empty_input"),
        
        # Rumore/nonsense
        ("oooo", "noise_input"),
        ("aaaaa", "noise_input"),
        ("oooo oooo oooo", "noise_input"),
        
        # Input ambigui (dovrebbero chiamare Local LLM)
        ("ciao", "fallback_gpt"),  # Con Local LLM down, dovrebbe passare a ChatGPT
        ("test", "fallback_gpt"),  # Con Local LLM down, "test" è input semplice → ChatGPT
        
        # Input validi (dovrebbero passare a ChatGPT)
        ("questa è una prova di registrazione", "chatgpt"),
        ("che tempo fa oggi", "chatgpt"),
        ("come stai", "chatgpt"),
    ]
    
    results = []
    
    for input_text, expected_behavior in test_cases:
        print(f"\n📝 Test: '{input_text}' → {expected_behavior}")
        
        # 1. Proactor decision
        intent = proactor.decide(
            input_text,
            user,
            cognitive_state,
            [],
            [],
            tone
        )
        
        # 2. ResponseGenerator check
        should_respond = intent.get("should_respond", True)
        decision = intent.get("decision", "escalate")
        
        # 3. Verifica comportamento
        if expected_behavior == "empty_input":
            success = not should_respond and decision == "silence"
        elif expected_behavior == "noise_input":
            success = not should_respond and decision == "silence"
        elif expected_behavior == "fallback_gpt":
            # Con Local LLM down, input semplici dovrebbero passare a ChatGPT
            success = should_respond and decision != "silence"
        elif expected_behavior == "chatgpt":
            success = should_respond and decision != "silence"
        else:
            success = False
        
        results.append((input_text, expected_behavior, success))
        print(f"✅ Success: {success}")
        print(f"   should_respond: {should_respond}")
        print(f"   decision: {decision}")
    
    print("\n" + "=" * 60)
    print("📊 RISULTATI TEST")
    
    passed = sum(1 for _, _, success in results if success)
    total = len(results)
    
    for input_text, expected, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} '{input_text}' → {expected}")
    
    print(f"\n🎯 TOTALE: {passed}/{total} test passati")
    
    if passed == total:
        print("🎉 Tutti i test passati! Integrazione funzionante.")
        return True
    else:
        print("⚠️ Alcuni test falliti. Verificare implementazione.")
        return False

def test_local_llm_fallback():
    """Test Local LLM con fallback"""
    print("\n🧪 TEST LOCAL LLM FALLBACK")
    print("=" * 40)
    
    # Test con input di rumore
    noise_inputs = ["oooo", "aaaa", "test test test test"]
    
    for noise_input in noise_inputs:
        print(f"\n📝 Test Local LLM: '{noise_input}'")
        
        try:
            result = local_llm.analyze(noise_input)
            print(f"   intent: {result.get('intent')}")
            print(f"   confidence: {result.get('confidence'):.2f}")
            print(f"   is_noise: {result.get('is_noise')}")
            print(f"   should_escalate: {result.get('should_escalate')}")
            
            # Verifica struttura
            required_keys = ["intent", "confidence", "clean_text", "is_noise", "should_escalate"]
            has_all_keys = all(key in result for key in required_keys)
            print(f"   structure_ok: {has_all_keys}")
            
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print("\n✅ Local LLM fallback test completato")

if __name__ == "__main__":
    # Esegui test
    success = test_proactor_integration()
    test_local_llm_fallback()
    
    if success:
        print("\n🎯 INTEGRAZIONE PROACTOR COMPLETATA CON SUCCESSO!")
        sys.exit(0)
    else:
        print("\n❌ INTEGRAZIONE PROACTOR DA VERIFICARE")
        sys.exit(1)
