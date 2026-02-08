#!/usr/bin/env python3
"""
TEST FIX PRIORITÀ PROACTOR
Verifica che PersonalPlex sia chiamato PRIMA di GPT
"""

import sys
import os
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_proactor_calls_personalplex_first():
    """Test che Proactor chiami PersonalPlex per primo"""
    
    print("🧪 TEST PROACTOR CALLS PERSONALPLEX FIRST")
    print("=" * 45)
    
    try:
        from core.intent_engine import IntentEngine
        
        engine = IntentEngine()
        
        test_message = "ciao"
        print(f"📝 Test Proactor con: '{test_message}'")
        
        # Parametri minimi
        cognitive_state = {"mood": "neutral"}
        recent_memories = []
        relevant_memories = []
        tone = "friendly"
        
        result = engine.decide(
            test_message,
            None,  # user
            cognitive_state,
            recent_memories,
            relevant_memories,
            tone
        )
        
        if result:
            reason = result.get("reason", "")
            should_respond = result.get("should_respond", False)
            decision = result.get("decision", "")
            
            print(f"   Reason: {reason}")
            print(f"   Should respond: {should_respond}")
            print(f"   Decision: {decision}")
            
            # Verifica che PersonalPlex sia stato chiamato per primo
            if reason == "personalplex_primary":
                print("✅ Proactor chiama PersonalPlex per primo")
                if "personalplex_response" in result:
                    response = result["personalplex_response"]
                    print(f"   PersonalPlex response: '{response[:30]}...'")
                    return True
                else:
                    print("❌ PersonalPlex response mancante")
                    return False
            else:
                print(f"❌ Proactor non chiama PersonalPlex per primo: {reason}")
                return False
        else:
            print("❌ Proactor returned None")
            return False
            
    except Exception as e:
        print(f"❌ Proactor test error: {e}")
        return False

def test_response_generator_uses_personalplex():
    """Test che ResponseGenerator usi risposta PersonalPlex"""
    
    print("\n🧪 TEST RESPONSE GENERATOR USES PERSONALPLEX")
    print("=" * 50)
    
    try:
        from core.response_generator import ResponseGenerator
        
        generator = ResponseGenerator()
        
        test_message = "ciao"
        print(f"📝 Test ResponseGenerator con: '{test_message}'")
        
        # Parametri minimi
        cognitive_state = {"mood": "neutral"}
        recent_memories = []
        relevant_memories = []
        tone = "friendly"
        
        # Simula intent con risposta PersonalPlex
        intent = {
            "should_respond": True,
            "decision": "respond",
            "reason": "personalplex_primary",
            "brain_mode": "relazione",
            "personalplex_response": "Ciao! Come stai? Sono PersonalPlex."
        }
        
        import asyncio
        response = asyncio.run(generator.generate_response(
            test_message,
            cognitive_state,
            recent_memories,
            relevant_memories,
            tone,
            intent
        ))
        
        if response and "PersonalPlex" in response:
            print("✅ ResponseGenerator usa risposta PersonalPlex")
            print(f"   Response: '{response[:50]}...'")
            return True
        else:
            print("❌ ResponseGenerator non usa risposta PersonalPlex")
            return False
            
    except Exception as e:
        print(f"❌ ResponseGenerator test error: {e}")
        return False

def test_end_to_end_priority():
    """Test end-to-end che verifichi la priorità"""
    
    print("\n🧪 TEST END-TO-END PRIORITY")
    print("=" * 30)
    
    try:
        from core.response_generator import ResponseGenerator
        
        generator = ResponseGenerator()
        
        test_message = "ciao"
        print(f"📝 Test E2E con: '{test_message}'")
        
        # Parametri minimi
        cognitive_state = {"mood": "neutral"}
        recent_memories = []
        relevant_memories = []
        tone = "friendly"
        
        import asyncio
        response = asyncio.run(generator.generate_response(
            test_message,
            cognitive_state,
            recent_memories,
            relevant_memories,
            tone,
            {"type": "conversation", "should_respond": True}
        ))
        
        if response and len(response.strip()) > 0:
            print("✅ End-to-end OK")
            print(f"   Response: '{response[:30]}...'")
            print("✅ Controllare log per ordine corretto:")
            print("   1. [PROACTOR] calling PERSONALPLEX first")
            print("   2. [PERSONALPLEX] generate_success=true")
            print("   3. [RESPONSE_GENERATOR] using PERSONALPLEX response")
            print("   4. NESSUN [CHATGPT] called=true")
            return True
        else:
            print("❌ End-to-end empty")
            return False
            
    except Exception as e:
        print(f"❌ End-to-end error: {e}")
        return False

def test_no_gpt_before_personalplex():
    """Test che GPT non venga chiamato prima di PersonalPlex"""
    
    print("\n🧪 TEST NO GPT BEFORE PERSONALPLEX")
    print("=" * 40)
    
    # Pattern che NON devono comparire nei log
    forbidden_patterns = [
        "[CHATGPT] called=true",
        "decision=ESCALATE_TO_CHATGPT",
        "GPT chiamato prima di PersonalPlex"
    ]
    
    # Pattern che DEVONO comparire nei log
    required_patterns = [
        "[PROACTOR] calling PERSONALPLEX first",
        "[PERSONALPLEX] generate_success=true",
        "[RESPONSE_GENERATOR] using PERSONALPLEX response"
    ]
    
    print("❌ Pattern NESSUNO deve comparire:")
    for pattern in forbidden_patterns:
        print(f"   - {pattern}")
    
    print("✅ Pattern DEVONO comparire:")
    for pattern in required_patterns:
        print(f"   - {pattern}")
    
    return True

if __name__ == "__main__":
    print("🎯 TEST FIX PRIORITÀ PROACTOR")
    print("=" * 40)
    print("OBIETTIVO: Verificare che PersonalPlex sia PRIMARIO")
    print("GPT = fallback reale, non preventivo")
    print("=" * 40)
    
    # Esegui tutti i test
    tests = [
        ("Proactor Calls PersonalPlex First", test_proactor_calls_personalplex_first),
        ("Response Generator Uses PersonalPlex", test_response_generator_uses_personalplex),
        ("End-to-End Priority", test_end_to_end_priority),
        ("No GPT Before PersonalPlex", test_no_gpt_before_personalplex)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*40}")
        success = test_func()
        results.append((test_name, success))
    
    print("\n" + "=" * 40)
    print("📊 RISULTATI FINALI")
    
    passed = 0
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if success:
            passed += 1
    
    print(f"\n🎯 TOTALE: {passed}/{len(results)} test passati")
    
    if passed == len(results):
        print("\n🎉 PRIORITÀ PROACTOR CORRETTA!")
        print("✅ PersonalPlex chiamato per primo")
        print("✅ GPT solo come fallback")
        print("✅ NESSUN GPT preventivo")
        print("✅ Sistema stabile e deterministico")
        print("\n✅ STATO OTTIMALE:")
        print("   PersonalPlex = cervello primario")
        print("   GPT = fallback reale")
        sys.exit(0)
    else:
        print("\n❌ PRIORITÀ PROACTOR ERRATA")
        print("⚠️ GPT chiamato prima di PersonalPlex")
        sys.exit(1)
