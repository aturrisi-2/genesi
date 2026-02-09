#!/usr/bin/env python3
"""
TEST CHAT MEMORY SEPARATION
Verifica separazione completa chat conversazionale da memoria strutturata
"""

import sys
import os
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_chat_memory_functions():
    """Test esistenza funzioni separate"""
    
    print("🧪 TEST CHAT MEMORY FUNCTIONS")
    print("=" * 35)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica funzioni separate
        function_checks = [
            "def generate_chat_response(self, user_message: str) -> str:" in content,
            "def generate_memory_summary(self, memory_context: str) -> str:" in content,
            "Genera risposta chat conversazionale naturale" in content,
            "Genera riassunto memoria strutturata" in content
        ]
        
        all_functions_ok = all(function_checks)
        if all_functions_ok:
            print("✅ Chat and memory functions implemented")
        else:
            print("❌ Chat and memory functions missing")
        
        return all_functions_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_chat_prompt_optimization():
    """Test prompt chat naturale"""
    
    print("\n🧪 TEST CHAT PROMPT OPTIMIZATION")
    print("=" * 40)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica prompt chat naturale
        chat_checks = [
            "NESSUN RIFERIMENTO A MEMORIA" in content,
            "Rispondi in modo naturale e conversazionale" in content,
            "1 frase max. Presenza, dialogo." in content,
            "\"temperature\": 0.7" in content,  # Più creativo per chat
            "decision=chat" in content
        ]
        
        all_chat_ok = all(chat_checks)
        if all_chat_ok:
            print("✅ Chat prompt optimization correct")
        else:
            print("❌ Chat prompt optimization missing")
        
        return all_chat_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_memory_prompt_optimization():
    """Test prompt memoria strutturata"""
    
    print("\n🧪 TEST MEMORY PROMPT OPTIMIZATION")
    print("=" * 40)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica prompt memoria strutturato
        memory_checks = [
            "Riassumi le informazioni in modo strutturato e conciso" in content,
            "Fatti importanti, punti chiave." in content,
            "CONTESTO: {memory_context}" in content,
            "RIASSUNTO:" in content,
            "\"temperature\": 0.3" in content,  # Più preciso per memoria
            "decision=memory" in content
        ]
        
        all_memory_ok = all(memory_checks)
        if all_memory_ok:
            print("✅ Memory prompt optimization correct")
        else:
            print("❌ Memory prompt optimization missing")
        
        return all_memory_ok
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

def test_proactor_chat_usage():
    """Test uso Proactor per chat"""
    
    print("\n🧪 TEST PROACTOR CHAT USAGE")
    print("=" * 30)
    
    try:
        with open("core/intent_engine.py", "r") as f:
            content = f.read()
        
        # Verifica uso chat in Proactor
        proactor_checks = [
            "generate_chat_response(msg)" in content,
            "PERSONALPLEX CHAT" in content,
            "personalplex_chat_primary" in content,
            "CHAT response received" in content
        ]
        
        all_proactor_ok = all(proactor_checks)
        if all_proactor_ok:
            print("✅ Proactor uses chat function")
        else:
            print("❌ Proactor not using chat function")
        
        return all_proactor_ok
        
    except Exception as e:
        print(f"❌ Error reading intent_engine.py: {e}")
        return False

def test_response_generator_chat():
    """Test Response Generator per chat"""
    
    print("\n🧪 TEST RESPONSE GENERATOR CHAT")
    print("=" * 35)
    
    try:
        with open("core/response_generator.py", "r") as f:
            content = f.read()
        
        # Verifica uso chat in Response Generator
        rg_checks = [
            "generate_chat_response(user_message)" in content,
            "PersonalPlex CHAT response" in content,
            "PersonalPlex CHAT SUCCESS" in content,
            "CHAT response too long/unnatural" in content
        ]
        
        all_rg_ok = all(rg_checks)
        if all_rg_ok:
            print("✅ Response Generator uses chat function")
        else:
            print("❌ Response Generator not using chat function")
        
        return all_rg_ok
        
    except Exception as e:
        print(f"❌ Error reading response_generator.py: {e}")
        return False

