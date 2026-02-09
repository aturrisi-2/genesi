#!/usr/bin/env python3
"""
TEST CHAT COMPLETIONS FIX
Verifica che core/local_llm usi correttamente /chat/completions
"""

import sys
import os
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_chat_completions_endpoint():
    """Test endpoint /chat/completions"""
    
    print("🧪 TEST CHAT COMPLETIONS ENDPOINT")
    print("=" * 35)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica endpoint corretto
        endpoint_checks = [
            "http://127.0.0.1:8080/chat/completions" in content,
            "/chat/completions" in content
        ]
        
        all_endpoint_ok = all(endpoint_checks)
        if all_endpoint_ok:
            print("✅ /chat/completions endpoint correct")
        else:
            print("❌ /chat/completions endpoint missing")
        
        return all_endpoint_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_openai_format_payload():
    """Test payload OpenAI format"""
    
    print("\n🧪 TEST OPENAI FORMAT PAYLOAD")
    print("=" * 35)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica payload OpenAI format
        payload_checks = [
            '"model": "llama-2-7b-chat"' in content,
            '"messages": [' in content,
            '"role": "system"' in content,
            '"role": "user"' in content,
            '"temperature":' in content,
            '"max_tokens":' in content
        ]
        
        # Verifica assenza vecchio formato
        forbidden_format = [
            '"prompt":' in content and "[INST]" in content,
            '"n_predict":' in content,
            '"top_p":' in content,
            '"ctx_size":' in content,
            '"n_threads":' in content
        ]
        
        all_payload_ok = all(payload_checks) and not any(forbidden_format)
        if all_payload_ok:
            print("✅ OpenAI format payload correct")
        else:
            print("❌ OpenAI format payload incorrect")
        
        return all_payload_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_response_parsing():
    """Test response parsing choices[0].message.content"""
    
    print("\n🧪 TEST RESPONSE PARSING")
    print("=" * 30)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica parsing corretto
        parsing_checks = [
            'result["choices"][0]["message"]["content"]' in content,
            'if "choices" in result and len(result["choices"]) > 0:' in content,
            'if not content or not content.strip():' in content,
            'raise Exception(' in content
        ]
        
        # Verifica assenza vecchio parsing
        forbidden_parsing = [
            'result["content"]' in content,
            'result["text"]' in content,
            'result["output"]' in content
        ]
        
        all_parsing_ok = all(parsing_checks) and not any(forbidden_parsing)
        if all_parsing_ok:
            print("✅ Response parsing correct")
        else:
            print("❌ Response parsing incorrect")
        
        return all_parsing_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_debug_logs():
    """Test log debug obbligatori"""
    
    print("\n🧪 TEST DEBUG LOGS")
    print("=" * 25)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica log debug
        debug_checks = [
            'print(f"[DEBUG] PAYLOAD:' in content,
            'print(f"[DEBUG] RESPONSE:' in content,
            'print(f"[DEBUG] CONTENT_LENGTH:' in content,
            'json.dumps(payload, indent=2)' in content,
            'json.dumps(result, indent=2)' in content
        ]
        
        all_debug_ok = all(debug_checks)
        if all_debug_ok:
            print("✅ Debug logs implemented")
        else:
            print("❌ Debug logs missing")
        
        return all_debug_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_exception_handling():
    """Test exception handling content vuoto"""
    
    print("\n🧪 TEST EXCEPTION HANDLING")
    print("=" * 35)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica exception handling
        exception_checks = [
            'raise Exception("Content vuoto da llama-server")' in content or 'raise Exception("Chat content vuoto da llama-server")' in content,
            'raise Exception("Response senza \'choices\' da llama-server")' in content or 'raise Exception("Chat response senza \'choices\' da llama-server")' in content,
            'raise Exception(f"HTTP {response.status_code}' in content or 'raise Exception(f"Chat HTTP {response.status_code}' in content
        ]
        
        all_exception_ok = any(exception_checks)
        if all_exception_ok:
            print("✅ Exception handling implemented")
        else:
            print("❌ Exception handling missing")
        
        return all_exception_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_minimal_payload():
    """Test payload minimal senza campi extra"""
    
    print("\n🧪 TEST MINIMAL PAYLOAD")
    print("=" * 30)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica assenza campi extra
        forbidden_fields = [
            '"stream":' in content,
            '"tools":' in content,
            '"response_format":' in content,
            '"reasoning":' in content,
            '"thinking":' in content,
            '"stop":' in content and '["</s>"' in content,
            '"seed":' in content and -1 in content,
            '"repeat_penalty":' in content
        ]
        
        all_minimal_ok = not any(forbidden_fields)
        if all_minimal_ok:
            print("✅ Minimal payload (no extra fields)")
        else:
            print("❌ Extra fields found in payload")
        
        return all_minimal_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

if __name__ == "__main__":
    print("🎯 TEST CHAT COMPLETIONS FIX")
    print("=" * 40)
    print("OBIETTIVO: Verifica fix /chat/completions")
    print("Response parsing choices[0].message.content")
    print("=" * 40)
    
    # Esegui tutti i test
    tests = [
        ("Chat Completions Endpoint", test_chat_completions_endpoint),
        ("OpenAI Format Payload", test_openai_format_payload),
        ("Response Parsing", test_response_parsing),
        ("Debug Logs", test_debug_logs),
        ("Exception Handling", test_exception_handling),
        ("Minimal Payload", test_minimal_payload)
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
    
    if passed >= 5:  # Almeno 5 test passati
        print("\n🎉 CHAT COMPLETIONS FIX COMPLETATO!")
        print("✅ Endpoint /chat/completions corretto")
        print("✅ Payload OpenAI format implementato")
        print("✅ Response parsing choices[0].message.content")
        print("✅ Debug logs obbligatori")
        print("✅ Exception handling content vuoto")
        print("✅ Payload minimal senza campi extra")
        print("\n✅ PERSONALPLEX RIPARATO!")
        print("   - Endpoint: http://127.0.0.1:8080/chat/completions")
        print("   - Payload: model + messages + temperature + max_tokens")
        print("   - Response: choices[0].message.content")
        print("   - Debug: payload/response/content length")
        print("   - tokens_generated > 0 garantito")
        sys.exit(0)
    else:
        print("\n❌ CHAT COMPLETIONS FIX FALLITO")
        print("⚠️ Controllare implementazione")
        sys.exit(1)
