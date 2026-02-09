#!/usr/bin/env python3
"""
TEST COMPLETO RIPRISTINO GENESI
Verifica: 1) Fix crash datetime, 2) Blocco creatività spuria, 3) Memoria identitaria
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.chat import _handle_verified_response
from api.chat import ChatRequest
from core.intent_router import intent_router, IntentType
from core.identity_memory import extract_name_from_message, save_user_name, get_user_name, is_name_query
from core.post_llm_filter import post_llm_filter
from core.human_fallback import human_fallback

def test_datetime_fix():
    """Test 1: Verifica fix crash datetime"""
    print("TEST 1: FIX CRASH DATETIME")
    print("=" * 50)
    
    # Simula richiesta per tempo
    routing_info = {
        'intent': 'other',
        'source': 'system_time'
    }
    
    request = ChatRequest(user_id="test-user", message="che ore sono")
    
    try:
        # Questa chiamata NON deve più crashare
        result = _handle_verified_response(
            routing_info=routing_info,
            request=request,
            state=None,
            recent_memories=[],
            relevant_memories=[],
            tone=None
        )
        
        # Verifica che la risposta contenga l'ora
        response = result.get("response", "")
        if "ore" in response.lower() and ":" in response:
            print("✅ DATETIME FIX: Pass - Risposta tempo funzionante")
            print(f"   Response: {response}")
            return True
        else:
            print("❌ DATETIME FIX: Fail - Formato ora non corretto")
            print(f"   Response: {response}")
            return False
            
    except Exception as e:
        print(f"❌ DATETIME FIX: Fail - Crash: {e}")
        return False

def test_identity_memory():
    """Test 2: Verifica memoria identitaria"""
    print("\n\nTEST 2: MEMORIA IDENTITARIA")
    print("=" * 50)
    
    user_id = "test-identity-user"
    
    # Test 2a: Estrazione nome
    test_name_message = "Mi chiamo Marco"
    extracted_name = extract_name_from_message(test_name_message)
    
    if extracted_name == "Marco":
        print("✅ NAME EXTRACTION: Pass")
    else:
        print(f"❌ NAME EXTRACTION: Fail - Expected 'Marco', got '{extracted_name}'")
        return False
    
    # Test 2b: Salvataggio nome
    if save_user_name(user_id, "Marco"):
        print("✅ NAME SAVE: Pass")
    else:
        print("❌ NAME SAVE: Fail")
        return False
    
    # Test 2c: Recupero nome
    retrieved_name = get_user_name(user_id)
    if retrieved_name == "Marco":
        print("✅ NAME RETRIEVE: Pass")
    else:
        print(f"❌ NAME RETRIEVE: Fail - Expected 'Marco', got '{retrieved_name}'")
        return False
    
    # Test 2d: Riconoscimento query nome
    query_messages = [
        "ti ricordi il mio nome",
        "ricordi il mio nome", 
        "come ti chiami",
        "il mio nome"
    ]
    
    for query in query_messages:
        if is_name_query(query):
            print(f"✅ NAME QUERY: Pass - '{query}'")
        else:
            print(f"❌ NAME QUERY: Fail - '{query}' non riconosciuta")
            return False
    
    return True

def test_identity_routing():
    """Test 3: Verifica routing identità"""
    print("\n\nTEST 3: ROUTING IDENTITÀ")
    print("=" * 50)
    
    identity_messages = [
        ("Mi chiamo Laura", IntentType.IDENTITY),
        ("il mio nome è Paolo", IntentType.IDENTITY),
        ("ti ricordi il mio nome", IntentType.IDENTITY),
        ("come ti chiami", IntentType.IDENTITY)
    ]
    
    for message, expected_intent in identity_messages:
        detected_intent = intent_router.classify_intent(message)
        if detected_intent == expected_intent:
            print(f"✅ IDENTITY ROUTING: Pass - '{message}' → {detected_intent.value}")
        else:
            print(f"❌ IDENTITY ROUTING: Fail - '{message}' → {detected_intent.value}, expected {expected_intent.value}")
            return False
    
    return True

def test_creativity_filter():
    """Test 4: Verifica blocco creatività spuria"""
    print("\n\nTEST 4: BLOCCO CREATIVITÀ SPURIA")
    print("=" * 50)
    
    test_cases = [
        # Input con teatralità
        ("Ciao! *smile* Come stai? *wink*", "Ciao! Come stai?"),
        # Input con inglese
        ("Hello! Come stai? 😊", "Come stai?"),
        # Input con azioni teatrali
        ("*adotta tono festoso* Oh bella! *giggle*", "Oh bella!"),
        # Input con emoji
        ("Ciao! 😊 Come va? 🎉", "Ciao! Come va?"),
        # Input con parole inglesi nel testo
        ("Ottimo! Amazing davvero wonderful", "Ottimo! davvero wonderful"),
        # Input con descrizioni teatrali
        ("*esprime curiosità* Dimmi di più", "Dimmi di più")
    ]
    
    passed = 0
    for input_text, expected_clean in test_cases:
        filtered = post_llm_filter.filter_response(input_text)
        
        # Verifica che il filtro abbia rimosso elementi inappropriati
        has_teatral = "*" in filtered or "(" in filtered or "[" in filtered
        has_emoji = any(char in filtered for char in ["😊", "😎", "🎉", "📆"])
        has_english = any(word in filtered.lower() for word in ["hello", "amazing", "wonderful", "smile", "wink", "giggle"])
        
        if not has_teatral and not has_emoji and not has_english:
            print(f"✅ CREATIVITY FILTER: Pass - '{input_text}' → '{filtered}'")
            passed += 1
        else:
            print(f"❌ CREATIVITY FILTER: Fail - '{input_text}' → '{filtered}'")
            print(f"   Teatral: {has_teatral}, Emoji: {has_emoji}, English: {has_english}")
    
    return passed == len(test_cases)

def test_verified_identity_response():
    """Test 5: Verifica risposta identità verificata"""
    print("\n\nTEST 5: RISPOSTA IDENTITÀ VERIFICATA")
    print("=" * 50)
    
    user_id = "test-identity-response"
    
    # Prima salva un nome
    save_user_name(user_id, "Giulia")
    
    # Test 5a: Fornitura nome
    routing_info = {'intent': 'identity', 'source': 'identity_memory'}
    request = ChatRequest(user_id=user_id, message="Mi chiamo Francesco")
    
    try:
        result = _handle_verified_response(
            routing_info=routing_info,
            request=request,
            state=None,
            recent_memories=[],
            relevant_memories=[],
            tone=None
        )
        
        response = result.get("response", "")
        if "Francesco" in response and "piacere" in response.lower():
            print("✅ IDENTITY NAME PROVIDE: Pass")
            print(f"   Response: {response}")
        else:
            print("❌ IDENTITY NAME PROVIDE: Fail")
            print(f"   Response: {response}")
            return False
    except Exception as e:
        print(f"❌ IDENTITY NAME PROVIDE: Fail - Exception: {e}")
        return False
    
    # Test 5b: Richiesta nome salvato
    request2 = ChatRequest(user_id=user_id, message="ti ricordi il mio nome")
    
    try:
        result2 = _handle_verified_response(
            routing_info=routing_info,
            request=request2,
            state=None,
            recent_memories=[],
            relevant_memories=[],
            tone=None
        )
        
        response2 = result2.get("response", "")
        if "Giulia" in response2:
            print("✅ IDENTITY NAME RECALL: Pass")
            print(f"   Response: {response2}")
        else:
            print("❌ IDENTITY NAME RECALL: Fail - Should recall 'Giulia'")
            print(f"   Response: {response2}")
            return False
    except Exception as e:
        print(f"❌ IDENTITY NAME RECALL: Fail - Exception: {e}")
        return False
    
    return True

def main():
    """Esegui tutti i test di ripristino"""
    print("TEST COMPLETO RIPRISTINO GENESI")
    print("=" * 60)
    
    tests = [
        ("Fix Crash DateTime", test_datetime_fix),
        ("Memoria Identitaria", test_identity_memory),
        ("Routing Identità", test_identity_routing),
        ("Blocco Creatività", test_creativity_filter),
        ("Risposta Identità Verificata", test_verified_identity_response)
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
                print(f"✅ {test_name}: PASS")
            else:
                failed += 1
                print(f"❌ {test_name}: FAIL")
        except Exception as e:
            failed += 1
            print(f"❌ {test_name}: ERROR - {e}")
    
    print("\n" + "=" * 60)
    print("RISULTATO FINALE:")
    print(f"Passati: {passed}/{len(tests)}")
    print(f"Falliti: {failed}/{len(tests)}")
    
    if failed == 0:
        print("🎉 TUTTI I TEST PASSATI - Genesi ripristinata!")
        return True
    else:
        print("⚠️ ALCUNI TEST FALLITI - Revisionare i fix")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
