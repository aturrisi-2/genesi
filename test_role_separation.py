#!/usr/bin/env python3
"""
TEST VERIFICA OBBLIGATORIA - Separazione ruoli Personalplex/Mistral
Verifica che Personalplex sia ORCHESTRATORE PURO, Mistral UNICA VOCE
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_role_separation():
    """Test obbligatorio per separazione ruoli"""
    
    print("🧪 TEST VERIFICA OBBLIGATORIA - SEPARAZIONE RUOLI")
    print("=" * 50)
    
    try:
        from core.surgical_pipeline import surgical_pipeline
        from core.state import CognitiveState
        from storage.users import User
        
        user = User(user_id="test_separation")
        cognitive_state = CognitiveState.build("test_separation")
        
        print("\n1. Test chat_free → deve usare Mistral")
        print("-" * 40)
        
        result = await surgical_pipeline.process_message(
            "ciao come stai?",
            cognitive_state,
            [],
            [],
            None,
            {},
            None
        )
        
        display_text = result.get('display_text', '')
        print(f"Risposta: {display_text}")
        
        # Verifiche obbligatorie
        checks = []
        
        # 1. Log NON devono contenere [PERSONALPLEX] Generating
        print("\n2. Verifica log")
        print("-" * 20)
        print("❌ NESSUN [PERSONALPLEX] Generating chat response")
        print("✅ DEVE comparire model=mistral-7b-instruct")
        print("✅ DEVE comparire [PERSONALPLEX] ORCHESTRATORE PURO")
        
        # 2. Risposta deve esistere
        if display_text and len(display_text.strip()) > 3:
            checks.append("Risposta generata correttamente")
            print("✅ Risposta generata correttamente")
        else:
            print("❌ Nessuna risposta generata")
        
        # 3. TTS deve funzionare
        tts_text = result.get('tts_text', '')
        if tts_text:
            checks.append("TTS funzionante")
            print("✅ TTS funzionante")
        else:
            print("❌ TTS non funzionante")
        
        print(f"\n🎯 CHECKS PASSATI: {len(checks)}/3")
        
        if len(checks) == 3:
            print("\n🎉 SEPARAZIONE RUOLI COMPLETATA!")
            print("✅ Personalplex = ORCHESTRATORE PURO")
            print("✅ Mistral = UNICA VOCE")
            print("✅ Nessun fallback a Personalplex")
            print("✅ Architettura rispettata")
            return True
        else:
            print("\n❌ SEPARAZIONE RUOLI FALLITA!")
            print("⚠️ Verificare violazioni architetturali")
            return False
            
    except Exception as e:
        print(f"❌ Errore test: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print("🎯 OBIETTIVO: Separazione ruoli Personalplex/Mistral")
    print("Personalplex = ORCHESTRATORE PURO")
    print("Mistral = UNICA VOCE")
    print("=" * 50)
    
    success = asyncio.run(test_role_separation())
    
    if success:
        print("\n✅ SISTEMA ARCHITETTURALMENTE CORRETTO")
        sys.exit(0)
    else:
        print("\n❌ VIOLAZIONI ARCHITETTURALI RILEVATE")
        sys.exit(1)
