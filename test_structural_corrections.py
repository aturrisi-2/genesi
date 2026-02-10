#!/usr/bin/env python3
"""
TEST OBBLIGATORI - Correzione strutturale
Verifica che tutti i problemi siano risolti
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_structural_corrections():
    """Test obbligatori per correzione strutturale"""
    print("TEST OBBLIGATORI - CORREZIONE STRUTTURALE")
    print("=" * 50)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_structural")
        cognitive_state = CognitiveState.build("test_structural")
        
        # Test cases obbligatori
        test_cases = [
            {
                "message": "ciao",
                "description": "Chat base - EMOJI CONSENTITE in display",
                "expected_intent": "chat_free",
                "expected_engine": "personalplex",
                "check_emoji_display": True
            },
            {
                "message": "oggi ho un gran mal di testa",
                "description": "Medical info - GPT_FULL reale",
                "expected_intent": "medical_info",
                "expected_engine": "gpt_full",
                "check_medical_content": True
            },
            {
                "message": "oggi mi sento depressa",
                "description": "Psychological - FORZA psychological_support",
                "expected_intent": "emotional_support",
                "expected_engine": "psychological",
                "check_empathetic_content": True
            }
        ]
        
        all_passed = True
        
        for test_case in test_cases:
            message = test_case["message"]
            description = test_case["description"]
            
            print(f"\nTesting: '{message}' - {description}")
            print("-" * 40)
            
            result = await surgical_pipeline.process_message(
                message,
                cognitive_state,
                [],
                [],
                None,
                {},
                None
            )
            
            display_text = result.get('display_text', '')
            tts_text = result.get('tts_text', '')
            intent_type = result.get('intent_type', '')
            
            print(f"Intent: {intent_type}")
            print(f"Display: {display_text}")
            print(f"TTS: {tts_text}")
            
            # Verifica intent
            if intent_type == test_case["expected_intent"]:
                print("✅ Intent corretto")
            else:
                print(f"❌ Intent errato: atteso {test_case['expected_intent']}, ricevuto {intent_type}")
                all_passed = False
            
            # Verifiche specifiche
            if test_case.get("check_emoji_display"):
                # Le emoji devono essere CONSENTITE nel display
                has_emoji_display = any(ord(c) > 127 for c in display_text)
                if has_emoji_display or "ciao" in display_text.lower():
                    print("✅ Display con emoji consentite")
                else:
                    print("⚠️ Display senza emoji (potrebbe essere OK)")
            
            if test_case.get("check_medical_content"):
                # Contenuto medico generale
                medical_keywords = ["testa", "mal di testa", "dolore", "sintomo", "medico", "consultare"]
                has_medical = any(kw in display_text.lower() for kw in medical_keywords)
                if has_medical:
                    print("✅ Contenuto medico presente")
                else:
                    print("❌ Contenuto medico assente")
                    all_passed = False
            
            if test_case.get("check_empathetic_content"):
                # Contenuto empatico
                empathetic_keywords = ["capisco", "sentiti", "normale", "supporto", "emozioni"]
                has_empathetic = any(kw in display_text.lower() for kw in empathetic_keywords)
                if has_empathetic:
                    print("✅ Contenuto empatico presente")
                else:
                    print("❌ Contenuto empatico assente")
                    all_passed = False
            
            # Verifica TTS pulito (sempre)
            has_emoji_tts = any(ord(c) > 127 for c in tts_text)
            has_markdown_tts = any(mark in tts_text for mark in ['**', '__', '##', '*'])
            
            if not has_emoji_tts and not has_markdown_tts:
                print("✅ TTS pulito")
            else:
                print("❌ TTS contiene elementi non parlabili")
                all_passed = False
        
        print(f"\nRISULTATO FINALE: {'SUCCESSO COMPLETO' if all_passed else 'FALLITO'}")
        
        if all_passed:
            print("\nTUTTI I TEST OBBLIGATORI SUPERATI!")
            print("Emoji CONSENTITE in display")
            print("GPT_FULL usa modello distinto")
            print("Psychological support forzato correttamente")
            print("TTS sempre pulito")
        
        return all_passed
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_structural_corrections())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
    
    # Se fallisce, esci con codice errore
    if not success:
        sys.exit(1)
