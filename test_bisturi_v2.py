#!/usr/bin/env python3
"""
TEST DI VERITÀ FINALE - Prompt Bisturi V2
Verifica risposta presente, non narrativa
"""

import sys
import os
import asyncio
import time
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_bisturi_v2():
    """Test definitivo bisturi v2"""
    
    print("TEST DI VERITÀ - PROMPT BISTURI V2")
    print("=" * 40)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_bisturi")
        cognitive_state = CognitiveState.build("test_bisturi")
        
        print("\nTest: 'Ciao'")
        print("-" * 15)
        print("Output CORRETTO atteso:")
        print("- 'Ciao. Piacere di sentirti.'")
        print("- 'Ciao, sono qui.'")
        print("\nOutput NON accettabile:")
        print("- parlare di sport")
        print("- parlare di ieri")
        print("- 'adoro fare...'")
        print("- storie, esempi, autobiografia")
        print("-" * 15)
        
        start_time = time.time()
        
        result = await surgical_pipeline.process_message(
            "Ciao",
            cognitive_state,
            [],
            [],
            None,
            {},
            None
        )
        
        end_time = time.time()
        latency = (end_time - start_time) * 1000
        
        display_text = result.get('display_text', '')
        print(f"\nRisposta: '{display_text}'")
        print(f"Latency: {latency:.0f}ms")
        
        # Verifiche critiche
        issues = []
        
        # 1. Timing - deve essere veloce
        if latency > 10000:  # più di 10 secondi
            issues.append("TROPPO LENTA - sta pensando troppo")
        
        # 2. Lunghezza - deve essere breve
        if len(display_text.split()) > 15:
            issues.append("TROPPO LUNGA - sta narrando")
        
        # 3. Contenuto - deve essere presente
        forbidden_patterns = [
            'parlare di', 'ieri', 'sport', 'adoro', 'amo',
            'esempio', 'storia', 'ricordo', 'solitamente',
            'di solito', 'spesso', 'di solito mi piace'
        ]
        
        for pattern in forbidden_patterns:
            if pattern.lower() in display_text.lower():
                issues.append(f"NARRATIVA: {pattern}")
        
        # 4. Risposta diretta
        if 'ciao' not in display_text.lower() and len(display_text) > 30:
            issues.append("NON DIRETTA - sta cambiando argomento")
        
        print(f"\nVERIFICA FINALE:")
        if not issues:
            print("✅ RISPOSTA PRESENTE")
            print("✅ VELOCE (< 10s)")
            print("✅ BREVE (1-2 frasi)")
            print("✅ DIRETTA (no narrazione)")
            return True
        else:
            print("❌ PROBLEMI:")
            for issue in issues:
                print(f"   - {issue}")
            return False
            
    except Exception as e:
        print(f"❌ Errore: {e}")
        return False

if __name__ == "__main__":
    success = asyncio.run(test_bisturi_v2())
    print(f"\nRISULTATO FINALE: {'SUCCESSO' if success else 'FALLIMENTO'}")
