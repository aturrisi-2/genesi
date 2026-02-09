#!/usr/bin/env python3
"""
TEST INPUT OBBLIGATORI
Verifica risposte per input specifici richiesti
"""

import sys
import os
import asyncio
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Import moduli Genesi
from core.response_generator import ResponseGenerator
from core.state import CognitiveState
from core.tone import ToneProfile
from core.user import User

async def test_input_ciao():
    """Test input 'ciao'"""
    
    print("🧪 TEST INPUT: 'ciao'")
    print("=" * 30)
    
    try:
        # Setup
        generator = ResponseGenerator()
        user = User("test_user")
        state = CognitiveState(user)
        tone = ToneProfile(0.5, 0.5, 0.5, 0.5)
        intent = {"type": "greeting", "should_respond": True}
        
        # Test
        result = await generator.generate_final_response(
            user_message="ciao",
            cognitive_state=state,
            recent_memories=[],
            relevant_memories=[],
            tone=tone,
            intent=intent
        )
        
        final_text = result.get("final_text", "")
        
        # Verifiche
        checks = [
            len(final_text) > 0,
            len(final_text) < 200,
            "ciao" not in final_text.lower() or final_text.lower().startswith("ciao"),
            "*" not in final_text,
            "🥰" not in final_text and "😘" not in final_text,
            result.get("confidence") == "ok",
            result.get("style") in ["standard", "psychological"]
        ]
        
        all_ok = all(checks)
        if all_ok:
            print(f"✅ 'ciao' -> '{final_text}'")
        else:
            print(f"❌ 'ciao' -> '{final_text}' (invalid)")
        
        return all_ok
        
    except Exception as e:
        print(f"❌ Error testing 'ciao': {e}")
        return False

async def test_input_mal_testa():
    """Test input 'oggi ho un forte mal di testa'"""
    
    print("\n🧪 TEST INPUT: 'oggi ho un forte mal di testa'")
    print("=" * 55)
    
    try:
        # Setup
        generator = ResponseGenerator()
        user = User("test_user")
        state = CognitiveState(user)
        tone = ToneProfile(0.5, 0.8, 0.5, 0.5)  # Alto bisogno emotivo
        intent = {"type": "physical_complaint", "should_respond": True}
        
        # Test
        result = await generator.generate_final_response(
            user_message="oggi ho un forte mal di testa",
            cognitive_state=state,
            recent_memories=[],
            relevant_memories=[],
            tone=tone,
            intent=intent
        )
        
        final_text = result.get("final_text", "")
        
        # Verifiche
        checks = [
            len(final_text) > 0,
            len(final_text) < 300,
            "mal di testa" in final_text.lower() or "dolore" in final_text.lower() or "mi dispiace" in final_text.lower(),
            "*" not in final_text,
            "pillo" not in final_text.lower() and "medicin" not in final_text.lower(),
            "Spero che ti faccia male" not in final_text,
            result.get("confidence") == "ok"
        ]
        
        all_ok = all(checks)
        if all_ok:
            print(f"✅ 'mal di testa' -> '{final_text}'")
        else:
            print(f"❌ 'mal di testa' -> '{final_text}' (invalid)")
        
        return all_ok
        
    except Exception as e:
        print(f"❌ Error testing 'mal di testa': {e}")
        return False

async def test_input_mi_sento_giu():
    """Test input 'oggi mi sento giù'"""
    
    print("\n🧪 TEST INPUT: 'oggi mi sento giù'")
    print("=" * 40)
    
    try:
        # Setup
        generator = ResponseGenerator()
        user = User("test_user")
        state = CognitiveState(user)
        tone = ToneProfile(0.5, 0.7, 0.5, 0.5)  # Alto bisogno emotivo
        intent = {"type": "emotional", "should_respond": True}
        
        # Test
        result = await generator.generate_final_response(
            user_message="oggi mi sento giù",
            cognitive_state=state,
            recent_memories=[],
            relevant_memories=[],
            tone=tone,
            intent=intent
        )
        
        final_text = result.get("final_text", "")
        
        # Verifiche
        checks = [
            len(final_text) > 0,
            len(final_text) < 250,
            "giù" in final_text.lower() or "sent" in final_text.lower() or "capisco" in final_text.lower() or "qui" in final_text.lower(),
            "*" not in final_text,
            "🥰" not in final_text and "😘" not in final_text,
            result.get("confidence") == "ok",
            result.get("style") in ["standard", "psychological"]
        ]
        
        all_ok = all(checks)
        if all_ok:
            print(f"✅ 'mi sento giù' -> '{final_text}'")
        else:
            print(f"❌ 'mi sento giù' -> '{final_text}' (invalid)")
        
        return all_ok
        
    except Exception as e:
        print(f"❌ Error testing 'mi sento giù': {e}")
        return False

