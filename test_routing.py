#!/usr/bin/env python3
"""
TEST SINGOLO - Verifica routing chirurgico
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_routing():
    """Test routing senza dipendenze esterne"""
    print("TEST ROUTING CHIRURGICO")
    print("-" * 40)
    
    try:
        from core.proactor import proactor
        
        # Test 1: ciao → personalplex
        decision1 = proactor.decide_engine("chat_free", "ciao")
        print(f"ciao -> {decision1['engine'].value} (expected: personalplex)")
        
        # Test 2: meteo → api_tools
        decision2 = proactor.decide_engine("chat_free", "che tempo fa a roma")
        print(f"meteo -> {decision2['engine'].value} (expected: api_tools)")
        
        # Test 3: dns → gpt_full
        decision3 = proactor.decide_engine("chat_free", "cos'è un dns")
        print(f"dns -> {decision3['engine'].value} (expected: gpt_full)")
        
        # Verifiche
        checks = [
            decision1['engine'].value == "personalplex",
            decision2['engine'].value == "api_tools", 
            decision3['engine'].value == "gpt_full"
        ]
        
        if all(checks):
            print("PASS: Routing chirurgico corretto")
            return True
        else:
            print("FAIL: Routing errato")
            return False
            
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_routing())
    sys.exit(0 if success else 1)
