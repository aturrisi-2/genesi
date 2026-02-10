#!/usr/bin/env python3
"""
TEST REALI OBBLIGATORI - Ripristino funzionale rami tecnici
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_technical_branches_restoration():
    """Test reali per verificare ripristino rami tecnici"""
    print("TEST REALI OBBLIGATORI - RIPRISTINO RAMI TECNICI")
    print("=" * 50)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_technical")
        cognitive_state = CognitiveState.build("test_technical")
        
        # Test cases obbligatori
        test_cases = [
            {
                "message": "oggi ho un gran mal di testa",
                "description": "Medical info - deve usare GPT_FULL",
                "expected_intent": "medical_info",
                "expected_engine": "gpt_full",
                "expected_keywords": ["testa", "mal di testa", "dolore", "sintomo"]
            },
            {
                "message": "oggi sono depresso",
                "description": "Psychological support - deve usare PsychologicalEngine",
                "expected_intent": "emotional_support",
                "expected_engine": "psychological",
                "expected_keywords": ["depresso", "sentimenti", "supporto", "capisco"]
            },
            {
                "message": "ciao come stai",
                "description": "Chat free - deve usare Personalplex",
                "expected_intent": "chat_free",
                "expected_engine": "personalplex",
                "expected_keywords": ["ciao", "stai", "come"]
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
            engine_used = result.get('engine_used', '')
            
            print(f"Intent: {intent_type}")
            print(f"Engine: {engine_used}")
            print(f"Display: {display_text}")
            print(f"TTS: {tts_text}")
            
            # Verifiche intent
            if intent_type == test_case["expected_intent"]:
                print("✅ Intent corretto")
            else:
                print(f"❌ Intent errato: atteso {test_case['expected_intent']}, ricevuto {intent_type}")
                all_passed = False
            
            # Verifiche engine (se disponibile)
            if engine_used:
                if engine_used == test_case["expected_engine"]:
                    print("✅ Engine corretto")
                else:
                    print(f"❌ Engine errato: atteso {test_case['expected_engine']}, ricevuto {engine_used}")
                    all_passed = False
            
            # Verifiche keywords
            response_lower = display_text.lower()
            keywords_found = [kw for kw in test_case["expected_keywords"] if kw in response_lower]
            
            if keywords_found:
                print(f"✅ Keywords trovate: {keywords_found}")
            else:
                print(f"❌ Nessuna keyword trovata da: {test_case['expected_keywords']}")
                all_passed = False
            
            # Verifiche TTS pulito
            has_emoji_tts = any(ord(c) > 127 for c in tts_text)
            has_markdown_tts = any(mark in tts_text for mark in ['**', '__', '##', '*'])
            
            if not has_emoji_tts and not has_markdown_tts:
                print("✅ TTS pulito")
            else:
                print("❌ TTS contiene elementi non parlabili")
                all_passed = False
        
        print(f"\nRISULTATO FINALE: {'SUCCESSO COMPLETO' if all_passed else 'FALLITO'}")
        
        if all_passed:
            print("\nTUTTI I TEST REALI SUPERATI!")
            print("Medical info usa GPT_FULL")
            print("Psychological usa PsychologicalEngine")
            print("Chat free usa Personalplex")
            print("TTS è sempre pulito")
            print("Gerarchia intenti rispettata")
        
        return all_passed
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_technical_branches_restoration())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
    
    # Se fallisce, esci con codice errore
    if not success:
        sys.exit(1)
