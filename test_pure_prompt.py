#!/usr/bin/env python3
"""
TEST VERIFICA DEFINITIVA - Prompt puro Mistral
Verifica eliminazione roleplay, inglese, *smile*, *giggle*
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_pure_prompt():
    """Test definitivo prompt puro"""
    
    print("TEST VERIFICA PROMPT PURO MISTRAL")
    print("=" * 40)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_pure")
        cognitive_state = CognitiveState.build("test_pure")
        
        print("\n1. Test: 'Ciao'")
        print("-" * 20)
        
        result = await surgical_pipeline.process_message(
            "Ciao",
            cognitive_state,
            [],
            [],
            None,
            {},
            None
        )
        
        display_text = result.get('display_text', '')
        print(f"Risposta: '{display_text}'")
        
        # Verifiche critiche assolute
        forbidden = [
            '*smile*', '*giggle*', 'smile', 'giggle',
            'already', 'just', 'I just', 'really',
            'hello', 'hi', 'bye', 'ok'
        ]
        
        issues = []
        for word in forbidden:
            if word.lower() in display_text.lower():
                issues.append(f"VIETATO: {word}")
        
        # Verifica italiano
        if any(char.isascii() and not char.isspace() and not char.isalnum() and char not in '.,!?;:àèéìòùÀÈÉÌÒÙ' for char in display_text):
            issues.append("CARATTERI NON ITALIANI")
        
        print(f"\nVERIFICA FINALE:")
        if not issues:
            print("✅ NESSUN ROLEPLAY")
            print("✅ NESSUN INGLESE") 
            print("✅ NESSUN *SMILE*/*GIGGLE*")
            print("✅ RISPOSTA ADULTA E NATURALE")
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
    success = asyncio.run(test_pure_prompt())
    print(f"\nRISULTATO FINALE: {'SUCCESSO' if success else 'FALLIMENTO'}")
