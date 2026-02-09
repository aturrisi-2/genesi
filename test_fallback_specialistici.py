#!/usr/bin/env python3
"""
TEST FALLBACK SPECIALISTICI - Verifica risposte contestuali
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_specialist_fallback():
    """Test fallback specialistici con risposte contestuali"""
    print("TEST FALLBACK SPECIALISTICI")
    print("=" * 50)
    print("VERIFICA: Specialistici falliscono -> risposte contestuali")
    print("=" * 50)
    
    try:
        from core.engines import engine_registry
        
        # Test fallback medico
        print("Test 1: Medical info fallback")
        response = await engine_registry._handle_specialist_fallback(
            intent_type="medical_info",
            message="ho mal di testa",
            params={},
            context={}
        )
        print(f"  Medical: '{response}'")
        
        medical_ok = "professionista" in response or "medico" in response.lower()
        
        # Test fallback psicologico
        print("Test 2: Psychological fallback")
        response = await engine_registry._handle_specialist_fallback(
            intent_type="psychological",
            message="mi sento depresso",
            params={},
            context={}
        )
        print(f"  Psychological: '{response}'")
        
        psychological_ok = "ascoltarti" in response or "sono con te" in response.lower()
        
        # Test fallback meteo
        print("Test 3: Weather fallback")
        response = await engine_registry._handle_specialist_fallback(
            intent_type="weather",
            message="che tempo fa",
            params={},
            context={}
        )
        print(f"  Weather: '{response}'")
        
        weather_ok = "meteo" in response.lower() or "riprovi" in response.lower()
        
        if medical_ok and psychological_ok and weather_ok:
            print("\nPASS: Tutti i fallback specialistici sono contestuali")
            return True
        else:
            print(f"\nFAIL: medical={medical_ok}, psychological={psychological_ok}, weather={weather_ok}")
            return False
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_specialist_fallback())
    sys.exit(0 if success else 1)
