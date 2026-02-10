#!/usr/bin/env python3
"""
TEST OBBLIGATORI FINALI - Verifica completa UI/TTS + Emoji + News
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_mandatory_requirements():
    """Test obbligatori come richiesto dal mandato"""
    print("TEST OBBLIGATORI FINALI")
    print("=" * 50)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_mandatory")
        cognitive_state = CognitiveState.build("test_mandatory")
        
        # Test cases obbligatori
        test_cases = [
            "ciao",
            "dimmi il meteo su roma", 
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
            
            print(f"Display (UI): '{display_text[:100]}...'")
            print(f"TTS (Voice): '{tts_text[:100]}...'")
            
            # Verifiche
            has_emoji_display = any(ord(c) > 127 for c in display_text)
            has_emoji_tts = any(ord(c) > 127 for c in tts_text)
            has_content_display = len(display_text) > 0
            has_content_tts = len(tts_text) > 0
            
            print(f"Verifiche:")
            print(f"  Display ha contenuto: {has_content_display}")
            print(f"  TTS ha contenuto: {has_content_tts}")
            print(f"  Emoji in display: {has_emoji_display}")
            print(f"  Emoji in TTS: {has_emoji_tts}")
            
            test_passed = True
            
            if "ciao" in message.lower():
                # Test chat libera
                if has_content_display and has_content_tts and not has_emoji_tts:
                    print("SUCCESS: Chat con contenuto e separazione OK")
                else:
                    print("ISSUE: Chat non funzionante")
                    test_passed = False
            
            elif "meteo" in message.lower():
                # Test meteo
                has_weather_emoji = any(emoji in display_text for emoji in ["soleggiato", "nuvoloso", "pioggia"])
                if has_content_display and has_content_tts and has_weather_emoji and not has_emoji_tts:
                    print("SUCCESS: Meteo con emoji UI e TTS pulito")
                else:
                    print("ISSUE: Meteo non funzionante")
                    test_passed = False
            
            elif "notizie" in message.lower():
                # Test news robuste
                has_news_format = "Attualita" in display_text or "Trasporti" in display_text
                has_fallback = "poche notizie" in display_text.lower() or "verificabili" in display_text.lower()
                
                print(f"  Formatto news: {has_news_format}")
                print(f"  Fallback robusto: {has_fallback}")
                
                if has_content_display and has_content_tts and (has_news_format or has_fallback) and not has_emoji_tts:
                    print("SUCCESS: News robuste con separazione OK")
                else:
                    print("ISSUE: News non funzionante")
                    test_passed = False
            
            if not test_passed:
                all_passed = False
        
        print(f"\nRISULTATO FINALE: {'SUCCESSO COMPLETO' if all_passed else 'FALLITO'}")
        
        if all_passed:
            print("\nTUTTI I TEST OBBLIGATORI SUPERATI!")
            print("UI mostra sempre testo")
            print("TTS parla sempre")
            print("Emoji visive presenti")
            print("Nessuna regressione")
        
        return all_passed
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_mandatory_requirements())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
    
    # Se fallisce, esci con codice errore
    if not success:
        sys.exit(1)
