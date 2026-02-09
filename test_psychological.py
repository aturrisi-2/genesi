#!/usr/bin/env python3
"""
TEST PSICOLOGICO - Verifica routing depressione
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_psychological():
    """Test routing psicologico"""
    print("TEST PSICOLOGICO - DEPRESSIONE")
    print("-" * 40)
    
    try:
        from core.proactor import proactor
        
        # Test depressione → psychological
        decision = proactor.decide_engine("chat_free", "oggi mi sento depresso")
        print(f"depresso -> {decision['engine'].value} (expected: psychological)")
        
        # Verifica
        if decision['engine'].value == "psychological":
            print("PASS: Psicologico routing corretto")
            return True
        else:
            print("FAIL: Psicologico routing errato")
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_psychological())
    sys.exit(0 if success else 1)
