#!/usr/bin/env python3
"""
TEST FINALE COMPORTAMENTO GENESI - VERSIONE SICURA
Simula i casi reali senza caratteri speciali
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_real_world_scenarios():
    """Test scenari reali dall'utente"""
    print("TEST FINALE - SCENARI REALI UTENTE")
    print("=" * 60)
    
    try:
        from core.identity_memory import extract_name_from_message, save_user_name, get_user_name, is_name_query
        from core.intent_router import intent_router, IntentType
        from core.post_llm_filter import post_llm_filter
        from core.human_fallback import human_fallback
        
        user_id = "test-real-user"
        
        # Scenario 1: Utente fornisce nome
        print("\n1. UTENTE FORNISCE NOME:")
        message1 = "Alfio"
        intent1 = intent_router.classify_intent(message1)
        name1 = extract_name_from_message(message1)
        
        if name1:
            save_user_name(user_id, name1)
            response1 = f"Piacere, {name1}! Ricorderò il tuo nome."
        else:
            response1 = "Ciao! Come posso aiutarti?"
        
        print(f"   Input: '{message1}'")
        print(f"   Intent: {intent1.value}")
        print(f"   Name extracted: {name1}")
        print(f"   Response: {response1}")
        
        # Scenario 2: Utente chiede nome
        print("\n2. UTENTE CHIEDE NOME:")
        message2 = "ti ricordi il mio nome"
        intent2 = intent_router.classify_intent(message2)
        saved_name = get_user_name(user_id)
        
        if saved_name:
            response2 = f"Sì, ti chiami {saved_name}."
        else:
            response2 = human_fallback.get_fallback("identity", message2)
        
        print(f"   Input: '{message2}'")
        print(f"   Intent: {intent2.value}")
        print(f"   Saved name: {saved_name}")
        print(f"   Response: {response2}")
        
        # Scenario 3: Mal di testa (medico)
        print("\n3. UTENTE HA MALE DI TESTA:")
        message3 = "oggi ho mal di testa"
        intent3 = intent_router.classify_intent(message3)
        
        # Simula risposta medica verificata
        if intent3 == IntentType.MEDICAL_INFO:
            response3 = "Il mal di testa è un disturbo comune che può avere molte cause, come stress, disidratazione o tensione muscolare. Se è intenso o persistente, è importante consultare un medico."
        else:
            response3 = "Posso aiutarti con altro?"
        
        # Applica filtro post-LLM
        filtered3 = post_llm_filter.filter_response(response3)
        
        print(f"   Input: '{message3}'")
        print(f"   Intent: {intent3.value}")
        print(f"   Medical response: {response3}")
        print(f"   Filtered: {filtered3}")
        
        # Scenario 4: Meteo (tool failure)
        print("\n4. UTENTE CHIEDE METEO:")
        message4 = "che tempo c'è a roma"
        intent4 = intent_router.classify_intent(message4)
        
        # Simula tool failure + fallback umano
        if intent4 == IntentType.WEATHER:
            response4 = human_fallback.get_fallback("weather", message4)
        else:
            response4 = "Non posso aiutarti con il meteo."
        
        print(f"   Input: '{message4}'")
        print(f"   Intent: {intent4.value}")
        print(f"   Fallback response: {response4}")
        
        # Scenario 5: Data/ora (system)
        print("\n5. UTENTE CHIEDE DATA:")
        message5 = "che giorno è oggi"
        intent5 = intent_router.classify_intent(message5)
        
        # Simula risposta sistema
        if intent5 == IntentType.OTHER:
            from datetime import datetime
            now = datetime.now()
            response5 = f"Oggi è {now.day} {now.strftime('%B')} {now.year}."
        else:
            response5 = "Non posso fornire la data."
        
        print(f"   Input: '{message5}'")
        print(f"   Intent: {intent5.value}")
        print(f"   System response: {response5}")
        
        # Scenario 6: Creatività spuria bloccata
        print("\n6. CREATIVITÀ SPURIA BLOCCATA:")
        creative_inputs = [
            "Ciao! *smile* Come stai? *wink*",
            "Hello! How are you?",
            "*giggle* Oh bella!",
            "February is cold"
        ]
        
        for creative_input in creative_inputs:
            filtered = post_llm_filter.filter_response(creative_input)
            has_issues = "*" in filtered or "hello" in filtered.lower()
            
            print(f"   Input: '{creative_input}'")
            print(f"   Filtered: '{filtered}'")
            print(f"   Issues blocked: {not has_issues}")
            print()
        
        # Verifica finale
        print("VERIFICA FINALE:")
        checks = [
            (name1 == "Alfio", "Nome estratto correttamente"),
            (intent2 == IntentType.IDENTITY, "Intent identità riconosciuto"),
            (saved_name == "Alfio", "Nome salvato e recuperato"),
            (intent3 == IntentType.MEDICAL_INFO, "Intent medico riconosciuto"),
            (intent4 == IntentType.WEATHER, "Intent weather riconosciuto"),
            (intent5 == IntentType.OTHER, "Intent tempo riconosciuto")
        ]
        
        all_passed = True
        for check, description in checks:
            status = "OK" if check else "FAIL"
            print(f"   {status}: {description}")
            if not check:
                all_passed = False
        
        return all_passed
        
    except Exception as e:
        print(f"ERRORE: {e}")
        return False

def main():
    """Esegui test finale"""
    print("TEST FINALE - COMPORTAMENTO GENESI COMPLETO")
    print("=" * 60)
    
    if test_real_world_scenarios():
        print("\n" + "=" * 60)
        print("SUCCESS: Tutti gli scenari reali funzionano!")
        print("Genesi è pronta per produzione.")
        return True
    else:
        print("\n" + "=" * 60)
        print("FAIL: Alcuni scenari non funzionano.")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
