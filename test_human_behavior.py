#!/usr/bin/env python3
"""
TEST COMPORTAMENTO UMANO STABILE
Verifica filtri post-LLM e fallback umani
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.post_llm_filter import post_llm_filter
from core.human_fallback import human_fallback

def test_post_llm_filter():
    """Testa filtro post-LLM per rimuovere contaminazioni"""
    
    test_cases = [
        # Caso 1: Contaminazione linguistica
        {
            "input": "Hola! Como estas? *giggle* Un bacio strettissimo caridad",
            "context": {"intent": "medical_info"},
            "should_filter": True,
            "description": "Contaminazione spagnolo + teatrale"
        },
        
        # Caso 2: Teatralità inappropriata
        {
            "input": "Oh no! *wink* Come stai? (sussurando) [guarda intorno]",
            "context": {"intent": "emotional_support"},
            "should_filter": True,
            "description": "Azione teatrale in contesto emotivo"
        },
        
        # Caso 3: Affermazioni mediche inappropriate
        {
            "input": "Non preoccuparti, ti guarirò subito. Stai bene, sarai tutto bene.",
            "context": {"intent": "medical_info"},
            "should_filter": True,
            "description": "Promesse mediche inappropriate"
        },
        
        # Caso 4: Risposta normale
        {
            "input": "Ciao! Come stai? Sono qui per aiutarti.",
            "context": {"intent": "chat_free"},
            "should_filter": False,
            "description": "Risposta normale italiana"
        }
    ]
    
    print("TEST POST-LLM FILTER")
    print("=" * 50)
    
    passed = 0
    failed = 0
    
    for i, test in enumerate(test_cases, 1):
        input_text = test["input"]
        context = test["context"]
        should_filter = test["should_filter"]
        description = test["description"]
        
        # Applica filtro
        filtered = post_llm_filter.filter_response(input_text, context)
        
        # Verifica
        if should_filter:
            # Dovrebbe filtrare (output diverso e più pulito)
            success = filtered != input_text and len(filtered) > 10
            status = "FILTERED" if success else "NOT_FILTERED"
        else:
            # Non dovrebbe filtrare (output simile)
            success = filtered == input_text or len(filtered) >= len(input_text) * 0.8
            status = "PRESERVED" if success else "OVER_FILTERED"
        
        if success:
            passed += 1
        else:
            failed += 1
        
        print(f"\nTest {i}: {description}")
        print(f"Status: {status}")
        print(f"Input: '{input_text}'")
        print(f"Output: '{filtered}'")
        print(f"Expected filter: {should_filter}")
    
    print(f"\nRisultati: {passed} passati, {failed} falliti")
    return failed == 0

def test_human_fallback():
    """Testa fallback umani per errori tecnici"""
    
    test_cases = [
        {
            "context": "weather",
            "query": "che tempo fa a roma",
            "expected_type": "weather_fallback"
        },
        {
            "context": "news", 
            "query": "notizie su roma",
            "expected_type": "news_fallback"
        },
        {
            "context": "identity",
            "query": "ti ricordi come mi chiamo",
            "expected_type": "identity_fallback"
        },
        {
            "context": "emotional_distress",
            "query": "sono depresso",
            "expected_type": "emotional_fallback"
        }
    ]
    
    print("\n\nTEST HUMAN FALLBACK")
    print("=" * 50)
    
    passed = 0
    failed = 0
    
    for i, test in enumerate(test_cases, 1):
        context = test["context"]
        query = test["query"]
        expected_type = test["expected_type"]
        
        # Ottieni fallback
        fallback = human_fallback.get_fallback(context, query)
        
        # Verifica
        success = (
            len(fallback) > 10 and  # Non vuoto
            "errore" not in fallback.lower() and  # Non tecnico
            "riprova" not in fallback.lower() and  # Non tecnico
            "posso aiutarti" in fallback.lower() or "mi dispiace" in fallback.lower()  # Umano
        )
        
        if success:
            passed += 1
            status = "HUMAN"
        else:
            failed += 1
            status = "TECHNICAL"
        
        print(f"\nTest {i}: {expected_type}")
        print(f"Status: {status}")
        print(f"Query: '{query}'")
        print(f"Fallback: '{fallback}'")
    
    print(f"\nRisultati: {passed} passati, {failed} falliti")
    return failed == 0

def main():
    """Esegui tutti i test"""
    print("TEST COMPORTAMENTO UMANO STABILE")
    print("=" * 60)
    
    filter_ok = test_post_llm_filter()
    fallback_ok = test_human_fallback()
    
    print("\n" + "=" * 60)
    print("RISULTATO FINALE:")
    print(f"Post-LLM Filter: {'PASS' if filter_ok else 'FAIL'}")
    print(f"Human Fallback: {'PASS' if fallback_ok else 'FAIL'}")
    
    if filter_ok and fallback_ok:
        print("TUTTI I TEST PASSATI - Comportamento umano stabile!")
        return True
    else:
        print("ALCUNI TEST FALLITI")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
