#!/usr/bin/env python3
"""
TEST POST-PROCESSOR LINGUISTICO
Verifica che il metatesto teatrale venga rimosso correttamente
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.text_post_processor import text_post_processor

def test_post_processor():
    """Testa tutti i casi di pulizia del metatesto"""
    
    test_cases = [
        # Caso base: azioni tra asterischi
        {
            "input": "Ciao! *adjusts sunglasses* Come va?",
            "expected": "Ciao! Come va?",
            "description": "Azioni tra asterischi"
        },
        
        # Tono affettuoso
        {
            "input": "*adotta un tono affettuoso* Sono felice di sentirti",
            "expected": "Sono felice di sentirti",
            "description": "Tono affettuoso"
        },
        
        # Azioni complesse
        {
            "input": "*si siede sulla sedia* Bene, grazie. *sorride* E tu?",
            "expected": "Bene, grazie. E tu?",
            "description": "Multiple azioni"
        },
        
        # Descrizioni in parentesi
        {
            "input": "(sussurando) Non lo dire a nessuno... *guarda intorno*",
            "expected": "Non lo dire a nessuno.",
            "description": "Azioni in parentesi"
        },
        
        # Punteggiatura multipla
        {
            "input": "Fantastico!!! Ma anche difficile...",
            "expected": "Fantastico! Ma anche difficile.",
            "description": "Punteggiatura multipla"
        },
        
        # Testo normale (non deve cambiare)
        {
            "input": "Ciao, come stai oggi? Spero bene.",
            "expected": "Ciao, come stai oggi? Spero bene.",
            "description": "Testo normale"
        },
        
        # Caso complesso: tutto insieme
        {
            "input": "*si avvicina* Ciao! Come va? *si siede* Tutto ok?",
            "expected": "Ciao! Come va? Tutto ok?",
            "description": "Tutto insieme"
        }
    ]
    
    print("TEST POST-PROCESSOR LINGUISTICO")
    print("=" * 50)
    
    passed = 0
    failed = 0
    
    for i, test in enumerate(test_cases, 1):
        input_text = test["input"]
        expected = test["expected"]
        description = test["description"]
        
        # Applica post-processor
        result = text_post_processor.clean_response(input_text)
        
        # Verifica
        success = result == expected
        if success:
            passed += 1
            status = "PASS"
        else:
            failed += 1
            status = "FAIL"
        
        print(f"\nTest {i}: {description}")
        print(f"Status: {status}")
        print(f"Input:    '{input_text}'")
        print(f"Expected: '{expected}'")
        print(f"Got:      '{result}'")
        
        if not success:
            print(f"ERRORE: Output non corrispondente!")
    
    print("\n" + "=" * 50)
    print(f"RISULTATI: {passed} passati, {failed} falliti")
    
    if failed == 0:
        print("TUTTI I TEST PASSATI!")
        return True
    else:
        print(f"{failed} TEST FALLITI!")
        return False

if __name__ == "__main__":
    success = test_post_processor()
    sys.exit(0 if success else 1)
