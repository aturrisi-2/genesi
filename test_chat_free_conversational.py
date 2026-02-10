#!/usr/bin/env python3
"""
TEST OBBLIGATORI - Ricalibrazione chat_free conversazionale
Verifica che chat_free sia naturale, non da assistente
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_chat_free_conversational():
    """Test obbligatori per ricalibrazione conversazionale"""
    print("TEST OBBLIGATORI - RICALIBRAZIONE CHAT_FREE CONVERSAZIONALE")
    print("=" * 60)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_conversational")
        cognitive_state = CognitiveState.build("test_conversational")
        
        # Test cases obbligatori
        test_cases = [
            {
                "message": "ciao",
                "description": "Saluto base - deve essere naturale, non da assistente",
                "forbidden_phrases": ["Come posso aiutarti", "Dimmi pure", "In cosa posso esserti utile"]
            },
            {
                "message": "io bene tu come stai",
                "description": "Risposta personale - deve essere coerente, non automatica",
                "forbidden_phrases": ["Come posso aiutarti", "Sono qui per aiutarti", "Posso aiutarti"]
            },
            {
                "message": "oggi è stata una giornata particolare",
                "description": "Racconto personale - deve rimanere nel contesto",
                "forbidden_phrases": ["Come posso aiutarti", "Cerchiamo di trovare", "Sono qui per"]
            },
            {
                "message": "bene",
                "description": "Risposta breve - NON deve chiudere la conversazione",
                "forbidden_phrases": ["Come posso aiutarti", "C'è altro", "Posso fare altro"]
            }
        ]
        
        all_passed = True
        
        for test_case in test_cases:
            message = test_case["message"]
            description = test_case["description"]
            forbidden = test_case["forbidden_phrases"]
            
            print(f"\nTesting: '{message}'")
            print(f"Descrizione: {description}")
            print("-" * 40)
            
            result = await surgical_pipeline.process_message(
                message,
                cognitive_state,
                [],
                [],
                None,
                {},
                None
            )
            
            display_text = result.get('display_text', '')
            tts_text = result.get('tts_text', '')
            intent_type = result.get('intent_type', '')
            
            print(f"Intent: {intent_type}")
            print(f"Display: {display_text}")
            print(f"TTS: {tts_text}")
            
            # Verifiche critiche
            issues = []
            
            # 1. Intent check
            if intent_type != "chat_free":
                issues.append(f"WRONG_INTENT_{intent_type}")
            
            # 2. Frasi da assistente VIETATE
            for phrase in forbidden:
                if phrase.lower() in display_text.lower():
                    issues.append(f"ASSISTENTE_PHRASE: {phrase}")
            
            # 3. Emoji format check
            bad_emoji_formats = [
                "*grinning face*", "*winking face*", "*ride*", "*smile*",
                ":smile:", ":wink:", ":laugh:",
                "(sorride)", "(ride)", "[sorride]"
            ]
            if any(bad in display_text for bad in bad_emoji_formats):
                issues.append("BAD_EMOJI_FORMAT")
            
            # 4. TTS clean check
            has_emoji_tts = any(ord(c) > 127 for c in tts_text)
            if has_emoji_tts:
                issues.append("EMOJI_IN_TTS")
            
            # 5. Naturalità check
            if len(display_text.strip()) < 5:
                issues.append("TOO_SHORT")
            
            # 6. Check conversazione continua
            if message == "bene":
                closing_phrases = ["C'è altro", "Posso fare altro", "Se hai bisogno"]
                if any(phrase in display_text for phrase in closing_phrases):
                    issues.append("CLOSING_CONVERSATION")
            
            if issues:
                print(f"❌ ISSUES: {', '.join(issues)}")
                all_passed = False
            else:
                print("✅ NATURALE E CONVERSAZIONALE")
        
        print(f"\nRISULTATO FINALE: {'SUCCESSO COMPLETO' if all_passed else 'FALLITO'}")
        
        if all_passed:
            print("\nTUTTI I TEST OBBLIGATORI SUPERATI!")
            print("Chat_free è ora naturale e conversazionale")
            print("Nessuna frase da assistente")
            print("Conversazione fluida e coerente")
            print("Emoji formato corretto")
            print("TTS pulito")
        else:
            print("\nBUG RILEVATI:")
            print("Chat_free ancora troppo orientata al servizio")
            print("Frasi da assistente presenti")
            print("Conversazione non naturale")
        
        return all_passed
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_chat_free_conversational())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
    
    # Se fallisce, esci con codice errore
    if not success:
        sys.exit(1)
