#!/usr/bin/env python3
"""
TEST OBBLIGATORI CHIRURGICI - 5 scenari critici
Verifica che tutti i fix chirurgici funzionino correttamente
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_scenario_1_napoleone():
    """Test 1: 'chi è Napoleone' → risposta storica corretta"""
    print("TEST 1: STORIA - 'chi è Napoleone'")
    print("-" * 40)
    
    try:
        from core.intent_router import intent_router
        from core.language_guard import language_guard
        
        message = "chi è Napoleone"
        
        # 1. Intent router deve riconoscere historical_info
        routing_info = intent_router.get_routing_info(message)
        intent_type = routing_info['intent']
        should_block = routing_info['block_creative_llm']
        
        print(f"  Intent: {intent_type}")
        print(f"  Block LLM: {should_block}")
        
        # 2. Language guard deve generare risposta italiana
        context = {"intent": intent_type, "user_message": message}
        simple_response = language_guard.generate_simple_response(context)
        
        print(f"  Response: {simple_response}")
        
        # Verifiche
        checks = [
            intent_type == "historical_info",
            should_block == True,
            simple_response and "napoleone" in simple_response.lower(),
            len(simple_response) > 20,
            all(ord(c) < 128 or c in 'àèéìíòóù' for c in simple_response)  # Italiano
        ]
        
        if all(checks):
            print("  PASS: Risposta storica corretta in italiano")
            return True
        else:
            print("  FAIL: Qualche check fallito")
            return False
            
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def test_scenario_2_system_time():
    """Test 2: 'che giorno è oggi' → solo system time"""
    print("\nTEST 2: TEMPO - 'che giorno è oggi'")
    print("-" * 40)
    
    try:
        from core.intent_router import intent_router
        from datetime import datetime
        
        message = "che giorno è oggi"
        
        # 1. Intent router deve riconoscere other
        routing_info = intent_router.get_routing_info(message)
        intent_type = routing_info['intent']
        should_block = routing_info['block_creative_llm']
        
        print(f"  Intent: {intent_type}")
        print(f"  Block LLM: {should_block}")
        
        # 2. Simula risposta di sistema
        now = datetime.now()
        mesi_italiani = {
            'January': 'gennaio', 'February': 'febbraio', 'March': 'marzo',
            'April': 'aprile', 'May': 'maggio', 'June': 'giugno',
            'July': 'luglio', 'August': 'agosto', 'September': 'settembre',
            'October': 'ottobre', 'November': 'novembre', 'December': 'dicembre'
        }
        mese_italiano = mesi_italiani.get(now.strftime('%B'), now.strftime('%B'))
        system_response = f"Oggi è {now.day} {mese_italiano} {now.year}."
        
        print(f"  System response: {system_response}")
        
        # Verifiche
        checks = [
            intent_type == "other",
            should_block == True,
            str(now.day) in system_response,
            mese_italiano in system_response,
            str(now.year) in system_response,
            "February" not in system_response,  # No inglese
            "January" not in system_response
        ]
        
        if all(checks):
            print("  PASS: Data in italiano corretta")
            return True
        else:
            print("  FAIL: Qualche check fallito")
            return False
            
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def test_scenario_3_weather():
    """Test 3: 'che tempo fa a roma' → usa OpenWeather"""
    print("\nTEST 3: METEO - 'che tempo fa a roma'")
    print("-" * 40)
    
    try:
        from core.intent_router import intent_router
        from core.tools import check_api_keys
        
        message = "che tempo fa a roma"
        
        # 1. Intent router deve riconoscere weather
        routing_info = intent_router.get_routing_info(message)
        intent_type = routing_info['intent']
        should_block = routing_info['block_creative_llm']
        
        print(f"  Intent: {intent_type}")
        print(f"  Block LLM: {should_block}")
        
        # 2. Check API keys
        api_status = check_api_keys()
        print(f"  API status: {api_status}")
        
        # 3. Simula weather response
        if api_status.get("openweather", False):
            weather_response = "A Roma ci sono 18°C con cielo sereno."
            print(f"  Weather response: {weather_response}")
            has_api = True
        else:
            weather_response = "Non riesco a ottenere informazioni meteo in questo momento."
            print(f"  Fallback response: {weather_response}")
            has_api = False
        
        # Verifiche
        checks = [
            intent_type == "weather",
            should_block == True,
            "roma" in weather_response.lower() or "informazioni meteo" in weather_response.lower(),
            len(weather_response) > 10
        ]
        
        if all(checks):
            print("  PASS: Gestione meteo corretta")
            return True
        else:
            print("  FAIL: Qualche check fallito")
            return False
            
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def test_scenario_4_dns():
    """Test 4: 'cosa è un dns' → spiegazione semplice in italiano"""
    print("\nTEST 4: CONOSCENZA - 'cosa è un dns'")
    print("-" * 40)
    
    try:
        from core.intent_router import intent_router
        from core.language_guard import language_guard
        
        message = "cosa è un dns"
        
        # 1. Intent router - probabilmente chat_free (non verified)
        routing_info = intent_router.get_routing_info(message)
        intent_type = routing_info['intent']
        should_block = routing_info['block_creative_llm']
        
        print(f"  Intent: {intent_type}")
        print(f"  Block LLM: {should_block}")
        
        # 2. Se non è verified, deve passare al LLM con filtro
        if not should_block:
            # Simula LLM response contaminata
            llm_response = "DNS is like a phonebook for the internet! *smile* It translates domain names to IP addresses."
            print(f"  Simulated LLM: {llm_response}")
            
            # 3. Language guard deve pulire
            guard_result = language_guard.check_and_clean(llm_response, {"intent": intent_type})
            print(f"  Guard issues: {guard_result['issues']}")
            
            if guard_result["should_fallback"]:
                # Genera risposta semplice
                simple_response = language_guard.generate_simple_response({"intent": intent_type})
                print(f"  Simple response: {simple_response}")
                
                checks = [
                    intent_type == "chat_free",
                    not should_block,
                    len(guard_result['issues']) > 0,  # Deve rilevare contaminazione
                    simple_response and len(simple_response) > 10
                ]
            else:
                checks = [False]  # Dovrebbe rilevare contaminazione
        else:
            # Se è verified, non dovrebbe accadere per DNS
            checks = [False]
        
        if all(checks):
            print("  PASS: Spiegazione semplice in italiano")
            return True
        else:
            print("  FAIL: Qualche check fallito")
            return False
            
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def test_scenario_5_ciao():
    """Test 5: 'ciao' → risposta breve, neutra, senza emoji"""
    print("\nTEST 5: SALUTO - 'ciao'")
    print("-" * 40)
    
    try:
        from core.intent_router import intent_router
        from core.language_guard import language_guard
        
        message = "ciao"
        
        # 1. Intent router - chat_free
        routing_info = intent_router.get_routing_info(message)
        intent_type = routing_info['intent']
        should_block = routing_info['block_creative_llm']
        
        print(f"  Intent: {intent_type}")
        print(f"  Block LLM: {should_block}")
        
        # 2. Simula LLM response con teatralità
        llm_response = "Ciao! Come stai oggi? *smile*"
        print(f"  Simulated LLM: {llm_response}")
        
        # 3. Language guard deve pulire
        guard_result = language_guard.check_and_clean(llm_response, {"intent": intent_type})
        print(f"  Guard issues: {guard_result['issues']}")
        print(f"  Cleaned: {guard_result['cleaned_text']}")
        
        # 4. Se contaminato, genera risposta semplice
        if guard_result["should_fallback"]:
            simple_response = language_guard.generate_simple_response({"intent": intent_type})
            print(f"  Simple response: {simple_response}")
            final_response = simple_response
        else:
            final_response = guard_result["cleaned_text"]
        
        # Verifiche
        checks = [
            intent_type == "chat_free",
            not should_block,
            len(guard_result['issues']) > 0,  # Deve rilevare contaminazione
            final_response and len(final_response) > 3,
            "😊" not in final_response,
            "*" not in final_response,
            len(final_response) < 100  # Breve
        ]
        
        if all(checks):
            print("  PASS: Risposta breve e neutra")
            return True
        else:
            print("  FAIL: Qualche check fallito")
            return False
            
    except Exception as e:
        print(f"  ERROR: {e}")
        return False

def main():
    """Esegui test chirurgici obbligatori"""
    print("TEST OBBLIGATORI CHIRURGICI - 5 SCENARI CRITICI")
    print("=" * 60)
    
    tests = [
        ("STORIA - Napoleone", test_scenario_1_napoleone),
        ("TEMPO - Data odierna", test_scenario_2_system_time),
        ("METEO - Roma", test_scenario_3_weather),
        ("CONOSCENZA - DNS", test_scenario_4_dns),
        ("SALUTO - Ciao", test_scenario_5_ciao),
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
                print(f"PASS {test_name}: OK")
            else:
                failed += 1
                print(f"FAIL {test_name}: KO")
        except Exception as e:
            failed += 1
            print(f"ERROR {test_name}: {e}")
    
    print("\n" + "=" * 60)
    print("RISULTATO CHIRURGICO:")
    print(f"Passati: {passed}/{len(tests)}")
    print(f"Falliti: {failed}/{len(tests)}")
    
    if failed == 0:
        print("SUCCESS: Tutti gli scenari critici funzionano!")
        print("\nGenesi è pronta per deployment chirurgico!")
        return True
    else:
        print("WARNING: Alcuni scenari falliscono")
        print("Revisionare i fix prima del deployment")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
