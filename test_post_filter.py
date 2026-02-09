#!/usr/bin/env python3
"""
TEST POST-FILTER NON DISTRUTTIVO
Verifica che il filtro pulisca ma non sostituisca
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_post_filter_cleaning():
    """Test pulizia post-filter"""
    print("TEST POST-FILTER NON DISTRUTTIVO")
    print("-" * 50)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        
        # Test 1: Pulizia emoji (simulato senza emoji reali)
        print("Test 1: Pulizia emoji e teatralità")
        contaminated = "Ciao! Come stai? *sorride*"
        cleaned = surgical_pipeline._clean_response_safely(contaminated, ["emoji", "theatricality"])
        print(f"  Originale: '{contaminated}'")
        print(f"  Pulito:    '{cleaned}'")
        print(f"  Expected: 'Ciao! Come stai?'")
        
        if "*sorride*" not in cleaned and "Come stai" in cleaned:
            print("  PASS: Teatralità rimossa, significato preservato")
        else:
            print("  FAIL: Pulizia non funzionante")
            return False
        
        # Test 2: Pulizia caratteri invalidi
        print("\nTest 2: Pulizia caratteri invalidi")
        contaminated = "Ciao @#$ Come stai?"
        cleaned = surgical_pipeline._clean_response_safely(contaminated, ["invalid_chars"])
        print(f"  Originale: '{contaminated}'")
        print(f"  Pulito:    '{cleaned}'")
        print(f"  Expected: 'Ciao Come stai?'")
        
        if "@#$" not in cleaned and "Ciao Come stai" in cleaned:
            print("  PASS: Caratteri invalidi rimossi")
        else:
            print("  FAIL: Pulizia caratteri non funzionante")
            return False
        
        # Test 3: Test vuoto
        print("\nTest 3: Test vuoto")
        cleaned = surgical_pipeline._clean_response_safely("", ["emoji"])
        print(f"  Vuoto: '{cleaned}'")
        
        if cleaned == "":
            print("  PASS: Gestione vuoto corretta")
        else:
            print("  FAIL: Gestione vuoto errata")
            return False
        
        print("\nPOST-FILTER NON DISTRUTTIVO: TUTTI I TEST PASS!")
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_post_filter_cleaning())
    sys.exit(0 if success else 1)
