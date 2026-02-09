#!/usr/bin/env python3
"""
TEST SEMPLIFICATO RIPRISTINO GENESI
Verifica solo i componenti critici senza dipendenze esterne
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_identity_memory():
    """Test memoria identitaria standalone"""
    print("TEST: MEMORIA IDENTITARIA")
    print("=" * 50)
    
    try:
        from core.identity_memory import extract_name_from_message, save_user_name, get_user_name, is_name_query
        
        # Test estrazione nome
        test_cases = [
            ("Mi chiamo Marco", "Marco"),
            ("il mio nome è Paolo", "Paolo"),
            ("io sono Laura", "Laura"),
            ("sono Giulia", "Giulia"),
            ("ciao", None)  # Non deve estrarre nulla
        ]
        
        for message, expected in test_cases:
            result = extract_name_from_message(message)
            if result == expected:
                print(f"OK EXTRACTION: '{message}' -> '{result}'")
            else:
                print(f"FAIL EXTRACTION: '{message}' -> '{result}' (expected '{expected}')")
                return False
        
        # Test query detection
        query_cases = [
            ("ti ricordi il mio nome", True),
            ("ricordi il mio nome", True),
            ("come ti chiami", True),
            ("che tempo fa", False),
            ("ciao come stai", False)
        ]
        
        for message, expected in query_cases:
            result = is_name_query(message)
            if result == expected:
                print(f"OK QUERY DETECT: '{message}' -> {result}")
            else:
                print(f"FAIL QUERY DETECT: '{message}' -> {result} (expected {expected})")
                return False
        
        print("OK MEMORIA IDENTITARIA: Tutti i test passati")
        return True
        
    except Exception as e:
        print(f"FAIL MEMORIA IDENTITARIA: Errore - {e}")
        return False

def test_intent_router():
    """Test routing identità"""
    print("\n\nTEST: INTENT ROUTER")
    print("=" * 50)
    
    try:
        from core.intent_router import intent_router, IntentType
        
        identity_cases = [
            "Mi chiamo Marco",
            "il mio nome è Laura", 
            "ti ricordi il mio nome",
            "come ti chiami"
        ]
        
        for message in identity_cases:
            intent = intent_router.classify_intent(message)
            if intent == IntentType.IDENTITY:
                print(f"OK ROUTING: '{message}' -> {intent.value}")
            else:
                print(f"FAIL ROUTING: '{message}' -> {intent.value} (expected IDENTITY)")
                return False
        
        print("OK INTENT ROUTER: Tutti i test passati")
        return True
        
    except Exception as e:
        print(f"FAIL INTENT ROUTER: Errore - {e}")
        return False

def test_post_llm_filter():
    """Test filtro post-LLM"""
    print("\n\nTEST: POST-LLM FILTER")
    print("=" * 50)
    
    try:
        from core.post_llm_filter import post_llm_filter
        
        test_cases = [
            # Input contaminati → output puliti
            ("Ciao! *smile* Come stai? *wink*", "Ciao! Come stai?"),
            ("Hello! 😊 How are you?", "How are you?"),
            ("*giggle* Oh bella! *esprime entusiasmo*", "Oh bella!"),
            ("February is cold", "is cold"),
            ("*adjusts sunglasses* Hey there", "Hey there")
        ]
        
        for input_text, expected_contains in test_cases:
            filtered = post_llm_filter.filter_response(input_text)
            
            # Verifica che abbia rimosso asterischi e emoji
            has_asterisks = "*" in filtered
            has_emoji = any(char in filtered for char in ["😊", "😎", "🎉"])
            has_english_words = any(word in filtered.lower() for word in ["hello", "february", "adjusts"])
            
            if not has_asterisks and not has_emoji:
                print(f"OK FILTER: '{input_text}' -> '{filtered}'")
            else:
                print(f"FAIL FILTER: '{input_text}' -> '{filtered}' (still has issues)")
                print(f"   Asterisks: {has_asterisks}, Emoji: {has_emoji}")
                return False
        
        print("OK POST-LLM FILTER: Tutti i test passati")
        return True
        
    except Exception as e:
        print(f"FAIL POST-LLM FILTER: Errore - {e}")
        return False

def test_human_fallback():
    """Test fallback umani"""
    print("\n\nTEST: HUMAN FALLBACK")
    print("=" * 50)
    
    try:
        from core.human_fallback import human_fallback
        
        test_cases = [
            ("weather", "che tempo fa a roma"),
            ("news", "ultime notizie"),
            ("identity", "ti ricordi il mio nome"),
            ("general", "aiutami")
        ]
        
        for context, query in test_cases:
            fallback = human_fallback.get_fallback(context, query)
            
            # Verifica che sia umano e non tecnico
            is_human = (
                len(fallback) > 10 and
                "errore" not in fallback.lower() and
                "riprova" not in fallback.lower() and
                ("posso aiutarti" in fallback.lower() or "mi dispiace" in fallback.lower())
            )
            
            if is_human:
                print(f"OK FALLBACK: {context} -> '{fallback}'")
            else:
                print(f"FAIL FALLBACK: {context} -> '{fallback}' (non umano)")
                return False
        
        print("OK HUMAN FALLBACK: Tutti i test passati")
        return True
        
    except Exception as e:
        print(f"FAIL HUMAN FALLBACK: Errore - {e}")
        return False

def test_datetime_import():
    """Test import datetime (verifica fix)"""
    print("\n\nTEST: DATETIME IMPORT FIX")
    print("=" * 50)
    
    try:
        # Verifica che il file non abbia import locali di datetime
        with open('c:/Users/turrisia/genesi/api/chat.py', 'r') as f:
            content = f.read()
        
        # Cerca import locali problematici
        problematic_lines = []
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if 'from datetime import datetime' in line and i > 10:  # Dopo gli import globali
                problematic_lines.append(f"Linea {i+1}: {line.strip()}")
        
        if problematic_lines:
            print("FAIL DATETIME FIX: Trovati import locali problematici:")
            for line in problematic_lines:
                print(f"   {line}")
            return False
        else:
            print("OK DATETIME FIX: Nessun import locale problematico")
            
            # Verifica che ci sia l'import globale
            if 'from datetime import datetime' in content:
                print("OK DATETIME FIX: Import globale presente")
            else:
                print("FAIL DATETIME FIX: Import globale mancante")
                return False
            
            return True
        
    except Exception as e:
        print(f"FAIL DATETIME FIX: Errore lettura file - {e}")
        return False

def main():
    """Esegui test semplificati"""
    print("TEST SEMPLIFICATO RIPRISTINO GENESI")
    print("=" * 60)
    
    tests = [
        ("Datetime Import Fix", test_datetime_import),
        ("Memoria Identitaria", test_identity_memory),
        ("Intent Router", test_intent_router),
        ("Post-LLM Filter", test_post_llm_filter),
        ("Human Fallback", test_human_fallback)
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            failed += 1
            print(f"FAIL {test_name}: ERROR - {e}")
    
    print("\n" + "=" * 60)
    print("RISULTATO FINALE:")
    print(f"Passati: {passed}/{len(tests)}")
    print(f"Falliti: {failed}/{len(tests)}")
    
    if failed == 0:
        print("TUTTI I TEST PASSATI - Fix critici funzionanti!")
        return True
    else:
        print("ALCUNI TEST FALLITI - Revisionare i fix")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
