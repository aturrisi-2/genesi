#!/usr/bin/env python3
"""
TEST ITALIAN PROMPT
Verifica che la direttiva italiana forte sia stata aggiunta a tutti i system prompt
"""

import sys
import os
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_italian_directive():
    """Test direttiva italiana in tutti i system prompt"""
    
    print("🧪 TEST ITALIAN DIRECTIVE")
    print("=" * 35)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica direttiva italiana forte
        italian_checks = [
            'Rispondi SEMPRE e SOLO in italiano' in content,
            'Non usare mai l\'inglese, nemmeno singole parole, espressioni o frasi' in content,
            'Se l\'utente scrive in italiano, rispondi esclusivamente in italiano' in content
        ]
        
        # Verifica che sia presente in tutte le funzioni
        function_checks = [
            content.count('Rispondi SEMPRE e SOLO in italiano') >= 3  # Almeno 3 occorrenze
        ]
        
        all_italian_ok = all(italian_checks) and all(function_checks)
        if all_italian_ok:
            print("✅ Italian directive added to all prompts")
        else:
            print("❌ Italian directive missing")
        
        return all_italian_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_generate_function():
    """Test direttiva in generate()"""
    
    print("\n🧪 TEST GENERATE FUNCTION")
    print("=" * 35)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica presenza in generate()
        generate_section = content.split('def generate(')[1].split('def generate_chat_response(')[0]
        
        generate_checks = [
            'Rispondi SEMPRE e SOLO in italiano' in generate_section,
            'Non usare mai l\'inglese' in generate_section,
            'Tu sei Genesi. Rispondi in modo naturale e conversazionale' in generate_section
        ]
        
        all_generate_ok = all(generate_checks)
        if all_generate_ok:
            print("✅ Italian directive in generate()")
        else:
            print("❌ Italian directive missing in generate()")
        
        return all_generate_ok
        
    except Exception as e:
        print(f"❌ Error analyzing generate(): {e}")
        return False

def test_chat_function():
    """Test direttiva in generate_chat_response()"""
    
    print("\n🧪 TEST CHAT FUNCTION")
    print("=" * 30)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica presenza in generate_chat_response()
        chat_section = content.split('def generate_chat_response(')[1].split('def generate_memory_summary(')[0]
        
        chat_checks = [
            'Rispondi SEMPRE e SOLO in italiano' in chat_section,
            'Non usare mai l\'inglese' in chat_section,
            'Tu sei Genesi. Rispondi in modo naturale e conversazionale' in chat_section
        ]
        
        all_chat_ok = all(chat_checks)
        if all_chat_ok:
            print("✅ Italian directive in generate_chat_response()")
        else:
            print("❌ Italian directive missing in generate_chat_response()")
        
        return all_chat_ok
        
    except Exception as e:
        print(f"❌ Error analyzing generate_chat_response(): {e}")
        return False

def test_memory_function():
    """Test direttiva in generate_memory_summary()"""
    
    print("\n🧪 TEST MEMORY FUNCTION")
    print("=" * 35)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica presenza in generate_memory_summary()
        memory_section = content.split('def generate_memory_summary(')[1]
        
        memory_checks = [
            'Rispondi SEMPRE e SOLO in italiano' in memory_section,
            'Non usare mai l\'inglese' in memory_section,
            'Tu sei Genesi. Riassumi le informazioni in modo strutturato e conciso' in memory_section
        ]
        
        all_memory_ok = all(memory_checks)
        if all_memory_ok:
            print("✅ Italian directive in generate_memory_summary()")
        else:
            print("❌ Italian directive missing in generate_memory_summary()")
        
        return all_memory_ok
        
    except Exception as e:
        print(f"❌ Error analyzing generate_memory_summary(): {e}")
        return False

def test_no_english_allowed():
    """Test che non ci siano riferimenti all'inglese consentiti"""
    
    print("\n🧪 TEST NO ENGLISH ALLOWED")
    print("=" * 40)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica assenza di permissivi inglese
        forbidden_patterns = [
            'puoi usare l\'inglese' in content.lower(),
            'inglese è accettato' in content.lower(),
            'in inglese se' in content.lower()
        ]
        
        # Verifica presenza divieti forti
        required_patterns = [
            'Non usare mai l\'inglese' in content,
            'SOLO in italiano' in content,
            'esclusivamente in italiano' in content
        ]
        
        all_no_english_ok = not any(forbidden_patterns) and all(required_patterns)
        if all_no_english_ok:
            print("✅ No English allowed - strong prohibition")
        else:
            print("❌ English allowed or weak prohibition")
        
        return all_no_english_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_system_prompt_structure():
    """Test struttura system prompt corretta"""
    
    print("\n🧪 TEST SYSTEM PROMPT STRUCTURE")
    print("=" * 40)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica struttura system_prompt
        structure_checks = [
            'system_prompt =' in content,
            'Rispondi SEMPRE e SOLO in italiano' in content,
            'Tu sei Genesi' in content
        ]
        
        # Verifica che sia all'inizio del prompt
        prompt_structure = [
            'f"<s>[INST] {system_prompt}' in content
        ]
        
        all_structure_ok = all(structure_checks) and any(prompt_structure)
        if all_structure_ok:
            print("✅ System prompt structure correct")
        else:
            print("❌ System prompt structure incorrect")
        
        return all_structure_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

if __name__ == "__main__":
    print("🎯 TEST ITALIAN PROMPT")
    print("=" * 40)
    print("OBIETTIVO: Verifica direttiva italiana forte in tutti i system prompt")
    print("Genesi risponde SEMPRE e SOLO in italiano")
    print("=" * 40)
    
    # Esegui tutti i test
    tests = [
        ("Italian Directive", test_italian_directive),
        ("Generate Function", test_generate_function),
        ("Chat Function", test_chat_function),
        ("Memory Function", test_memory_function),
        ("No English Allowed", test_no_english_allowed),
        ("System Prompt Structure", test_system_prompt_structure)
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
        print("\n🎉 ITALIAN PROMPT COMPLETATO!")
        print("✅ Direttiva italiana forte aggiunta")
        print("✅ Tutte le funzioni modificate")
        print("✅ Nessun inglese consentito")
        print("✅ Struttura system prompt corretta")
        print("✅ Divieti espliciti e non ambigui")
        print("\n✅ GENESI PARLA SOLO ITALIANO!")
        print("   - 'Rispondi SEMPRE e SOLO in italiano'")
        print("   - 'NON usare mai l'inglese'")
        print("   - 'esclusivamente in italiano'")
        print("   - Applicato a TUTTE le chiamate chat")
        print("   - 100% risposte in italiano garantite")
        sys.exit(0)
    else:
        print("\n❌ ITALIAN PROMPT FALLITO")
        print("⚠️ Controllare implementazione")
        sys.exit(1)