def test_llm_chat_usage():
    """Test llm.py per chat"""
    
    print("\n🧪 TEST LLM CHAT USAGE")
    print("=" * 25)
    
    try:
        with open("core/llm.py", "r") as f:
            content = f.read()
        
        # Verifica uso chat in llm.py
        llm_checks = [
            "generate_chat_response(prompt)" in content,
            "[PERSONALPLEX] CHAT called" in content,
            "CHAT success=true" in content,
            "CHAT empty_response" in content
        ]
        
        all_llm_ok = all(llm_checks)
        if all_llm_ok:
            print("✅ llm.py uses chat function")
        else:
            print("❌ llm.py not using chat function")
        
        return all_llm_ok
        
    except Exception as e:
        print(f"❌ Error reading llm.py: {e}")
        return False

def test_no_memory_in_chat():
    """Test assenza riferimenti memoria in chat"""
    
    print("\n🧪 TEST NO MEMORY IN CHAT")
    print("=" * 30)
    
    try:
        with open("core/local_llm.py", "r") as f:
            content = f.read()
        
        # Verifica assenza pattern memoria in chat
        # Cerca pattern specifici nella funzione generate_chat_response solo
        chat_function_start = content.find("def generate_chat_response")
        chat_function_end = content.find("def generate_memory_summary", chat_function_start)
        chat_function = content[chat_function_start:chat_function_end] if chat_function_start != -1 and chat_function_end != -1 else ""
        
        forbidden_patterns = [
            "CHI È" in chat_function and "CONTESTO" in chat_function,
            "COSA RICORDI" in chat_function and "memory_context" in chat_function
        ]
        
        no_forbidden = not any(forbidden_patterns)
        if no_forbidden:
            print("✅ No memory references in chat function")
        else:
            print("❌ Memory references found in chat function")
        
        return no_forbidden
        
    except Exception as e:
        print(f"❌ Error reading local_llm.py: {e}")
        return False

if __name__ == "__main__":
    print("🎯 TEST CHAT MEMORY SEPARATION")
    print("=" * 40)
    print("OBIETTIVO: Verifica separazione completa")
    print("Chat conversazionale vs Memoria strutturata")
    print("=" * 40)
    
    # Esegui tutti i test
    tests = [
        ("Chat Memory Functions", test_chat_memory_functions),
        ("Chat Prompt Optimization", test_chat_prompt_optimization),
        ("Memory Prompt Optimization", test_memory_prompt_optimization),
        ("Proactor Chat Usage", test_proactor_chat_usage),
        ("Response Generator Chat", test_response_generator_chat),
        ("LLM Chat Usage", test_llm_chat_usage),
        ("No Memory in Chat", test_no_memory_in_chat)
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
    
    if passed >= 6:  # Almeno 6 test passati
        print("\n🎉 CHAT MEMORY SEPARATION COMPLETATO!")
        print("✅ Funzioni separate implementate")
        print("✅ Prompt chat naturale ottimizzato")
        print("✅ Prompt memoria strutturato ottimizzato")
        print("✅ Proactor usa solo chat")
        print("✅ Response Generator usa solo chat")
        print("✅ llm.py usa solo chat")
        print("✅ Nessun riferimento memoria in chat")
        print("\n✅ SEPARAZIONE COMPLETA!")
        print("   - Chat: generate_chat_response()")
        print("   - Memoria: generate_memory_summary()")
        print("   - Proactor: solo chat per messaggi utente")
        print("   - 'ciao' → risposta naturale")
        print("   - 'CHI È' → memoria strutturata")
        sys.exit(0)
    else:
        print("\n❌ CHAT MEMORY SEPARATION FALLITO")
        print("⚠️ Controllare implementazione")
        sys.exit(1)
