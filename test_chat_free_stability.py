#!/usr/bin/env python3
"""
TEST OBBLIGATORI - Chat_free stabilità
Verifica che chat_free non vada mai in timeout o fallback
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_chat_free_stability():
    """Test obbligatori per stabilità chat_free"""
    print("TEST OBBLIGATORI - CHAT_FREE STABILITÀ")
    print("=" * 50)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_stability")
        cognitive_state = CognitiveState.build("test_stability")
        
        # Test cases obbligatori
        test_cases = [
            "ciao",
            "chi sei",
            "come va oggi",
            "oggi mi sento giù",
            "raccontami qualcosa"
        ]
        
        all_passed = True
        
        for message in test_cases:
            print(f"\nTesting: '{message}'")
            print("-" * 30)
            
            start_time = asyncio.get_event_loop().time()
            
            result = await surgical_pipeline.process_message(
                message,
                cognitive_state,
                [],
                [],
                None,
                {},
                None
            )
            
            end_time = asyncio.get_event_loop().time()
            duration = (end_time - start_time) * 1000
            
            display_text = result.get('display_text', '')
            tts_text = result.get('tts_text', '')
            intent_type = result.get('intent_type', '')
            
            print(f"Intent: {intent_type}")
            print(f"Display: {display_text}")
            print(f"TTS: {tts_text}")
            print(f"Duration: {duration:.0f}ms")
            
            # Verifiche critiche
            issues = []
            
            # 1. Timeout check
            if duration > 30000:  # 30 secondi
                issues.append("TIMEOUT")
            
            # 2. Fallback check
            fallback_phrases = [
                "Cerchiamo di trovare una soluzione insieme",
                "Posso aiutarti in altro modo",
                "Cerchiamo un approccio diverso"
            ]
            if any(phrase in display_text for phrase in fallback_phrases):
                if intent_type == "chat_free":
                    issues.append("FALLBACK_CHAT_FREE")
                else:
                    print("Fallback accettabile per intent non chat_free")
            
            # 3. Empty response check
            if not display_text or len(display_text.strip()) < 3:
                issues.append("EMPTY_RESPONSE")
            
            # 4. Intent check
            if message in ["ciao", "chi sei", "come va oggi", "raccontami qualcosa"]:
                if intent_type != "chat_free":
                    issues.append(f"WRONG_INTENT_{intent_type}")
            
            # 5. Emoji format check
            bad_emoji_formats = [
                "*grinning face*", "*winking face*", "*ride*", "*smile*",
                ":smile:", ":wink:", ":laugh:",
                "(sorride)", "(ride)", "[sorride]"
            ]
            if any(bad in display_text for bad in bad_emoji_formats):
                issues.append("BAD_EMOJI_FORMAT")
            
            # 6. TTS clean check
            has_emoji_tts = any(ord(c) > 127 for c in tts_text)
            if has_emoji_tts:
                issues.append("EMOJI_IN_TTS")
            
            if issues:
                print(f"❌ ISSUES: {', '.join(issues)}")
                all_passed = False
            else:
                print("✅ OK")
        
        print(f"\nRISULTATO FINALE: {'SUCCESSO COMPLETO' if all_passed else 'FALLITO'}")
        
        if all_passed:
            print("\nTUTTI I TEST OBBLIGATORI SUPERATI!")
            print("Chat_free è stabile")
            print("Nessun timeout")
            print("Nessun fallback inappropriato")
            print("Emoji formato corretto")
            print("TTS pulito")
        else:
            print("\nBUG RILEVATI:")
            print("Chat_free instabile o con problemi")
        
        return all_passed
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_chat_free_stability())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
    
    # Se fallisce, esci con codice errore
    if not success:
        sys.exit(1)
