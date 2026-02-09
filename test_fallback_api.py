#!/usr/bin/env python3
"""
TEST FALLBACK CORRETTI - Simula fallimento API tools
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_api_tools_fallback():
    """Test fallback API tools -> GPT-full"""
    print("TEST FALLBACK API TOOLS")
    print("=" * 50)
    print("VERIFICA: API tools fallisce -> GPT-full (NON PersonalPlex)")
    print("=" * 50)
    
    try:
        from core.engines import engine_registry
        
        # Simula API tools che non può gestire weather (fallback)
        print("Simulando API tools che fallisce per weather...")
        
        # Chiamata diretta per testare fallback
        response = await engine_registry.generate_with_engine(
            engine_type="api_tools",
            message="che tempo fa a roma",
            params={"intent_type": "weather"},
            context={"test": True}
        )
        
        print(f"Risposta: '{response}'")
        
        # Verifica che non sia una risposta PersonalPlex
        personalplex_indicators = ["😊", "*sorride*", "ciao!", "hey!", "tesoro"]
        is_personalplex = any(indicator in response.lower() for indicator in personalplex_indicators)
        
        if is_personalplex:
            print("FAIL: La risposta sembra da PersonalPlex!")
            return False
        else:
            print("PASS: La risposta non è da PersonalPlex")
            return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_api_tools_fallback())
    sys.exit(0 if success else 1)
