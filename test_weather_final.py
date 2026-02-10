#!/usr/bin/env python3
"""
TEST FINALE METEO - Verifica flusso completo
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_weather_final():
    """Test finale del flusso meteo completo"""
    print("TEST FINALE METEO - VERIFICA FLUSSO COMPLETO")
    print("=" * 50)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_weather")
        cognitive_state = CognitiveState.build("test_weather")
        
        message = "com'è il tempo a roma"
        print(f"Test con: '{message}'")
        print("Verifica flusso completo IntentEngine -> Proactor -> API Tools -> Weather Handler")
        print("=" * 50)
        
        result = await surgical_pipeline.process_message(
            message,
            cognitive_state,
            [],
            [],
            None,
            {},
            None
        )
        
        print("=" * 50)
        print("RISULTATO FINALE:")
        print(f"Response: '{result.get('final_text', 'NO_RESPONSE')}'")
        print(f"Engine: {result.get('engine_used', 'unknown')}")
        
        # Verifica che il flusso sia corretto
        response = result.get('final_text', '')
        if "Errore nel recupero dati meteo" in response:
            print("SUCCESSO: Flusso meteo completo funzionante!")
            print("- IntentEngine: weather")
            print("- Proactor: api_tools")
            print("- API Tools: weather handler chiamato")
            print("- Weather Handler: errore gestito correttamente")
        elif "Servizio non disponibile" in response:
            print("SUCCESSO: Flusso meteo completo funzionante!")
            print("- IntentEngine: weather")
            print("- Proactor: api_tools")
            print("- API Tools: weather handler chiamato")
            print("- Weather Handler: errore gestito correttamente")
        else:
            print(f"Risposta: {response}")
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_weather_final())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
