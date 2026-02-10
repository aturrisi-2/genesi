#!/usr/bin/env python3
"""
TEST VELOCE - Chat_free completamente libera
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_free_chat():
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_free")
        cognitive_state = CognitiveState.build("test_free")
        
        print("Test chat_free completamente libera:")
        print("-" * 30)
        
        result = await surgical_pipeline.process_message(
            "ciao, come stai oggi?",
            cognitive_state,
            [],
            [],
            None,
            {},
            None
        )
        
        display = result.get('display_text', '')
        print(f"Risposta: {display}")
        
        return len(display) > 10
        
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_free_chat())
    print(f"Test: {'OK' if success else 'FAIL'}")
