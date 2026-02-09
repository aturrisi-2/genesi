#!/usr/bin/env python3
"""
TEST MEDICO - Verifica routing mal di testa
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_medical():
    """Test routing medico"""
    print("TEST MEDICO - MAL DI TESTA")
    print("-" * 40)
    
    try:
        from core.proactor import proactor
        
        # Test mal di testa → gpt_full
        decision = proactor.decide_engine("chat_free", "ho mal di testa")
        print(f"mal di testa -> {decision['engine'].value} (expected: gpt_full)")
        
        # Verifica
        if decision['engine'].value == "gpt_full":
            print("PASS: Medico routing corretto")
            return True
        else:
            print("FAIL: Medico routing errato")
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_medical())
    sys.exit(0 if success else 1)
