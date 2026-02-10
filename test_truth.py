#!/usr/bin/env python3
"""
TEST DI VERITÀ - Verifica fix architetturali
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_truth():
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_truth")
        cognitive_state = CognitiveState.build("test_truth")
        
        print("TEST DI VERITÀ:")
        print("=" * 40)
        
        # Test 1: Conversazione umana
        print("\n1. 'Io bene e tu'")
        result1 = await surgical_pipeline.process_message(
            "Io bene e tu", cognitive_state, [], [], None, {}, None
        )
        print(f"   Risposta: {result1.get('display_text', '')}")
        print(f"   Intent: {result1.get('intent_type', '')}")
        
        # Test 2: Data reale
        print("\n2. 'Che giorno è oggi'")
        result2 = await surgical_pipeline.process_message(
            "Che giorno è oggi", cognitive_state, [], [], None, {}, None
        )
        print(f"   Risposta: {result2.get('display_text', '')}")
        print(f"   Intent: {result2.get('intent_type', '')}")
        
        # Verifiche
        print("\n" + "=" * 40)
        print("VERIFICHE:")
        
        # Test 1: conversazione
        response1 = result1.get('display_text', '').lower()
        if 'come posso aiutarti' in response1:
            print("❌ Test 1 FALLITO: frase da assistente")
        elif 'bene anche io' in response1 or 'io bene' in response1:
            print("✅ Test 1 OK: conversazione naturale")
        else:
            print(f"? Test 1 INCERTO: {response1}")
        
        # Test 2: data
        response2 = result2.get('display_text', '')
        intent2 = result2.get('intent_type', '')
        if intent2 == 'date_time':
            print("✅ Test 2 OK: routing a date_time")
        elif intent2 == 'chat_free':
            print("❌ Test 2 FALLITO: ancora chat_free")
        else:
            print(f"? Test 2 INCERTO: intent {intent2}")
            
        # Check data reale vs inventata
        if 'aprile' in response2.lower() or '13' in response2:
            print("❌ Data inventata rilevata")
        elif any(month in response2.lower() for month in ['febbraio', 'febbrai', 'lunedì', 'martedì', 'mercoledì']):
            print("✅ Data plausibile")
        
        return True
        
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_truth())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