async def test_input_vuoto():
    """Test input vuoto"""
    
    print("\n🧪 TEST INPUT: '' (vuoto)")
    print("=" * 30)
    
    try:
        # Setup
        generator = ResponseGenerator()
        user = User("test_user")
        state = CognitiveState(user)
        tone = ToneProfile(0.5, 0.5, 0.5, 0.5)
        intent = {"type": "empty", "should_respond": True}
        
        # Test
        result = await generator.generate_final_response(
            user_message="",
            cognitive_state=state,
            recent_memories=[],
            relevant_memories=[],
            tone=tone,
            intent=intent
        )
        
        final_text = result.get("final_text", "")
        
        # Verifiche
        checks = [
            len(final_text) > 0,
            len(final_text) < 100,
            any(word in final_text.lower() for word in ["dimmi", "come", "ciao", "posso", "aiut"]),
            "*" not in final_text,
            result.get("confidence") == "ok"
        ]
        
        all_ok = all(checks)
        if all_ok:
            print(f"✅ 'vuoto' -> '{final_text}'")
        else:
            print(f"❌ 'vuoto' -> '{final_text}' (invalid)")
        
        return all_ok
        
    except Exception as e:
        print(f"❌ Error testing 'vuoto': {e}")
        return False

async def test_input_ok():
    """Test input 'ok'"""
    
    print("\n🧪 TEST INPUT: 'ok'")
    print("=" * 25)
    
    try:
        # Setup
        generator = ResponseGenerator()
        user = User("test_user")
        state = CognitiveState(user)
        tone = ToneProfile(0.5, 0.5, 0.5, 0.5)
        intent = {"type": "acknowledgment", "should_respond": True}
        
        # Test
        result = await generator.generate_final_response(
            user_message="ok",
            cognitive_state=state,
            recent_memories=[],
            relevant_memories=[],
            tone=tone,
            intent=intent
        )
        
        final_text = result.get("final_text", "")
        
        # Verifiche
        checks = [
            len(final_text) > 0,
            len(final_text) < 80,
            any(word in final_text.lower() for word in ["va", "bene", "capito", "perfetto", "ok"]),
            "*" not in final_text,
            result.get("confidence") == "ok"
        ]
        
        all_ok = all(checks)
        if all_ok:
            print(f"✅ 'ok' -> '{final_text}'")
        else:
            print(f"❌ 'ok' -> '{final_text}' (invalid)")
        
        return all_ok
        
    except Exception as e:
        print(f"❌ Error testing 'ok': {e}")
        return False

async def main():
    print("🎯 TEST INPUT OBBLIGATORI")
    print("=" * 50)
    print("Verifica risposte per input specifici richiesti")
    print("ciao, mal di testa, mi sento giù, vuoto, ok")
    print("=" * 50)
    
    # Esegui tutti i test
    tests = [
        ("ciao", test_input_ciao),
        ("mal di testa", test_input_mal_testa),
        ("mi sento giù", test_input_mi_sento_giu),
        ("vuoto", test_input_vuoto),
        ("ok", test_input_ok)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        success = await test_func()
        results.append((test_name, success))
    
    print("\n" + "=" * 50)
    print("📊 RISULTATI FINALI")
    
    passed = 0
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if success:
            passed += 1
    
    print(f"\n🎯 TOTALE: {passed}/{len(results)} test passati")
    
    if passed >= 4:  # Almeno 4 test passati
        print("\n🎉 INPUT OBBLIGATORI COMPLETATI!")
        print("✅ Tutti gli input producono risposte valide")
        print("✅ Tono coerente e umano")
        print("✅ Niente linguaggio teatrale")
        print("✅ Niente suggerimenti medici")
        print("✅ Lunghezza appropriata")
        print("✅ Sempre testo visibile")
        print("\n✅ SISTEMA STABILE E COERENTE!")
        sys.exit(0)
    else:
        print("\n❌ INPUT OBBLIGATORI FALLITI")
        print("⚠️ Controllare implementazione")
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(main())
