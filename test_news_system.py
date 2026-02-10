#!/usr/bin/env python3
"""
TEST SISTEMA NEWS - Verifica integrazione API reale
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_news_system():
    """Test completo del sistema news"""
    print("TEST SISTEMA NEWS - INTEGRAZIONE API REALE")
    print("=" * 50)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_news")
        cognitive_state = CognitiveState.build("test_news")
        
        # Test cases
        test_cases = [
            "dimmi le notizie su roma",
            "dimmi le notizie su milano",
            "dimmi le notizie di oggi"
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
            
            response = result.get('final_text', '')
            print(f"Response: '{response}'")
            
            # Verifiche
            has_real_content = len(response) > 20 and "Non disponibili" not in response
            has_no_dates = not any(char.isdigit() and char in "0123456789" for char in response if char.isdigit())
            is_tts_friendly = not any(char in "[]{}()\"':;" for char in response)
            
            print(f"News Check:")
            print(f"  Real content: {has_real_content}")
            print(f"  No dates: {has_no_dates}")
            print(f"  TTS friendly: {is_tts_friendly}")
            
            if has_real_content and is_tts_friendly:
                print("✅ SUCCESS: News funzionante")
            else:
                print("⚠️  ISSUE: News non funzionante")
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_news_system())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
