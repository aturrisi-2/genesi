#!/usr/bin/env python3
"""
TEST DEBUG METEO - Solo log per capire il flusso
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_meteo_debug():
    """Test con log debug per meteo"""
    print("TEST DEBUG METEO - com'è il tempo a roma")
    print("=" * 50)
    print("ATTENZIONE: Questo test stampera TUTTI i log di debug")
    print("=" * 50)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        # Simula richiesta utente
        user = User(user_id="test_debug")
        cognitive_state = CognitiveState.build("test_debug")
        
        # Messaggio di test per meteo
        message = "com'è il tempo a roma"
        
        print(f"\nMESSAGGIO DI TEST: '{message}'")
        print("=" * 50)
        print("AVVIO PIPELINE CON LOG DEBUG...")
        print("=" * 50)
        
        # Esegui pipeline completa
        result = await surgical_pipeline.process_message(
            user_message=message,
            cognitive_state=cognitive_state,
            recent_memories=[],
            relevant_memories=[],
            tone=None,
            intent={},  # Vuoto per forzare classificazione
            document_context=None
        )
        
        print("=" * 50)
        print("RISULTATO PIPELINE:")
        print(f"Response: '{result.get('final_text', 'NO_RESPONSE')}'")
        print(f"Engine: {result.get('engine_used', 'unknown')}")
        print("=" * 50)
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_meteo_debug())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
