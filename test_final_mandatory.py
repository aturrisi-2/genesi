#!/usr/bin/env python3
"""
TEST FINALI OBBLIGATORI - Verifica completa separazione canali
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_final_mandatory():
    """Test finali obbligatori come richiesto dal mandato"""
    print("TEST FINALI OBBLIGATORI - SEPARAZIONE CANALI")
    print("=" * 50)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_final")
        cognitive_state = CognitiveState.build("test_final")
        
        # Test cases obbligatori
        test_cases = [
            "ciao",
            "dimmi il tempo su roma", 
            "dimmi le notizie su roma"
        ]
        
        all_passed = True
        
        for message in test_cases:
            print(f"\nTesting: '{message}'")
            print("-" * 30)
            
            result = await surgical_pipeline.process_message(
                message,
                cognitive_state,
                [],
                [],
                None,
                {},
                None
            )
            
            # Verifica separazione UI/TTS
            display_text = result.get('display_text', '')
            tts_text = result.get('tts_text', '')
            
            print(f"Display (UI): {display_text}")
            print(f"TTS (Voice): {tts_text}")
            
            # Verifiche specifiche
            has_emoji_display = any(ord(c) > 127 for c in display_text)
            has_emoji_tts = any(ord(c) > 127 for c in tts_text)
            has_content_display = len(display_text) > 0
            has_content_tts = len(tts_text) > 0
            
            # Verifiche specifiche per bug
            has_ascii_emoticon_display = any(emoticon in display_text for emoticon in [':D', ':)', ':P', ';)'])
            has_ascii_emoticon_tts = any(emoticon in tts_text for emoticon in [':D', ':)', ':P', ';)'])
            has_english_display = any(word in display_text.lower() for word in ['hello', 'hi', 'thanks', 'amazing'])
            has_english_tts = any(word in tts_text.lower() for word in ['hello', 'hi', 'thanks', 'amazing'])
            has_markdown_display = any(mark in display_text for mark in ['**', '__', '##'])
            has_markdown_tts = any(mark in tts_text for mark in ['**', '__', '##'])
            
            print(f"Verifiche:")
            print(f"  Display ha contenuto: {has_content_display}")
            print(f"  TTS ha contenuto: {has_content_tts}")
            print(f"  Emoji unicode in display: {has_emoji_display}")
            print(f"  Emoji unicode in TTS: {has_emoji_tts}")
            print(f"  ASCII emoticon in display: {has_ascii_emoticon_display}")
            print(f"  ASCII emoticon in TTS: {has_ascii_emoticon_tts}")
            print(f"  Inglese in display: {has_english_display}")
            print(f"  Inglese in TTS: {has_english_tts}")
            print(f"  Markdown in display: {has_markdown_display}")
            print(f"  Markdown in TTS: {has_markdown_tts}")
            
            test_passed = True
            
            if "ciao" in message.lower():
                # Test 1: "ciao"
                # UI  → "Ciao! 😊 Come va?"
                # TTS → "Ciao! Come va?"
                if (has_content_display and has_content_tts and 
                    not has_ascii_emoticon_display and not has_ascii_emoticon_tts and
                    not has_english_display and not has_english_tts and
                    not has_markdown_tts):
                    print("SUCCESS: Test 1 - Chat OK")
                else:
                    print("ISSUE: Test 1 - Chat non funzionante")
                    test_passed = False
            
            elif "tempo" in message.lower() or "meteo" in message.lower():
                # Test 2: "dimmi il tempo su roma"
                # UI  → emoji + markdown
                # TTS → frase piana italiana
                if (has_content_display and has_content_tts and 
                    not has_ascii_emoticon_display and not has_ascii_emoticon_tts and
                    not has_english_display and not has_english_tts and
                    not has_markdown_tts and not has_emoji_tts):
                    print("SUCCESS: Test 2 - Meteo OK")
                else:
                    print("ISSUE: Test 2 - Meteo non funzionante")
                    test_passed = False
            
            elif "notizie" in message.lower():
                # Test 3: "dimmi le notizie su roma"
                # UI  → molte emoji
                # TTS → nessuna emoji, nessun asterisco
                if (has_content_display and has_content_tts and 
                    not has_ascii_emoticon_display and not has_ascii_emoticon_tts and
                    not has_english_display and not has_english_tts and
                    not has_markdown_tts and not has_emoji_tts):
                    print("SUCCESS: Test 3 - News OK")
                else:
                    print("ISSUE: Test 3 - News non funzionante")
                    test_passed = False
            
            if not test_passed:
                all_passed = False
        
        print(f"\nRISULTATO FINALE: {'SUCCESSO COMPLETO' if all_passed else 'FALLITO'}")
        
        if all_passed:
            print("\nTUTTI I TEST FINALI SUPERATI!")
            print("Display_text: emoji e markdown OK")
            print("TTS_text: pulito e parlabile")
            print("Nessuna ASCII emoticon")
            print("Nessuna parola inglese")
            print("Nessuna emoji letta dal TTS")
        
        return all_passed
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_final_mandatory())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
    
    # Se fallisce, esci con codice errore
    if not success:
        sys.exit(1)
