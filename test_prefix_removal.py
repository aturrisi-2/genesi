#!/usr/bin/env python3
"""
TEST VALIDAZIONE OBBLIGATORIA - Rimozione prefisso "Risposta:" da chat_free
Verifica bypass totale formatter per chat_free
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_prefix_removal():
    """Test obbligatorio rimozione prefissi chat_free"""
    
    print("TEST VALIDAZIONE OBBLIGATORIA - Rimozione prefisso 'Risposta:'")
    print("=" * 60)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_prefix")
        cognitive_state = CognitiveState.build("test_prefix")
        
        print("\nTest: 'ciao'")
        print("-" * 20)
        print("Output ATTESO:")
        print("- 'Ciao! Come va?'")
        print("- 'Ciao, sono qui.'")
        print("❌ NON ACCETTABILE:")
        print("- 'Risposta: Ciao! Come va?'")
        print("- 'Domanda: Ciao! Come va?'")
        print("- 'Answer: Ciao! Come va?'")
        print("-" * 20)
        
        result = await surgical_pipeline.process_message(
            "ciao",
            cognitive_state,
            [],
            [],
            None,
            {},
            None
        )
        
        display_text = result.get('display_text', '')
        print(f"\nDisplay: '{display_text}'")
        
        # Verifiche critiche
        issues = []
        
        # 1. Controlla prefissi vietati
        forbidden_prefixes = [
            'Risposta:', 'Domanda:', 'Answer:', 'Question:',
            'La risposta è:', 'La domanda è:'
        ]
        
        for prefix in forbidden_prefixes:
            if prefix in display_text:
                issues.append(f"PREFISSO VIETATO: {prefix}")
        
        # 2. Verifica che sia testo nudo (nessuna formattazione)
        if any(char in display_text for char in ['[', ']', '{', '}', '<', '>', '|']):
            issues.append("CARATTERI FORMATTAZIONE")
        
        # 3. Verifica che sia breve e diretto
        if len(display_text.split()) > 15:
            issues.append("TROPPO LUNGO - possibile spiegazione")
        
        # 4. Verifica che non ci sia struttura Q/A
        if any(pattern in display_text for pattern in ['domanda', 'risposta', 'answer', 'question']):
            if pattern.lower() not in display_text.lower():
                issues.append(f"STRUTTURA Q/A: {pattern}")
        
        print(f"\nVERIFICA FINALE:")
        if not issues:
            print("✅ NESSUN PREFISSO VIETATO")
            print("✅ NESSUNA FORMATTAZIONE")
            print("✅ TESTO NUO DAL MODELLO")
            print("✅ BREVE E DIRETTA")
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
    success = asyncio.run(test_prefix_removal())
    print(f"\nRISULTATO FINALE: {'SUCCESSO' if success else 'FALLIMENTO'}")
