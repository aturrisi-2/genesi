#!/usr/bin/env python3
"""
TEST COMPLETO PATTERNS METEO
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_weather_patterns():
    user = User(user_id='test')
    cognitive_state = CognitiveState.build('test')
    
    patterns = [
        'che tempo fa oggi',
        'meteo milano', 
        'piove a torino?'
    ]
    
    for pattern in patterns:
        print(f'Testing: {pattern}')
        result = await surgical_pipeline.process_message(
            pattern, cognitive_state, [], [], None, {}, None
        )
        response = result.get('final_text', 'NO_RESPONSE')
        print(f'Response: {response[:50]}...')
        print()

if __name__ == "__main__":
    from core.surgical_pipeline import surgical_pipeline
    from core.state import CognitiveState
    from storage.users import User
    
    asyncio.run(test_weather_patterns())
