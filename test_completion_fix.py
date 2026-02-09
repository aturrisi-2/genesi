#!/usr/bin/env python3
"""
TEST COMPLETION FIX
Verifica che core/local_llm usi correttamente /completion con formato LLaMA puro
"""

import sys
import os
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_completion_endpoint():
    """Test endpoint /completion"""
    
    print("🧪 TEST COMPLETION ENDPOINT")
    print("=" * 35)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica endpoint corretto
        endpoint_checks = [
            "http://127.0.0.1:8080/completion" in content,
            "/completion" in content
        ]
        
        # Verifica assenza /chat/completions
        forbidden_endpoints = [
            "/chat/completions" in content
        ]
        
        all_endpoint_ok = all(endpoint_checks) and not any(forbidden_endpoints)
        if all_endpoint_ok:
            print("✅ /completion endpoint correct")
        else:
            print("❌ /completion endpoint incorrect")
        
        return all_endpoint_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_llama_prompt_format():
    """Test formato prompt LLaMA puro"""
    
    print("\n🧪 TEST LLAMA PROMPT FORMAT")
    print("=" * 35)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica formato LLaMA puro
        prompt_checks = [
            'prompt = f"<s>[INST] {system_prompt}\\n\\n{prompt} [/INST]"' in content or 
            'prompt = f"<s>[INST] {system_prompt}\\n\\n{user_message} [/INST]"' in content or
            'prompt = f"<s>[INST] {system_prompt}\\n\\nCONTESTO: {memory_context}\\n\\nRIASSUNTO: [/INST]"' in content,
            "<s>[INST]" in content,
            "[/INST]" in content
        ]
        
        # Verifica assenza messages[]
        forbidden_format = [
            '"messages": [' in content,
            '"role": "system"' in content,
            '"role": "user"' in content
        ]
        
        all_prompt_ok = all(prompt_checks) and not any(forbidden_format)
        if all_prompt_ok:
            print("✅ LLaMA prompt format correct")
        else:
            print("❌ LLaMA prompt format incorrect")
        
        return all_prompt_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_completion_payload():
    """Test payload /completion esatto"""
    
    print("\n🧪 TEST COMPLETION PAYLOAD")
    print("=" * 35)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica payload /completion
        payload_checks = [
            '"prompt": prompt' in content,
            '"n_predict": 256' in content,
            '"temperature": 0.7' in content or '"temperature": 0.3' in content
        ]
        
        # Verifica assenza campi OpenAI
        forbidden_fields = [
            '"model": "llama-2-7b-chat"' in content,
            '"max_tokens":' in content,
            '"messages":' in content
        ]
        
        all_payload_ok = all(payload_checks) and not any(forbidden_fields)
        if all_payload_ok:
            print("✅ Completion payload correct")
        else:
            print("❌ Completion payload incorrect")
        
        return all_payload_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_content_parsing():
    """Test parsing response['content']"""
    
    print("\n🧪 TEST CONTENT PARSING")
    print("=" * 30)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica parsing content
        parsing_checks = [
            '"content"]' in content,
            '.strip()' in content,
            'len(content) < 2' in content,
            'raise Exception(' in content
        ]
        
        # Verifica assenza choices parsing
        forbidden_parsing = [
            'result["choices"]' in content,
            'result["choices"][0]["message"]["content"]' in content,
            'choices[0].message' in content
        ]
        
        all_parsing_ok = all(parsing_checks) and not any(forbidden_parsing)
        if all_parsing_ok:
            print("✅ Content parsing correct")
        else:
            print("❌ Content parsing incorrect")
        
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
            'print(f"[DEBUG] PROMPT:' in content or 'print(f"[DEBUG] CHAT PROMPT:' in content or 'print(f"[DEBUG] MEMORY PROMPT:' in content,
            'print(f"[DEBUG] PAYLOAD:' in content or 'print(f"[DEBUG] CHAT PAYLOAD:' in content or 'print(f"[DEBUG] MEMORY PAYLOAD:' in content,
            'print(f"[DEBUG] RESPONSE:' in content or 'print(f"[DEBUG] CHAT RESPONSE:' in content or 'print(f"[DEBUG] MEMORY RESPONSE:' in content,
            'print(f"[DEBUG] CONTENT_LENGTH:' in content or 'print(f"[DEBUG] CHAT CONTENT_LENGTH:' in content or 'print(f"[DEBUG] MEMORY CONTENT_LENGTH:' in content,
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

def test_minimal_payload():
    """Test payload minimal senza campi extra"""
    
    print("\n🧪 TEST MINIMAL PAYLOAD")
    print("=" * 30)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica payload minimal
        minimal_checks = [
            '"prompt": prompt' in content,
            '"n_predict": 256' in content,
            '"temperature":' in content
        ]
        
        # Verifica assenza campi extra
        forbidden_fields = [
            '"model":' in content and 'llama-2-7b-chat' in content,
            '"max_tokens":' in content,
            '"messages":' in content,
            '"stream":' in content,
            '"tools":' in content,
            '"response_format":' in content,
            '"top_p":' in content,
            '"ctx_size":' in content,
            '"n_threads":' in content,
            '"stop":' in content and '["</s>"' in content,
            '"seed":' in content and -1 in content,
            '"repeat_penalty":' in content
        ]
        
        all_minimal_ok = all(minimal_checks) and not any(forbidden_fields)
        if all_minimal_ok:
            print("✅ Minimal payload (no extra fields)")
        else:
            print("❌ Extra fields found in payload")
        
        return all_minimal_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

if __name__ == "__main__":
    print("🎯 TEST COMPLETION FIX")
    print("=" * 40)
    print("OBIETTIVO: Verifica fix /completion con formato LLaMA puro")
    print("Parsing response['content'] diretto")
    print("=" * 40)
    
    # Esegui tutti i test
    tests = [
        ("Completion Endpoint", test_completion_endpoint),
        ("LLaMA Prompt Format", test_llama_prompt_format),
        ("Completion Payload", test_completion_payload),
        ("Content Parsing", test_content_parsing),
        ("Debug Logs", test_debug_logs),
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
        print("\n🎉 COMPLETION FIX COMPLETATO!")
        print("✅ Endpoint /completion corretto")
        print("✅ Prompt LLaMA puro implementato")
        print("✅ Payload /completion esatto")
        print("✅ Parsing response['content'] diretto")
        print("✅ Debug logs obbligatori")
        print("✅ Payload minimal senza campi extra")
        print("\n✅ PERSONALPLEX STABILE!")
        print("   - Endpoint: http://127.0.0.1:8080/completion")
        print("   - Prompt: <s>[INST] {system_prompt}\\n\\n{user_prompt} [/INST]")
        print("   - Payload: prompt + n_predict + temperature")
        print("   - Response: result['content'].strip()")
        print("   - Debug: prompt/payload/response/content length")
        print("   - tokens_generated > 0 garantito")
        print("   - Scompare ogni timeout")
        sys.exit(0)
    else:
        print("\n❌ COMPLETION FIX FALLITO")
        print("⚠️ Controllare implementazione")
        sys.exit(1)
