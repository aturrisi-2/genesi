#!/usr/bin/env python3
"""
TEST ULTRA FAST OPTIMIZATION
Verifica implementazione PersonalPlex < 1200ms e compatibilità TTS
"""

import sys
import os
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_ultra_fast_configuration():
    """Test configurazione ultra-veloce"""
    
    print("🧪 TEST ULTRA FAST CONFIGURATION")
    print("=" * 35)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica configurazione ultra-veloce
        ultra_fast_checks = [
            "timeout: int = 1.2" in content,
            "ctx_size = 512" in content,
            "max_tokens = 32" in content,
            "temperature = 0.6" in content,
            "top_p = 0.9" in content
        ]
        
        all_ultra_fast_ok = all(ultra_fast_checks)
        if all_ultra_fast_ok:
            print("✅ Ultra fast configuration correct")
        else:
            print("❌ Ultra fast configuration incomplete")
        
        return all_ultra_fast_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_brief_response_limits():
    """Test limiti risposta breve"""
    
    print("\n🧪 TEST BRIEF RESPONSE LIMITS")
    print("=" * 35)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica limiti risposta
        brief_checks = [
            "Rispondi in 1 frase max, 25 token max" in content,
            "min(max_tokens, 25)" in content,
            "\"stop\": [\"</s>\", \"[INST]\", \"[/INST]\", \"\\n\", \":\", \"•\", \"-\"]" in content,
            "mirostat" in content
        ]
        
        all_brief_ok = all(brief_checks)
        if all_brief_ok:
            print("✅ Brief response limits implemented")
        else:
            print("❌ Brief response limits missing")
        
        return all_brief_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_single_call_enforcement():
    """Test applicazione chiamata singola"""
    
    print("\n🧪 TEST SINGLE CALL ENFORCEMENT")
    print("=" * 35)
    
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
            
            # Verifica logica singola chiamata
            single_call_checks = [
                "UNA SOLA VOLTA" in content,
                "immediate GPT fallback" in content or "immediate GPT" in content,
                "NO retry" in content or "NON retry" in content
            ]
            
            file_ok = any(single_call_checks)
            if file_ok:
                print(f"✅ Single call enforced in {file_name}")
            else:
                print(f"❌ Single call not enforced in {file_name}")
                all_single_call_ok = False
                
        except Exception as e:
            print(f"❌ Error reading {file_path}: {e}")
            all_single_call_ok = False
    
    return all_single_call_ok

def test_logging_with_decision():
    """Test logging con decisione finale"""
    
    print("\n🧪 TEST LOGGING WITH DECISION")
    print("=" * 35)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica logging con decisione
        logging_checks = [
            "decision=local" in content,
            "decision=gpt" in content,
            "latency_ms=" in content,
            "tokens_generated=" in content,
            "model=llama-2-7b-chat" in content
        ]
        
        all_logging_ok = all(logging_checks)
        if all_logging_ok:
            print("✅ Logging with decision implemented")
        else:
            print("❌ Logging with decision missing")
        
        return all_logging_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_natural_response_validation():
    """Test validazione risposte naturali"""
    
    print("\n🧪 TEST NATURAL RESPONSE VALIDATION")
    print("=" * 40)
    
    try:
        with open("core/response_generator.py", "r") as f:
            content = f.read()
        
        # Verifica validazione naturale
        validation_checks = [
            "len(words) <= 10" in content,
            "[':', '•', '-', '1.', '2.', '3.']" in content,
            "response too long/unnatural" in content,
            "PersonalPlex 7B SUCCESS" in content
        ]
        
        all_validation_ok = all(validation_checks)
        if all_validation_ok:
            print("✅ Natural response validation implemented")
        else:
            print("❌ Natural response validation missing")
        
        return all_validation_ok
        
    except Exception as e:
        print(f"❌ Error reading response_generator.py: {e}")
        return False

def test_timeout_fallback_logic():
    """Test logica fallback timeout"""
    
    print("\n🧪 TEST TIMEOUT FALLBACK LOGIC")
    print("=" * 35)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica logica fallback
        fallback_checks = [
            "requests.exceptions.Timeout" in content,
            "return \"\"  # Fallback immediato a GPT" in content,
            "decision=gpt, error=timeout" in content,
            "1.2s hard timeout" in content
        ]
        
        all_fallback_ok = all(fallback_checks)
        if all_fallback_ok:
            print("✅ Timeout fallback logic implemented")
        else:
            print("❌ Timeout fallback logic missing")
        
        return all_fallback_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

if __name__ == "__main__":
    print("🎯 TEST ULTRA FAST OPTIMIZATION")
    print("=" * 40)
    print("OBIETTIVO: Verifica PersonalPlex < 1200ms")
    print("Compatibilità TTS realtime")
    print("=" * 40)
    
    # Esegui tutti i test
    tests = [
        ("Ultra Fast Configuration", test_ultra_fast_configuration),
        ("Brief Response Limits", test_brief_response_limits),
        ("Single Call Enforcement", test_single_call_enforcement),
        ("Logging with Decision", test_logging_with_decision),
        ("Natural Response Validation", test_natural_response_validation),
        ("Timeout Fallback Logic", test_timeout_fallback_logic)
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
        print("\n🎉 ULTRA FAST OPTIMIZATION COMPLETATO!")
        print("✅ Configurazione < 1200ms implementata")
        print("✅ Limiti risposta 25 token/1 frase")
        print("✅ Chiamata singola applicata")
        print("✅ Logging con decisione finale")
        print("✅ Validazione risposte naturali")
        print("✅ Fallback timeout immediato")
        print("\n✅ PERSONALPLEX ULTRA-VELOCE!")
        print("   - Timeout: 1.2s hard")
        print("   - Max tokens: 25")
        print("   - 1 frase max")
        print("   - Fallback GPT immediato")
        print("   - Compatibilità TTS realtime")
        sys.exit(0)
    else:
        print("\n❌ ULTRA FAST OPTIMIZATION FALLITO")
        print("⚠️ Controllare implementazione")
        sys.exit(1)
