#!/usr/bin/env python3
"""
TEST FIX NUMERI METEO - TTS FRIENDLY
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_weather_tts_friendly():
    """Test del fix numeri meteo per TTS friendly"""
    print("TEST FIX NUMERI METEO - TTS FRIENDLY")
    print("=" * 50)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_weather")
        cognitive_state = CognitiveState.build("test_weather")
        
        # Test cases
        test_cases = [
            "che tempo fa a roma",
            "che tempo fa a bologna"
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
            
            # Verifica TTS friendly
            has_decimals = '.' in response and any(c.isdigit() for c in response.split('.'))
            has_percent = 'per cento' in response or '%' in response
            has_wind_desc = any(word in response for word in ['debole', 'moderato', 'forte', 'molto forte'])
            
            print(f"TTS Check:")
            print(f"  No decimals: {not has_decimals}")
            print(f"  Has percent: {has_percent}")
            print(f"  Has wind desc: {has_wind_desc}")
            
            if not has_decimals and (has_percent or 'gradi' in response):
                print("✅ SUCCESS: TTS friendly response")
            else:
                print("❌ ISSUE: Response not TTS friendly")
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_weather_tts_friendly())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
