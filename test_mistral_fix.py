#!/usr/bin/env python3
"""
TEST VERIFICA IMMEDIATA - Fix prompt Mistral
Verifica scomparsa *smile*, *giggle*, inglese
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_mistral_fix():
    """Test immediato fix prompt"""
    
    print("TEST VERIFICA FIX PROMPT MISTRAL")
    print("=" * 40)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_fix")
        cognitive_state = CognitiveState.build("test_fix")
        
        print("\n1. Test: 'ciao come stai?'")
        print("-" * 30)
        
        result = await surgical_pipeline.process_message(
            "ciao come stai?",
            cognitive_state,
            [],
            [],
            None,
            {},
            None
        )
        
        display_text = result.get('display_text', '')
        print(f"Risposta: '{display_text}'")
        
        # Verifiche critiche
        issues = []
        
        # ❌ NON devono più esistere
        forbidden_patterns = ['*smile*', '*giggle*', 'already', 'I just', 'smile', 'giggle']
        for pattern in forbidden_patterns:
            if pattern.lower() in display_text.lower():
                issues.append(f"TROVATO: {pattern}")
        
        # ✅ DEVE essere italiano puro
        english_words = ['already', 'just', 'smile', 'giggle', 'love', 'like', 'really']
        for word in english_words:
            if word.lower() in display_text.lower():
                issues.append(f"INGLESE: {word}")
        
        # ✅ DEVE essere coerente
        if len(display_text.strip()) < 5:
            issues.append("RISPOSTA TROPPO CORTA")
        
        print(f"\nVERIFICA:")
        if not issues:
            print("✅ NESSUN PROBLEMA RILEVATO")
            print("✅ Nessun *smile* o *giggle*")
            print("✅ Nessun inglese")
            print("✅ Risposta coerente")
            return True
        else:
            print("❌ PROBLEMI RILEVATI:")
            for issue in issues:
                print(f"   - {issue}")
            return False
            
    except Exception as e:
        print(f"❌ Errore: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_mistral_fix())
    print(f"\nRISULTATO: {'SUCCESSO' if success else 'FALLIMENTO'}")
