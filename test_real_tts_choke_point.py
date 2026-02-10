#!/usr/bin/env python3
"""
TEST REALI OBBLIGATORI - Verifica finale choke point TTS
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_real_tts_choke_point():
    """Test reali per verificare choke point TTS"""
    print("TEST REALI OBBLIGATORI - CHOKE POINT TTS")
    print("=" * 50)
    
    try:
        from core.surgical_pipeline import surgical_pipeline, sanitize_for_tts
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_real")
        cognitive_state = CognitiveState.build("test_real")
        
        # Test cases obbligatori
        test_cases = [
            {
                "message": "ciao",
                "description": "Chat base con emoji",
                "expect_emoji_display": True,
                "expect_clean_tts": True
            },
            {
                "message": "dimmi il tempo a roma",
                "description": "Meteo con emoji e markdown",
                "expect_emoji_display": True,
                "expect_clean_tts": True
            },
            {
                "message": "dimmi le notizie a bologna",
                "description": "News con markdown",
                "expect_emoji_display": True,
                "expect_clean_tts": True
            }
        ]
        
        all_passed = True
        
        for test_case in test_cases:
            message = test_case["message"]
            description = test_case["description"]
            
            print(f"\nTesting: '{message}' - {description}")
            print("-" * 40)
            
            # 1. Test pipeline completa
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
            
            print(f"Display (UI): {display_text}")
            print(f"TTS (Voice): {tts_text}")
            
            # 2. Test diretto sanitize_for_tts
            print(f"\nTest diretto sanitize_for_tts:")
            test_dirty = f"🌤️ **Roma** 🌤️ 13°C, nubi sparse 💧 Umidità 83% 🌬️ Vento debole"
            sanitized = sanitize_for_tts(test_dirty)
            print(f"Input: {test_dirty}")
            print(f"Output: {sanitized}")
            
            # 3. Verifiche TTS
            has_emoji_tts = any(ord(c) > 127 for c in tts_text)
            has_markdown_tts = any(mark in tts_text for mark in ['**', '__', '##', '*'])
            has_ascii_emoticon_tts = any(emoticon in tts_text for emoticon in [':D', ':)', ':P', ';)'])
            has_english_tts = any(word in tts_text.lower() for word in ['hello', 'hi', 'thanks', 'amazing'])
            
            print(f"\nVerifiche TTS:")
            print(f"  Emoji unicode: {has_emoji_tts}")
            print(f"  Markdown: {has_markdown_tts}")
            print(f"  ASCII emoticon: {has_ascii_emoticon_tts}")
            print(f"  Inglese: {has_english_tts}")
            
            # 4. Verifiche sanitize_for_tts diretto
            has_emoji_sanitized = any(ord(c) > 127 for c in sanitized)
            has_markdown_sanitized = any(mark in sanitized for mark in ['**', '__', '##', '*'])
            
            print(f"\nVerifiche sanitize_for_tts:")
            print(f"  Emoji unicode: {has_emoji_sanitized}")
            print(f"  Markdown: {has_markdown_sanitized}")
            
            # 5. Test critico
            tts_clean = not has_emoji_tts and not has_markdown_tts and not has_ascii_emoticon_tts and not has_english_tts
            sanitize_clean = not has_emoji_sanitized and not has_markdown_sanitized
            
            if tts_clean and sanitize_clean:
                print("SUCCESS: TTS e sanitize_for_tts sono puliti!")
            else:
                print("ISSUE: TTS o sanitize_for_tts contengono elementi non parlabili!")
                all_passed = False
            
            # 6. Verifica display
            if test_case["expect_emoji_display"]:
                has_emoji_display = any(ord(c) > 127 for c in display_text)
                has_markdown_display = any(mark in display_text for mark in ['**', '__', '##', '*'])
                
                print(f"\nVerifiche Display:")
                print(f"  Emoji unicode: {has_emoji_display}")
                print(f"  Markdown: {has_markdown_display}")
                
                if has_emoji_display or has_markdown_display:
                    print("SUCCESS: Display ha elementi visivi come previsto")
                else:
                    print("WARNING: Display senza elementi visivi")
        
        print(f"\nRISULTATO FINALE: {'SUCCESSO COMPLETO' if all_passed else 'FALLITO'}")
        
        if all_passed:
            print("\nTUTTI I TEST REALI SUPERATI!")
            print("Choke point sanitize_for_tts funzionante")
            print("TTS riceve SOLO testo parlabile")
            print("Display mantiene elementi visivi")
            print("Nessuna emoji letta dal TTS")
        
        return all_passed
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_real_tts_choke_point())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
    
    # Se fallisce, esci con codice errore
    if not success:
        sys.exit(1)
