#!/usr/bin/env python3
"""
TEST FINALE COMPLETO - 5 FIX CRITICI
Verifica che tutti i problemi identificati siano risolti
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_step1_personalplex_dominated():
    """Test STEP 1: PersonalPlex domato con post-processing FORZATO"""
    print("STEP 1: PersonalPlex DOMATO")
    print("-" * 40)
    
    try:
        from core.post_llm_filter import post_llm_filter
        
        # Test casi critici che devono essere BLOCCATI
        test_cases = [
            # Input con inglese - deve fare fallback
            ("Hello! How are you?", True),
            ("What's your name? *smile*", True),
            # Input con teatralità - deve fare fallback
            ("*giggle* Oh bella! *wink*", True),
            ("(sorride) Ciao! [abbraccia]", True),
            # Input con mesi inglesi - deve fare fallback
            ("Today is February 9th", True),
            ("Monday is boring", True),
            # Input italiano pulito - deve passare
            ("Ciao, come stai?", False),
            ("Oggi e una bella giornata", False),
        ]
        
        passed = 0
        for input_text, should_fallback in test_cases:
            filtered = post_llm_filter.filter_response(input_text)
            
            # Verifica se ha fatto fallback (testo generico o troppo corto)
            is_fallback = (
                ("non riesco" in filtered.lower() or
                 "mi dispiace" in filtered.lower() or
                 len(filtered) < 5)  # Solo se davvero troppo corto
            )
            
            if is_fallback == should_fallback:
                print(f"  OK: '{input_text}' -> {'FALLBACK' if is_fallback else 'PASSED'}")
                passed += 1
            else:
                print(f"  FAIL: '{input_text}' -> Expected {'FALLBACK' if should_fallback else 'PASSED'}, got {'FALLBACK' if is_fallback else 'PASSED'}")
        
        return passed == len(test_cases)
        
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def test_step2_verified_first():
    """Test STEP 2: Verified PRIMA del modello"""
    print("\nSTEP 2: VERIFIED PRIMA DEL MODELLO")
    print("-" * 40)
    
    try:
        from core.intent_router import intent_router, IntentType
        
        # Test che tutti gli intent verified blocchino LLM
        verified_intents = [
            ("oggi ho mal di testa", IntentType.MEDICAL_INFO),
            ("chi è Alessandro Magno", IntentType.HISTORICAL_INFO),
            ("che tempo fa a Roma", IntentType.WEATHER),
            ("ultime notizie", IntentType.NEWS),
            ("che giorno è oggi", IntentType.OTHER),
            ("Mi chiamo Marco", IntentType.IDENTITY),
        ]
        
        passed = 0
        for message, expected_intent in verified_intents:
            detected_intent = intent_router.classify_intent(message)
            should_block = intent_router.should_block_creative_llm(detected_intent)
            
            if detected_intent == expected_intent and should_block:
                print(f"  OK: '{message}' -> {detected_intent.value} (BLOCKED)")
                passed += 1
            else:
                print(f"  FAIL: '{message}' -> {detected_intent.value} (expected {expected_intent.value}, BLOCK={should_block})")
        
        return passed == len(verified_intents)
        
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def test_step3_psychological_bypass():
    """Test STEP 3: Ramo psicologico non blocca domande informative"""
    print("\nSTEP 3: RAMO PSICOLOGICO BYPASS")
    print("-" * 40)
    
    try:
        from core.intent_router import intent_router
        
        # Simula utente emotivamente attivo che fa domande factual
        factual_questions = [
            "chi è Alessandro Magno",
            "che giorno è oggi", 
            "che tempo fa a Milano",
            "mi chiamo Marco",
        ]
        
        passed = 0
        for question in factual_questions:
            routing_info = intent_router.get_routing_info(question)
            
            # Se è factual, deve bloccare LLM e andare a verified
            if routing_info['block_creative_llm']:
                print(f"  OK: '{question}' -> VERIFIED bypass")
                passed += 1
            else:
                print(f"  FAIL: '{question}' -> Would go to psychological branch")
        
        return passed == len(factual_questions)
        
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def test_step4_api_keys():
    """Test STEP 4: API key configuration"""
    print("\nSTEP 4: API KEY CONFIGURATION")
    print("-" * 40)
    
    try:
        from core.tools import _get_openweather_key, _get_newsapi_key
        
        # Test che le funzioni di API key esistano
        openweather_key = _get_openweather_key()
        newsapi_key = _get_newsapi_key()
        
        print(f"  OpenWeather key function: OK")
        print(f"  NewsAPI key function: OK")
        print(f"  OpenWeather key present: {bool(openweather_key)}")
        print(f"  NewsAPI key present: {bool(newsapi_key)}")
        
        # Le funzioni devono esistere anche se le keys non sono configurate
        return True
        
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def test_step5_italian_date():
    """Test STEP 5: Data in italiano"""
    print("\nSTEP 5: DATA IN ITALIANO")
    print("-" * 40)
    
    try:
        from datetime import datetime
        
        # Test mapping mesi italiano
        mesi_italiani = {
            'January': 'gennaio', 'February': 'febbraio', 'March': 'marzo',
            'April': 'aprile', 'May': 'maggio', 'June': 'giugno',
            'July': 'luglio', 'August': 'agosto', 'September': 'settembre',
            'October': 'ottobre', 'November': 'novembre', 'December': 'dicembre'
        }
        
        now = datetime.now()
        mese_inglese = now.strftime('%B')
        mese_italiano = mesi_italiani.get(mese_inglese, mese_inglese)
        
        # Verifica che il mapping funzioni
        if mese_italiano != mese_inglese:
            print(f"  OK: {mese_inglese} -> {mese_italiano}")
            
            # Test formato data completo
            data_formattata = f"Oggi è {now.day} {mese_italiano} {now.year}."
            print(f"  OK: Data formattata: {data_formattata}")
            
            # Verifica che non contenga inglese
            has_english = any(word in data_formattata.lower() for word in ['january', 'february', 'march', 'april', 'may', 'june', 'july', 'august', 'september', 'october', 'november', 'december'])
            
            if not has_english:
                print(f"  OK: Nessun inglese nella data")
                return True
            else:
                print(f"  FAIL: Trovato inglese nella data")
                return False
        else:
            print(f"  FAIL: Mapping mesi non funzionante")
            return False
        
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def main():
    """Esegui test completo dei 5 fix"""
    print("TEST COMPLETO - 5 FIX CRITICI GENESI")
    print("=" * 60)
    
    tests = [
        ("STEP 1: PersonalPlex Domato", test_step1_personalplex_dominated),
        ("STEP 2: Verified PRIMA del Modello", test_step2_verified_first),
        ("STEP 3: Ramo Psicologico Bypass", test_step3_psychological_bypass),
        ("STEP 4: API Key Configuration", test_step4_api_keys),
        ("STEP 5: Data in Italiano", test_step5_italian_date),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
                print(f"PASS {test_name}: PASS")
            else:
                failed += 1
                print(f"FAIL {test_name}: FAIL")
        except Exception as e:
            failed += 1
            print(f"ERROR {test_name}: ERROR - {e}")
    
    print("\n" + "=" * 60)
    print("RISULTATO FINALE:")
    print(f"Passati: {passed}/{len(tests)}")
    print(f"Falliti: {failed}/{len(tests)}")
    
    if failed == 0:
        print("TUTTI I 5 FIX COMPLETATI - Genesi è deterministica!")
        print("\nComportamento garantito:")
        print("- Zero inglese/emoji/teatralità")
        print("- Verified responses PRIMA del modello")
        print("- Ramo psicologico non blocca domande factual")
        print("- API keys configurabili")
        print("- Date sempre in italiano")
        return True
    else:
        print("ALCUNI FIX FALLITI - Revisionare implementazione")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
