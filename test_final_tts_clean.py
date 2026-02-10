#!/usr/bin/env python3
"""
TEST FINALE OBBLIGATORIO - Verifica completa separazione canali TTS
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_final_tts_separation():
    """Test finale per verificare separazione completa TTS"""
    print("TEST FINALE - SEPARAZIONE COMPLETA TTS")
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
            "dimmi il tempo a roma", 
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
            
            # Verifiche CRITICHE per TTS
            has_emoji_tts = any(ord(c) > 127 for c in tts_text)
            has_markdown_tts = any(mark in tts_text for mark in ['**', '__', '##', '*'])
            has_ascii_emoticon_tts = any(emoticon in tts_text for emoticon in [':D', ':)', ':P', ';)'])
            has_english_tts = any(word in tts_text.lower() for word in ['hello', 'hi', 'thanks', 'amazing'])
            
            print(f"Verifiche TTS:")
            print(f"  Emoji unicode in TTS: {has_emoji_tts}")
            print(f"  Markdown in TTS: {has_markdown_tts}")
            print(f"  ASCII emoticon in TTS: {has_ascii_emoticon_tts}")
            print(f"  Inglese in TTS: {has_english_tts}")
            
            # TEST CRITICO: TTS deve essere pulito
            tts_clean = not has_emoji_tts and not has_markdown_tts and not has_ascii_emoticon_tts and not has_english_tts
            
            if tts_clean:
                print("SUCCESS: TTS text è pulito!")
            else:
                print("ISSUE: TTS text contiene elementi non parlabili!")
                all_passed = False
            
            # Verifica che display abbia elementi visivi (dove previsto)
            if "tempo" in message.lower() or "meteo" in message.lower():
                has_emoji_display = any(ord(c) > 127 for c in display_text)
                has_markdown_display = any(mark in display_text for mark in ['**', '__', '##', '*'])
                
                print(f"Verifiche Display:")
                print(f"  Emoji unicode in Display: {has_emoji_display}")
                print(f"  Markdown in Display: {has_markdown_display}")
                
                if has_emoji_display or has_markdown_display:
                    print("SUCCESS: Display ha elementi visivi come previsto")
                else:
                    print("WARNING: Display senza elementi visivi (potrebbe essere OK)")
            
            if "notizie" in message.lower():
                has_emoji_display = any(ord(c) > 127 for c in display_text)
                has_markdown_display = any(mark in display_text for mark in ['**', '__', '##', '*'])
                
                print(f"Verifiche Display News:")
                print(f"  Emoji unicode in Display: {has_emoji_display}")
                print(f"  Markdown in Display: {has_markdown_display}")
                
                if has_emoji_display or has_markdown_display:
                    print("SUCCESS: Display news ha elementi visivi come previsto")
                else:
                    print("WARNING: Display news senza elementi visivi")
        
        print(f"\nRISULTATO FINALE: {'SUCCESSO COMPLETO' if all_passed else 'FALLITO'}")
        
        if all_passed:
            print("\nTUTTI I TEST DI SEPARAZIONE SUPERATI!")
            print("TTS riceve SOLO testo parlabile")
            print("Nessuna emoji in TTS")
            print("Nessun markdown in TTS")
            print("Nessuna ASCII emoticon in TTS")
            print("Nessuna parola inglese in TTS")
            print("Display mantiene elementi visivi")
        
        return all_passed
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_final_tts_separation())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
    
    # Se fallisce, esci con codice errore
    if not success:
        sys.exit(1)
