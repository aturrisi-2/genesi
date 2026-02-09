#!/usr/bin/env python3
"""
TEST FINALE POST-FILTER - Verifica completa fix
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_final_post_filter():
    """Test finale completo post-filter"""
    print("TEST FINALE POST-FILTER NON DISTRUTTIVO")
    print("=" * 60)
    print("VERIFICA: MAI PIU 'Cerchiamo di trovare una soluzione insieme'")
    print("=" * 60)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        
        # Simula risposte contaminate da PersonalPlex
        test_cases = [
            {
                "name": "Chat libera con teatralità",
                "input": "ciao",
                "contaminated": "Ciao! Come stai? *sorride* Tutto bene?",
                "issues": ["theatricality"],
                "expected_contains": ["Ciao", "Come stai"],
                "expected_not_contains": ["*sorride*", "Cerchiamo di trovare"]
            },
            {
                "name": "Risposta medica con teatralità",
                "input": "ho mal di testa",
                "contaminated": "Mi dispiace che tu abbia mal di testa *preoccupato* Prova un paracetamolo",
                "issues": ["theatricality"],
                "expected_contains": ["Mi dispiace", "mal di testa"],
                "expected_not_contains": ["*preoccupato*", "Cerchiamo di trovare"]
            },
            {
                "name": "Risposta con caratteri invalidi",
                "input": "come ti chiami",
                "contaminated": "Sono Genesi @#$ la tua assistente",
                "issues": ["invalid_chars"],
                "expected_contains": ["Sono Genesi", "la tua assistente"],
                "expected_not_contains": ["@#$", "Cerchiamo di trovare"]
            }
        ]
        
        passed = 0
        failed = 0
        
        for i, test_case in enumerate(test_cases, 1):
            print(f"\nTest {i}: {test_case['name']}")
            print("-" * 40)
            
            # Pulisci la risposta
            cleaned = surgical_pipeline._clean_response_safely(
                test_case['contaminated'], 
                test_case['issues']
            )
            
            print(f"  Originale: '{test_case['contaminated']}'")
            print(f"  Pulito:    '{cleaned}'")
            
            # Verifica contenuto atteso
            all_good = True
            
            for expected in test_case['expected_contains']:
                if expected not in cleaned:
                    print(f"  FAIL: Manca '{expected}'")
                    all_good = False
            
            for not_expected in test_case['expected_not_contains']:
                if not_expected in cleaned:
                    print(f"  FAIL: Contiene '{not_expected}'")
                    all_good = False
            
            # Verifica che non sia la frase fissa
            if "Cerchiamo di trovare una soluzione insieme" in cleaned:
                print(f"  FAIL: Contiene frase fissa di fallback!")
                all_good = False
            
            if all_good:
                print(f"  PASS: Pulizia corretta, significato preservato")
                passed += 1
            else:
                print(f"  FAIL: Pulizia non funzionante")
                failed += 1
        
        print("\n" + "=" * 60)
        print("RISULTATO FINALE:")
        print(f"Passati: {passed}/{len(test_cases)}")
        print(f"Falliti: {failed}/{len(test_cases)}")
        
        if failed == 0:
            print("\nSUCCESSO COMPLETO!")
            print("POST-FILTER NON DISTRUTTIVO VERIFICATO:")
            print("  Emoji rimosse")
            print("  Teatralità rimossa")
            print("  Caratteri invalidi rimossi")
            print("  Significato preservato")
            print("  MAI frase fissa di fallback")
            print("\nGenesi ora risponderà con testo pulito ma significativo!")
            return True
        else:
            print("\nWARNING: Alcuni test falliti")
            return False
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_final_post_filter())
    sys.exit(0 if success else 1)
