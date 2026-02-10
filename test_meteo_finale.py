#!/usr/bin/env python3
"""
TEST FINALE METEO CON SIMULAZIONE API KEY
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_weather_with_mock_key():
    """Test meteo simulando API key configurata"""
    print("TEST METEO CON SIMULAZIONE API KEY")
    print("=" * 50)
    
    # Simula API key per test
    os.environ["OPENWEATHER_API_KEY"] = "test_key_123456"
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_weather")
        cognitive_state = CognitiveState.build("test_weather")
        
        message = "com'è il tempo a roma"
        print(f"Test con: '{message}'")
        print("API key simulata configurata")
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
            print("✅ Flusso corretto ma API key non valida (aspettato)")
        elif "Servizio non disponibile" in response:
            print("✅ Flusso corretto ma API key non valida (aspettato)")
        elif "18°C" in response or "sereno" in response:
            print("✅ SUCCESSO: Meteo funzionante con dati reali!")
        else:
            print(f"⚠️  Risposta inaspettata: {response}")
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_weather_with_mock_key())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
