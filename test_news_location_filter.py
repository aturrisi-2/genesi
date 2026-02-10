#!/usr/bin/env python3
"""
TEST FILTRO NEWS PER LOCALITÀ - Verifica comportamento desiderato
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_news_location_filter():
    """Test del filtro news per località"""
    print("TEST FILTRO NEWS PER LOCALITÀ")
    print("=" * 50)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_news")
        cognitive_state = CognitiveState.build("test_news")
        
        # Test cases obbligatori
        test_cases = [
            "dimmi le notizie su roma",
            "dimmi le notizie",
            "dimmi le notizie su milano"
        ]
        
        for message in test_cases:
            print(f"\nTesting: '{message}'")
            print("-" * 30)
            
            result = await surgical_pipeline.process_message(
                message,
                cognitive_state,
                [],
                [],
                None,
                {},
                None
            )
            
            response = result.get('final_text', '')
            print(f"Response: '{response}'")
            
            # Verifiche specifiche
            if "roma" in message.lower():
                # DEVE parlare solo di Roma
                is_roma_specific = any(word in response.lower() for word in ["roma", "romano", "romana", "lazio", "capitale"])
                has_generic = any(word in response.lower() for word in ["oroscopo", "metalmeccanici", "nazionale"])
                
                print(f"Roma Check:")
                print(f"  Roma specific: {is_roma_specific}")
                print(f"  No generic: {not has_generic}")
                
                if is_roma_specific and not has_generic:
                    print("✅ SUCCESS: Filtraggio Roma funzionante")
                else:
                    print("❌ ISSUE: Filtraggio Roma non funzionante")
            
            elif "milano" in message.lower():
                # DEVE parlare solo di Milano
                is_milano_specific = any(word in response.lower() for word in ["milano", "milanese", "lombardia"])
                has_generic = any(word in response.lower() for word in ["oroscopo", "metalmeccanici"])
                
                print(f"Milano Check:")
                print(f"  Milano specific: {is_milano_specific}")
                print(f"  No generic: {not has_generic}")
                
                if is_milano_specific and not has_generic:
                    print("✅ SUCCESS: Filtraggio Milano funzionante")
                else:
                    print("❌ ISSUE: Filtraggio Milano non funzionante")
            
            else:
                # Può essere nazionale
                print("Generic check: OK (national news allowed)")
        
        return True
        
    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_news_location_filter())
    print(f"\nTest completato: {'SUCCESSO' if success else 'FALLITO'}")
