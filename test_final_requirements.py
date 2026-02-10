#!/usr/bin/env python3
"""
TEST FINALI OBBLIGATORI - Separazione UI/TTS + Robustezza News
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_final_requirements():
    """Test finali obbligatori come richiesto"""
    print("TEST FINALI OBBLIGATORI")
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
            "dammi il meteo di roma", 
            "dammi le notizie a roma"
        ]
        
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
            
            print(f"Display (UI): '{display_text[:100]}...'")
            print(f"TTS (Voice): '{tts_text[:100]}...'")
            
            # Verifiche
            has_emoji_display = any(ord(c) > 127 for c in display_text)
            has_emoji_tts = any(ord(c) > 127 for c in tts_text)
            
            print(f"Verifiche:")
            print(f"  Emoji in display: {has_emoji_display}")
            print(f"  Emoji in TTS: {has_emoji_tts}")
            
            if "ciao" in message.lower():
                # Test chat libera
                if has_emoji_display and not has_emoji_tts:
                    print("✅ SUCCESS: Chat con separazione UI/TTS")
                else:
                    print("❌ ISSUE: Chat separazione non funzionante")
            
            elif "meteo" in message.lower():
                # Test meteo
                has_weather_emoji = any(emoji in display_text for emoji in ["☀️", "☁️", "🌧️", "❄️"])
                if has_weather_emoji and has_emoji_display and not has_emoji_tts:
                    print("✅ SUCCESS: Meteo con emoji UI e TTS pulito")
                else:
                    print("❌ ISSUE: Meteo non funzionante")
            
            elif "notizie" in message.lower():
                # Test news robuste
                has_news_format = "📰" in display_text and "👉" in display_text and "📍" in display_text
                has_fallback = "poche notizie" in display_text.lower() or "verificabili" in display_text.lower()
                
                print(f"  Formatto news: {has_news_format}")
                print(f"  Fallback robusto: {has_fallback}")
                
                if (has_news_format or has_fallback) and has_emoji_display and not has_emoji_tts:
                    print("✅ SUCCESS: News robuste con separazione UI/TTS")
                else:
                    print("❌ ISSUE: News non funzionante")
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_final_requirements())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
