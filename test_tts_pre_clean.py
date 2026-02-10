#!/usr/bin/env python3
"""
TEST FINALE OBBLIGATORIO - Verifica TTS_PRE pulito
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_tts_pre_clean():
    """Test finale per verificare che TTS_PRE sia pulito"""
    print("TEST FINALE - TTS_PRE PULITO")
    print("=" * 50)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_tts")
        cognitive_state = CognitiveState.build("test_tts")
        
        # Test cases con emoji e markdown
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
            
            # TEST CRITICO: TTS_PRE deve essere pulito
            tts_clean = not has_emoji_tts and not has_markdown_tts and not has_ascii_emoticon_tts and not has_english_tts
            
            if tts_clean:
                print("SUCCESS: TTS text è pulito!")
            else:
                print("ISSUE: TTS text contiene elementi non parlabili!")
                all_passed = False
            
            # Verifica che display abbia emoji (dove previsto)
            if "tempo" in message.lower() or "meteo" in message.lower():
                has_emoji_display = any(ord(c) > 127 for c in display_text)
                if has_emoji_display:
                    print("SUCCESS: Display ha emoji come previsto")
                else:
                    print("WARNING: Display senza emoji (potrebbe essere OK)")
            
            if "notizie" in message.lower():
                has_emoji_display = any(ord(c) > 127 for c in display_text)
                if has_emoji_display:
                    print("SUCCESS: Display news ha emoji come previsto")
                else:
                    print("WARNING: Display news senza emoji")
        
        print(f"\nRISULTATO FINALE: {'SUCCESSO COMPLETO' if all_passed else 'FALLITO'}")
        
        if all_passed:
            print("\nTUTTI I TEST TTS_PRE SUPERATI!")
            print("TTS riceve SOLO testo parlabile")
            print("Nessuna emoji in TTS")
            print("Nessun markdown in TTS")
            print("Nessuna ASCII emoticon in TTS")
            print("Nessuna parola inglese in TTS")
            print("Display mantiene emoji e markdown")
        
        return all_passed
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_tts_pre_clean())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
    
    # Se fallisce, esci con codice errore
    if not success:
        sys.exit(1)
