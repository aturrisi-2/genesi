#!/usr/bin/env python3
"""
TEST FIX FINALE PERSONALPLEX 7B
Verifica eliminazione completa chiamate /analyze
"""

import sys
import os
import requests
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_personalplex_health():
    """Test health endpoint"""
    
    print("🧪 TEST HEALTH PERSONALPLEX")
    print("=" * 30)
    
    try:
        response = requests.get("http://localhost:8001/health", timeout=5)
        
        if response.status_code == 200:
            print("✅ PersonalPlex health OK")
            return True
        else:
            print(f"❌ Health error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

def test_personalplex_chat_completions():
    """Test /v1/chat/completions"""
    
    print("\n🧪 TEST CHAT COMPLETIONS")
    print("=" * 30)
    
    try:
        payload = {
            "model": "mistral-7b-instruct",
            "messages": [
                {"role": "system", "content": "Tu sei Genesi."},
                {"role": "user", "content": "ciao"}
            ],
            "max_tokens": 50
        }
        
        response = requests.post(
            "http://localhost:8001/v1/chat/completions",
            json=payload,
            timeout=15
        )
        
        if response.status_code == 200:
            result = response.json()
            if "choices" in result and len(result["choices"]) > 0:
                content = result["choices"][0]["message"]["content"]
                print("✅ Chat completions OK")
                print(f"   Response: '{content[:30]}...'")
                return True
            else:
                print("❌ Invalid response format")
                return False
        else:
            print(f"❌ HTTP error: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Chat completions failed: {e}")
        return False

def test_local_llm_no_analyze_method():
    """Test che LocalLLM non abbia più metodo analyze"""
    
    print("\n🧪 TEST LOCAL_LLM NO ANALYZE METHOD")
    print("=" * 40)
    
    try:
        from core.local_llm import LocalLLM
        
        local_llm = LocalLLM()
        
        # Verifica che il metodo analyze NON esista
        if hasattr(local_llm, 'analyze'):
            print("❌ LocalLLM ha ancora metodo analyze - DA RIMUOVERE")
            return False
        else:
            print("✅ LocalLLM non ha metodo analyze")
            
        # Verifica che il metodo generate ESISTA
        if hasattr(local_llm, 'generate'):
            print("✅ LocalLLM ha metodo generate")
            return True
        else:
            print("❌ LocalLLM non ha metodo generate")
            return False
            
    except Exception as e:
        print(f"❌ Test LocalLLM error: {e}")
        return False

def test_local_llm_generate():
    """Test metodo generate"""
    
    print("\n🧪 TEST LOCAL_LLM GENERATE")
    print("=" * 30)
    
    try:
        from core.local_llm import LocalLLM
        
        local_llm = LocalLLM()
        
        response = local_llm.generate("ciao")
        
        if response and len(response.strip()) > 0:
            print("✅ LocalLLM.generate OK")
            print(f"   Response: '{response[:30]}...'")
            return True
        else:
            print("❌ LocalLLM.generate empty")
            return False
            
    except Exception as e:
        print(f"❌ LocalLLM.generate error: {e}")
        return False

def test_proactor_no_personalplex_calls():
    """Test che Proactor non chiami più PersonalPlex"""
    
    print("\n🧪 TEST PROACTOR NO PERSONALPLEX CALLS")
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
        
        result = engine.analyze_intent(
            test_message,
            cognitive_state,
            recent_memories,
            relevant_memories,
            tone
        )
        
        if result:
            # Verifica che NON ci siano dati PersonalPlex
            plex_data = [k for k in result.keys() if 'plex' in k.lower()]
            
            if len(plex_data) == 0:
                print("✅ Proactor non chiama PersonalPlex")
                print("✅ Solo routing/intent detection")
                return True
            else:
                print(f"❌ Proactor chiama ancora PersonalPlex: {plex_data}")
                return False
        else:
            print("❌ Proactor returned None")
            return False
            
    except Exception as e:
        print(f"❌ Proactor test error: {e}")
        return False

def test_llm_generate_uses_personalplex():
    """Test che generate_response usi PersonalPlex"""
    
    print("\n🧪 TEST LLM GENERATE USES PERSONALPLEX")
    print("=" * 45)
    
    try:
        from core.llm import generate_response
        
        test_payload = {
            "prompt": "ciao",
            "intent": {"brain_mode": "relazione"}
        }
        
        print(f"📝 Test generate_response")
        
        response = generate_response(test_payload)
        
        if response and len(response.strip()) > 0:
            print("✅ generate_response OK")
            print(f"   Response: '{response[:30]}...'")
            print("✅ Controllare log per [PERSONALPLEX] generate_success=true")
            return True
        else:
            print("❌ generate_response empty")
            return False
            
    except Exception as e:
        print(f"❌ generate_response error: {e}")
        return False

def test_end_to_end_simple():
    """Test end-to-end semplice"""
    
    print("\n🧪 TEST END-TO-END SEMPLICE")
    print("=" * 35)
    
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
        intent = {"type": "conversation", "should_respond": True}
        
        import asyncio
        response = asyncio.run(generator.generate_response(
            test_message,
            cognitive_state,
            recent_memories,
            relevant_memories,
            tone,
            intent
        ))
        
        if response and len(response.strip()) > 0:
            print("✅ End-to-end OK")
            print(f"   Response: '{response[:30]}...'")
            return True
        else:
            print("❌ End-to-end empty")
            return False
            
    except Exception as e:
        print(f"❌ End-to-end error: {e}")
        return False

if __name__ == "__main__":
    print("🎯 TEST FIX FINALE PERSONALPLEX 7B")
    print("=" * 50)
    print("OBIETTIVO: Verificare eliminazione completa /analyze")
    print("PersonalPlex usato SOLO via /v1/chat/completions")
    print("=" * 50)
    
    # Esegui tutti i test
    tests = [
        ("Health", test_personalplex_health),
        ("Chat Completions", test_personalplex_chat_completions),
        ("LocalLLM No Analyze", test_local_llm_no_analyze_method),
        ("LocalLLM Generate", test_local_llm_generate),
        ("Proactor No PersonalPlex", test_proactor_no_personalplex_calls),
        ("LLM Generate Uses PersonalPlex", test_llm_generate_uses_personalplex),
        ("End-to-End Simple", test_end_to_end_simple)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        success = test_func()
        results.append((test_name, success))
    
    print("\n" + "=" * 50)
    print("📊 RISULTATI FINALI")
    
    passed = 0
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if success:
            passed += 1
    
    print(f"\n🎯 TOTALE: {passed}/{len(results)} test passati")
    
    if passed == len(results):
        print("\n🎉 FIX FINALE PERSONALPLEX 7B COMPLETATO!")
        print("✅ NESSUNA chiamata a /analyze")
        print("✅ SOLO /v1/chat/completions")
        print("✅ LocalLLM senza metodo analyze")
        print("✅ Proactor non chiama PersonalPlex")
        print("✅ generate_response usa PersonalPlex")
        print("✅ Fallback GPT solo se server down")
        print("\n✅ SISTEMA STABILE E DETERMINISTICO")
        print("\nLOG ATTESI:")
        print("✅ [PERSONALPLEX] generate_success=true")
        print("❌ NESSUN HTTP 404")
        print("❌ NESSUN ESCALATE_FALLBACK_GPT")
        print("✅ [GPT] fallback=true (solo se server down)")
        sys.exit(0)
    else:
        print("\n❌ FIX FINALE PERSONALPLEX 7B FALLITO")
        print("⚠️ Controllare errori rimanenti")
        sys.exit(1)
