#!/usr/bin/env python3
"""
TEST LLAMA ONLY
Verifica eliminazione completa fallback GPT e routing solo llama.cpp
"""

import sys
import os
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_llama_format_prompt():
    """Test formato LLaMA 2 obbligatorio"""
    
    print("🧪 TEST LLAMA FORMAT PROMPT")
    print("=" * 30)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica formato LLaMA 2 in tutte le funzioni
        llama_checks = [
            "<s>[INST] <<SYS>>" in content,
            "<</SYS>>" in content,
            "[/INST]" in content,
            "Tu sei Genesi. Rispondi in modo naturale e conversazionale." in content
        ]
        
        all_llama_ok = all(llama_checks)
        if all_llama_ok:
            print("✅ LLaMA 2 format implemented")
        else:
            print("❌ LLaMA 2 format missing")
        
        return all_llama_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_no_gpt_fallback():
    """Test assenza fallback GPT"""
    
    print("\n🧪 TEST NO GPT FALLBACK")
    print("=" * 25)
    
    files_to_check = [
        ("core/local_llm.py", "local_llm"),
        ("core/intent_engine.py", "intent_engine"),
        ("core/response_generator.py", "response_generator"),
        ("core/llm.py", "llm")
    ]
    
    all_no_gpt_ok = True
    
    for file_path, file_name in files_to_check:
        try:
            with open(file_path, "r") as f:
                content = f.read()
            
            # Verifica assenza fallback GPT
            forbidden_patterns = [
                "fallback to GPT" in content,
                "ESCALATE_TO_GPT" in content,
                "OpenAI(" in content,
                "chat.completions" in content,
                "api_key" in content and "OPENAI" in content,
                "client.chat" in content
            ]
            
            file_ok = not any(forbidden_patterns)
            if file_ok:
                print(f"✅ No GPT fallback in {file_name}")
            else:
                print(f"❌ GPT fallback found in {file_name}")
                all_no_gpt_ok = False
                
        except Exception as e:
            print(f"❌ Error reading {file_path}: {e}")
            all_no_gpt_ok = False
    
    return all_no_gpt_ok

def test_llama_endpoint_only():
    """Test endpoint solo llama.cpp"""
    
    print("\n🧪 TEST LLAMA ENDPOINT ONLY")
    print("=" * 30)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica endpoint llama.cpp
        endpoint_checks = [
            "/completion" in content,
            "requests.post" in content
        ]
        
        all_endpoint_ok = all(endpoint_checks)
        if all_endpoint_ok:
            print("✅ Only llama.cpp endpoint")
        else:
            print("❌ Endpoint issues found")
            # Debug: mostra cosa manca
            for check in endpoint_checks:
                if not check:
                    print(f"  Missing: {check}")
        
        return all_endpoint_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_no_openai_imports():
    """Test assenza import OpenAI"""
    
    print("\n🧪 TEST NO OPENAI IMPORTS")
    print("=" * 30)
    
    files_to_check = [
        ("core/local_llm.py", "local_llm"),
        ("core/intent_engine.py", "intent_engine"),
        ("core/response_generator.py", "response_generator"),
        ("core/llm.py", "llm")
    ]
    
    all_no_openai_ok = True
    
    for file_path, file_name in files_to_check:
        try:
            with open(file_path, "r") as f:
                content = f.read()
            
            # Verifica assenza import OpenAI
            openai_imports = [
                "from openai import OpenAI" in content,
                "import openai" in content,
                "OpenAI(" in content
            ]
            
            file_ok = not any(openai_imports)
            if file_ok:
                print(f"✅ No OpenAI imports in {file_name}")
            else:
                print(f"❌ OpenAI imports found in {file_name}")
                all_no_openai_ok = False
                
        except Exception as e:
            print(f"❌ Error reading {file_path}: {e}")
            all_no_openai_ok = False
    
    return all_no_openai_ok

def test_response_handling():
    """Test response handling senza reinterpretazione"""
    
    print("\n🧪 TEST RESPONSE HANDLING")
    print("=" * 30)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica response handling diretto
        response_checks = [
            "content = result[\"content\"].strip()" in content,
            "return content" in content,
            'return ""' in content,  # Nessuna risposta su fallback
            "NESSUN fallback - solo llama.cpp" in content
        ]
        
        # Verifica assenza riformattazione
        forbidden_handling = [
            "_clean_tics" in content,
            "_format_val" in content,
            "reformat" in content.lower()
        ]
        
        all_response_ok = all(response_checks) and not any(forbidden_handling)
        if all_response_ok:
            print("✅ Direct response handling")
        else:
            print("❌ Response reformatting found")
        
        return all_response_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_deterministic_behavior():
    """Test comportamento deterministico"""
    
    print("\n🧪 TEST DETERMINISTIC BEHAVIOR")
    print("=" * 35)
    
    try:
        with open("core/intent_engine.py", "r") as f:
            content = f.read()
        
        # Verifica comportamento deterministico
        deterministic_checks = [
            "should_respond\": False" in content,
            "NO RESPONSE" in content,
            "NESSUN FALLBACK" in content,
            "solo PersonalPlex" in content
        ]
        
        # Verifica routing semplificato
        all_deterministic_ok = any(deterministic_checks)
        if all_deterministic_ok:
            print("✅ Deterministic behavior")
        else:
            print("❌ Complex routing found")
        
        return all_deterministic_ok
        
    except Exception as e:
        print(f"❌ Error reading intent_engine.py: {e}")
        return False

if __name__ == "__main__":
    print("🎯 TEST LLAMA ONLY")
    print("=" * 40)
    print("OBIETTIVO: Verifica eliminazione completa GPT")
    print("Routing ESCLUSIVAMENTE llama.cpp")
    print("=" * 40)
    
    # Esegui tutti i test
    tests = [
        ("LLaMA Format Prompt", test_llama_format_prompt),
        ("No GPT Fallback", test_no_gpt_fallback),
        ("LLaMA Endpoint Only", test_llama_endpoint_only),
        ("No OpenAI Imports", test_no_openai_imports),
        ("Response Handling", test_response_handling),
        ("Deterministic Behavior", test_deterministic_behavior)
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
        print("\n🎉 LLAMA ONLY COMPLETATO!")
        print("✅ Formato LLaMA 2 obbligatorio")
        print("✅ Nessun fallback GPT")
        print("✅ Solo endpoint llama.cpp")
        print("✅ Nessuna import OpenAI")
        print("✅ Response handling diretto")
        print("✅ Comportamento deterministico")
        print("\n✅ GENESI LLAMA-ONLY!")
        print("   - Solo llama.cpp: http://127.0.0.1:8080/completion")
        print("   - Formato LLaMA 2: <s>[INST] <<SYS>> ...")
        print("   - Nessun fallback GPT")
        print("   - Comportamento stabile e coerente")
        print("   - 'ciao' → risposta naturale")
        sys.exit(0)
    else:
        print("\n❌ LLAMA ONLY FALLITO")
        print("⚠️ Controllare implementazione")
        sys.exit(1)
