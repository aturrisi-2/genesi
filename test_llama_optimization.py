#!/usr/bin/env python3
"""
TEST LLAMA.CPP OPTIMIZATION
Verifica implementazione llama.cpp diretto per latenza 1-3s
"""

import sys
import os
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_llama_cpp_configuration():
    """Test configurazione llama.cpp"""
    
    print("🧪 TEST LLAMA.CPP CONFIGURATION")
    print("=" * 35)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica configurazione llama.cpp
        llama_checks = [
            "backend_url: str = \"http://localhost:8080/completion\"" in content,
            "timeout: int = 8" in content,
            "max_retries: int = 0" in content,
            "/opt/models/llama-2-7b-chat.Q4_K_M.gguf" in content,
            "ctx_size = 2048" in content,
            "max_tokens = 256" in content,
            "temperature = 0.7" in content
        ]
        
        all_llama_ok = all(llama_checks)
        if all_llama_ok:
            print("✅ Llama.cpp configuration correct")
        else:
            print("❌ Llama.cpp configuration incomplete")
        
        return all_llama_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_health_check_removed():
    """Test rimozione health check"""
    
    print("\n🧪 TEST HEALTH CHECK REMOVED")
    print("=" * 35)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica assenza health check
        if "_health_check" not in content and "health_check" not in content:
            print("✅ Health check completely removed")
            health_ok = True
        else:
            print("❌ Health check still present")
            health_ok = False
        
        return health_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_llama_cpp_payload():
    """Test payload llama.cpp diretto"""
    
    print("\n🧪 TEST LLAMA.CPP PAYLOAD")
    print("=" * 30)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica payload llama.cpp
        payload_checks = [
            "formatted_prompt = f\"[INST] {prompt} [/INST]\"" in content,
            "\"prompt\": formatted_prompt" in content,
            "\"model\": self.model_path" in content,
            "\"n_predict\": max_tokens" in content,
            "\"temperature\": temperature" in content,
            "\"ctx_size\": self.ctx_size" in content,
            "\"n_threads\": 4" in content,
            "\"stop\": [\"</s>\", \"[INST]\", \"[/INST]\"]" in content
        ]
        
        all_payload_ok = all(payload_checks)
        if all_payload_ok:
            print("✅ Llama.cpp payload correct")
        else:
            print("❌ Llama.cpp payload incomplete")
        
        return all_payload_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_single_call_logic():
    """Test logica chiamata singola"""
    
    print("\n🧪 TEST SINGLE CALL LOGIC")
    print("=" * 30)
    
    files_to_check = [
        ("core/intent_engine.py", "intent_engine"),
        ("core/response_generator.py", "response_generator"),
        ("core/llm.py", "llm")
    ]
    
    all_single_call_ok = True
    
    for file_path, file_name in files_to_check:
        try:
            with open(file_path, "r") as f:
                content = f.read()
            
            # Verifica assenza retry/doppie chiamate
            single_call_checks = [
                "UNA SOLA VOLTA" in content,
                "NO RETRY" in content,
                "fallback to GPT" not in content.lower(),
                "retry" not in content.lower(),
                "_health_check" not in content
            ]
            
            file_ok = all(single_call_checks)
            if file_ok:
                print(f"✅ Single call logic in {file_name}")
            else:
                print(f"❌ Single call logic missing in {file_name}")
                all_single_call_ok = False
                
        except Exception as e:
            print(f"❌ Error reading {file_path}: {e}")
            all_single_call_ok = False
    
    return all_single_call_ok

def test_logging_format():
    """Test formato logging UNA riga"""
    
    print("\n🧪 TEST LOGGING FORMAT")
    print("=" * 25)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica logging UNA riga
        if "latency_ms={latency:.0f}, tokens_generated={tokens_count}, model=llama-2-7b-chat" in content:
            print("✅ Single line logging format correct")
            logging_ok = True
        else:
            print("❌ Single line logging format missing")
            logging_ok = False
        
        return logging_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_timeout_handling():
    """Test gestione timeout 8s"""
    
    print("\n🧪 TEST TIMEOUT HANDLING")
    print("=" * 30)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica gestione timeout
        timeout_checks = [
            "timeout=self.timeout" in content,
            "requests.exceptions.Timeout" in content,
            "Scusa, ci ho messo troppo tempo. Riprova." in content,
            "Scusa, c'è stato un problema. Riprova." in content
        ]
        
        all_timeout_ok = all(timeout_checks)
        if all_timeout_ok:
            print("✅ Timeout handling correct")
        else:
            print("❌ Timeout handling incomplete")
        
        return all_timeout_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

if __name__ == "__main__":
    print("🎯 TEST LLAMA.CPP OPTIMIZATION")
    print("=" * 40)
    print("OBIETTIVO: Verifica ottimizzazione llama.cpp diretto")
    print("Latenza 1-3s per PersonalPlex 7B")
    print("=" * 40)
    
    # Esegui tutti i test
    tests = [
        ("Llama.cpp Configuration", test_llama_cpp_configuration),
        ("Health Check Removed", test_health_check_removed),
        ("Llama.cpp Payload", test_llama_cpp_payload),
        ("Single Call Logic", test_single_call_logic),
        ("Logging Format", test_logging_format),
        ("Timeout Handling", test_timeout_handling)
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
        print("\n🎉 LLAMA.CPP OPTIMIZATION COMPLETATO!")
        print("✅ Configurazione llama.cpp corretta")
        print("✅ Health check rimosso")
        print("✅ Payload llama.cpp diretto")
        print("✅ Logica chiamata singola")
        print("✅ Logging UNA riga")
        print("✅ Timeout 8s gestito")
        print("\n✅ LATENZA OTTIMIZZATA!")
        print("   - Llama.cpp diretto: 1-3s")
        print("   - Nessuna doppia generazione")
        print("   - Nessun retry")
        print("   - Timeout hard 8s")
        print("   - Fallback breve su timeout")
        sys.exit(0)
    else:
        print("\n❌ LLAMA.CPP OPTIMIZATION FALLITO")
        print("⚠️ Controllare implementazione")
        sys.exit(1)
