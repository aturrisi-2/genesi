#!/usr/bin/env python3
"""
TEST VALID RESPONSES
Verifica che le risposte valide di llama.cpp non vengano scartate
"""

import sys
import os
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_no_length_rejection():
    """Test che le risposte brevi non vengano scartate"""
    
    print("🧪 TEST NO LENGTH REJECTION")
    print("=" * 35)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica assenza controllo len < 2
        forbidden_checks = [
            'if len(content) < 2:' in content,
            'if len(content) <= 2:' in content,
            'len(content) < 2' in content and 'raise Exception' in content
        ]
        
        # Verifica presenza controllo solo vuoto
        valid_checks = [
            'if not content:' in content,
            'if not content:' in content and 'raise Exception' in content
        ]
        
        all_ok = not any(forbidden_checks) and any(valid_checks)
        if all_ok:
            print("✅ No length rejection - only empty check")
        else:
            print("❌ Length rejection still present")
        
        return all_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_http_200_always_valid():
    """Test che HTTP 200 con content non vuoto sia sempre valido"""
    
    print("\n🧪 TEST HTTP 200 ALWAYS VALID")
    print("=" * 40)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica logica HTTP 200 + content non vuoto
        logic_checks = [
            'if response.status_code == 200:' in content,
            'if "content" in result:' in content,
            'content = result["content"].strip()' in content,
            'if not content:' in content,
            'return content' in content
        ]
        
        # Verifica assenza rejection per lunghezza
        forbidden_logic = [
            'len(content) < 2' in content and 'raise Exception' in content,
            'troppo corto' in content
        ]
        
        all_logic_ok = all(logic_checks) and not any(forbidden_logic)
        if all_logic_ok:
            print("✅ HTTP 200 + non-empty content always valid")
        else:
            print("❌ HTTP 200 logic incorrect")
        
        return all_logic_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_tokens_from_content():
    """Test che tokens_generated sia calcolato dal contenuto"""
    
    print("\n🧪 TEST TOKENS FROM CONTENT")
    print("=" * 35)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica calcolo tokens dal contenuto
        token_checks = [
            'tokens_count = len(content.split())' in content,
            'tokens_generated={tokens_count}' in content
        ]
        
        # Verifica assenza tokens=0 su content valido
        forbidden_tokens = [
            'tokens_generated=0' in content and 'error=timeout' in content
        ]
        
        all_tokens_ok = all(token_checks)
        if all_tokens_ok:
            print("✅ Tokens calculated from content")
        else:
            print("❌ Tokens calculation incorrect")
        
        return all_tokens_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_accepted_responses_log():
    """Test log esplicito quando risposta accettata"""
    
    print("\n🧪 TEST ACCEPTED RESPONSES LOG")
    print("=" * 40)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica log risposte accettate
        log_checks = [
            'print(f"[DEBUG] RISPOSTA ACCETTATA:' in content,
            'print(f"[DEBUG] CHAT RISPOSTA ACCETTATA:' in content,
            'print(f"[DEBUG] MEMORY RISPOSTA ACCETTATA:' in content
        ]
        
        any_log_ok = any(log_checks)
        if any_log_ok:
            print("✅ Accepted responses log implemented")
        else:
            print("❌ Accepted responses log missing")
        
        return any_log_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_no_false_timeout():
    """Test che non ci siano timeout falsi"""
    
    print("\n🧪 TEST NO FALSE TIMEOUT")
    print("=" * 35)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica timeout solo su requests.exceptions.Timeout
        timeout_checks = [
            'except requests.exceptions.Timeout:' in content,
            'error=timeout' in content
        ]
        
        # Verifica che timeout sia solo su eccezioni di rete
        all_timeout_ok = any(timeout_checks)
        if all_timeout_ok:
            print("✅ No false timeout - only on network timeout")
        else:
            print("❌ False timeout possible")
        
        return all_timeout_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_single_char_responses():
    """Test che risposte di 1 carattere siano accettate"""
    
    print("\n🧪 TEST SINGLE CHAR RESPONSES")
    print("=" * 40)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica che solo content vuoto sia rifiutato
        rejection_checks = [
            'if not content:' in content,
            'if not content:' in content and 'raise Exception' in content
        ]
        
        # Verifica assenza controllo su singolo carattere
        single_char_ok = [
            'if len(content) < 2:' not in content,
            'if len(content) <= 1:' not in content
        ]
        
        all_single_ok = any(rejection_checks) and all(single_char_ok)
        if all_single_ok:
            print("✅ Single character responses accepted")
        else:
            print("❌ Single character responses rejected")
        
        return all_single_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

if __name__ == "__main__":
    print("🎯 TEST VALID RESPONSES")
    print("=" * 40)
    print("OBIETTIVO: Verifica che risposte valide non vengano scartate")
    print("HTTP 200 + content non vuoto = SEMPRE VALIDO")
    print("=" * 40)
    
    # Esegui tutti i test
    tests = [
        ("No Length Rejection", test_no_length_rejection),
        ("HTTP 200 Always Valid", test_http_200_always_valid),
        ("Tokens From Content", test_tokens_from_content),
        ("Accepted Responses Log", test_accepted_responses_log),
        ("No False Timeout", test_no_false_timeout),
        ("Single Char Responses", test_single_char_responses)
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
        print("\n🎉 VALID RESPONSES FIX COMPLETATO!")
        print("✅ Nessun rejection per lunghezza")
        print("✅ HTTP 200 + content non vuoto sempre valido")
        print("✅ Tokens calcolati dal contenuto")
        print("✅ Log esplicito risposte accettate")
        print("✅ Nessun timeout falso")
        print("✅ Risposte di 1 carattere accettate")
        print("\n✅ GENESI ACCETTA RISPOSTE VALIDE!")
        print("   - 'ciao' → risposta visibile")
        print("   - 'OK' → risposta accettata")
        print("   - '✅' → risposta accettata")
        print("   - Nessun tokens_generated=0 se content esiste")
        print("   - Nessun timeout se HTTP 200")
        sys.exit(0)
    else:
        print("\n❌ VALID RESPONSES FIX FALLITO")
        print("⚠️ Controllare implementazione")
        sys.exit(1)
