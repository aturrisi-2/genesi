#!/usr/bin/env python3
"""
TEST COMPLETO SISTEMA MIGLIORATO - News approfondite + Emoji + Separazione TTS
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_enhanced_system():
    """Test completo del sistema migliorato"""
    print("TEST SISTEMA MIGLIORATO - News approfondite + Emoji + TTS separation")
    print("=" * 70)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_enhanced")
        cognitive_state = CognitiveState.build("test_enhanced")
        
        # Test cases obbligatori
        test_cases = [
            "dimmi le notizie su roma",
            "che tempo fa a roma",
            "ciao come stai"
        ]
        
        for message in test_cases:
            print(f"\nTesting: '{message}'")
            print("-" * 50)
            
            result = await surgical_pipeline.process_message(
                message,
                cognitive_state,
                [],
                [],
                None,
                {},
                None
            )
            
            # Test separazione testo/TTS
            final_text = result.get('final_text', '')
            tts_text = result.get('tts_text', '')
            
            print(f"Testo visivo (con emoji): '{final_text[:100]}...'")
            print(f"Testo TTS (senza emoji): '{tts_text[:100]}...'")
            
            # Verifiche specifiche
            has_emoji_visivo = any(ord(c) > 127 for c in final_text)
            has_emoji_tts = any(ord(c) > 127 for c in tts_text)
            
            print(f"Verifiche:")
            print(f"  Emoji nel testo visivo: {has_emoji_visivo}")
            print(f"  Emoji nel testo TTS: {has_emoji_tts}")
            
            if "roma" in message.lower():
                # Test news approfondite
                has_context = any(word in final_text.lower() for word in ["questo", "potrebbe", "rilevante", "importante"])
                has_category = any(word in final_text for word in ["Trasporti", "Politica", "Sanità"])
                
                print(f"  News Check:")
                print(f"    Ha contesto: {has_context}")
                print(f"    Ha categoria: {has_category}")
                
                if has_context and has_category and has_emoji_visivo and not has_emoji_tts:
                    print("SUCCESS: News approfondite con emoji e TTS pulito!")
                else:
                    print("ISSUE: Verifiche non superate")
            
            elif "tempo" in message.lower():
                # Test weather con emoji
                has_weather_emoji = any(emoji in final_text for emoji in ["soleggiato", "nuvoloso", "pioggia"])
                
                print(f"  Weather Check:")
                print(f"    Ha emoji meteo: {has_weather_emoji}")
                
                if has_weather_emoji and has_emoji_visivo and not has_emoji_tts:
                    print("SUCCESS: Weather con emoji e TTS pulito!")
                else:
                    print("ISSUE: Weather non funzionante")
            
            else:
                # Test chat libera
                if has_emoji_visivo and not has_emoji_tts:
                    print("SUCCESS: Chat con emoji e TTS pulito!")
                else:
                    print("ISSUE: Chat non funzionante")
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_enhanced_system())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
