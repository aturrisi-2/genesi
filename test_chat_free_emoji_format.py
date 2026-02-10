#!/usr/bin/env python3
"""
TEST DI VALIDAZIONE - Chat_free formato emoji
Verifica che solo emoji Unicode reali siano usate
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_chat_free_emoji_format():
    """Test validazione formato emoji chat_free"""
    print("TEST DI VALIDAZIONE - CHAT_FREE FORMATO EMOJI")
    print("=" * 50)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_emoji_format")
        cognitive_state = CognitiveState.build("test_emoji_format")
        
        # Test cases
        test_cases = [
            {
                "message": "Ciao",
                "description": "Test base - deve usare emoji Unicode o testo pulito"
            },
            {
                "message": "Come stai?",
                "description": "Test conversazione - controllo formato"
            },
            {
                "message": "Che bel giorno!",
                "description": "Test positività - emoji appropriate"
            }
        ]
        
        all_passed = True
        
        for test_case in test_cases:
            message = test_case["message"]
            description = test_case["description"]
            
            print(f"\nTesting: '{message}' - {description}")
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
            
            print(f"Display: {display_text}")
            print(f"TTS: {tts_text}")
            
            # Verifiche CRITICHE per formato
            has_descriptions = any(pattern in display_text.lower() for pattern in [
                '*grinning face*', '*winking face*', '*ride*', '*smile*',
                ':smile:', ':wink:', ':laugh:',
                '(sorride)', '(ride)', '[sorride]',
                '*sorride*', '*ride*'
            ])
            
            has_emoji_unicode = any(emoji in display_text for emoji in ['😊', '😄', '😉', '🙃', '😎', '🤔'])
            
            print(f"Verifiche formato:")
            print(f"  Descrizioni testuali: {has_descriptions}")
            print(f"  Emoji Unicode: {has_emoji_unicode}")
            
            # Test critico
            if has_descriptions:
                print("❌ CONTIENE DESCRIZIONI TESTUALI - BUG!")
                all_passed = False
            else:
                print("✅ Nessuna descrizione testuale")
            
            if has_emoji_unicode or not has_descriptions:
                print("✅ Formato corretto")
            else:
                print("⚠️ Formato accettabile (testo pulito)")
            
            # Verifica TTS pulito (sempre)
            has_emoji_tts = any(ord(c) > 127 for c in tts_text)
            has_markdown_tts = any(mark in tts_text for mark in ['**', '__', '##', '*'])
            
            if not has_emoji_tts and not has_markdown_tts:
                print("✅ TTS pulito")
            else:
                print("❌ TTS contiene elementi non parlabili")
                all_passed = False
        
        print(f"\nRISULTATO FINALE: {'SUCCESSO COMPLETO' if all_passed else 'FALLITO'}")
        
        if all_passed:
            print("\nTUTTI I TEST SUPERATI!")
            print("Chat_free usa solo emoji Unicode reali")
            print("Nessuna descrizione testuale di emoji")
            print("TTS sempre pulito")
        else:
            print("\nBUG RILEVATO:")
            print("Descrizioni testuali di emoji presenti")
            print("Correggere prompt o post-processing")
        
        return all_passed
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_chat_free_emoji_format())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
    
    # Se fallisce, esci con codice errore
    if not success:
        sys.exit(1)
