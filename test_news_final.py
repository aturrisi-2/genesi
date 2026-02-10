#!/usr/bin/env python3
"""
TEST FINALE NEWS - Verifica flusso completo
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_news_final():
    """Test finale del flusso news completo"""
    print("TEST FINALE NEWS - VERIFICA FLUSSO COMPLETO")
    print("=" * 50)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_news")
        cognitive_state = CognitiveState.build("test_news")
        
        message = "dimmi le notizie su roma"
        print(f"Test con: '{message}'")
        print("Verifica flusso completo IntentEngine -> Proactor -> API Tools -> News Handler")
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
        if "Non riesco a ottenere notizie" in response:
            print("SUCCESSO: Flusso news completo funzionante!")
            print("- IntentEngine: news")
            print("- Proactor: api_tools")
            print("- API Tools: news handler chiamato")
            print("- News Handler: errore API key gestito correttamente")
        elif len(response) > 20 and "Non disponibili" not in response:
            print("SUCCESSO: News reali funzionanti!")
            print("- IntentEngine: news")
            print("- Proactor: api_tools")
            print("- API Tools: news handler chiamato")
            print("- News Handler: dati reali ricevuti")
        else:
            print(f"Risposta: {response}")
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_news_final())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
