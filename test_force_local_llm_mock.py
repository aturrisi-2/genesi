#!/usr/bin/env python3
"""
Test forzatura PersonalPlex 7B con mock funzionante
Dimostra che la logica di forzatura funziona correttamente
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_force_local_llm_mock():
    """Test forzatura PersonalPlex 7B con mock funzionante"""
    
    print("🧪 TEST FORZATURA PERSONALPLEX 7B (MOCK)")
    print("=" * 45)
    
    try:
        from core.response_generator import ResponseGenerator, FORCE_LOCAL_LLM
        from unittest.mock import patch, MagicMock
        
        print(f"✅ FORCE_LOCAL_LLM = {FORCE_LOCAL_LLM}")
        
        if not FORCE_LOCAL_LLM:
            print("❌ ERRORE: FORCE_LOCAL_LLM non è abilitato")
            return False
        
        generator = ResponseGenerator()
        
        # Test cases obbligatori
        test_inputs = [
            "ciao",
            "come stai?", 
            "raccontami una storia breve",
            "ho mal di testa"
        ]
        
        results = []
        
        for i, user_input in enumerate(test_inputs, 1):
            print(f"\n📝 Test {i}/4: '{user_input}'")
            
            # Mock LocalLLM per simulare risposta funzionante
            with patch('core.response_generator.LocalLLM') as mock_local_class:
                mock_local = mock_local_class.return_value
                mock_response = {
                    "response": f"Risposta PersonalPlex per: {user_input}",
                    "intent": "conversation",
                    "confidence": 0.9
                }
                mock_local.analyze.return_value = mock_response
            
                # Parametri test minimi
                cognitive_state = {"mood": "neutral"}
                recent_memories = []
                relevant_memories = []
                tone = "friendly"
                intent = {"type": "conversation", "should_respond": True}
                
                try:
                    import asyncio
                    response = asyncio.run(generator.generate_response(
                        user_input,
                        cognitive_state,
                        recent_memories,
                        relevant_memories,
                        tone,
                        intent
                    ))
                    
                    # Verifica che la risposta contenga il testo PersonalPlex
                    if response and "PersonalPlex" in response:
                        print(f"   ✅ Risposta PersonalPlex: '{response[:50]}...'")
                        results.append((user_input, True, response))
                    else:
                        print(f"   ❌ Risposta non PersonalPlex: '{response[:50]}...'")
                        results.append((user_input, False, response))
                        
                except Exception as e:
                    print(f"   ❌ Errore durante test: {e}")
                    results.append((user_input, False, ""))
        
        # Analizza risultati
        passed = sum(1 for _, success, _ in results if success)
        total = len(results)
        
        print(f"\n📊 RISULTATI TEST:")
        for input_text, success, response in results:
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"{status} '{input_text}'")
        
        print(f"\n🎯 TOTALE: {passed}/{total} test passati")
        
        if passed == total:
            print("🎉 PersonalPlex 7B forzatura FUNZIONANTE!")
            return True
        else:
            print("⚠️ PersonalPlex 7B forzatura ha problemi")
            return False
            
    except Exception as e:
        print(f"❌ Errore generale test: {e}")
        return False

def test_force_local_llm_logs():
    """Test che i log di forzatura siano corretti"""
    
    print("\n🧪 TEST LOG FORZATURA")
    print("=" * 25)
    
    try:
        from core.response_generator import ResponseGenerator, FORCE_LOCAL_LLM
        from unittest.mock import patch, MagicMock
        import io
        import sys
        
        # Cattura output stdout
        captured_output = io.StringIO()
        sys.stdout = captured_output
        
        generator = ResponseGenerator()
        
        # Mock LocalLLM funzionante
        with patch('core.response_generator.LocalLLM') as mock_local_class:
            mock_local = mock_local_class.return_value
            mock_local.analyze.return_value = {
                "response": "Test risposta PersonalPlex",
                "intent": "conversation",
                "confidence": 0.9
            }
            
            # Parametri test
            cognitive_state = {"mood": "neutral"}
            recent_memories = []
            relevant_memories = []
            tone = "friendly"
            intent = {"type": "conversation", "should_respond": True}
            
            import asyncio
            response = asyncio.run(generator.generate_response(
                "test input",
                cognitive_state,
                recent_memories,
                relevant_memories,
                tone,
                intent
            ))
        
        # Ripristina stdout
        sys.stdout = sys.__stdout__
        
        # Analizza log
        log_output = captured_output.getvalue()
        
        required_logs = [
            "[FORCED_LOCAL_LLM] IGNORING Proactor decision",
            "[FORCED_LOCAL_LLM] PersonalPlex 7B called with",
            "[FORCED_LOCAL_LLM] PersonalPlex 7B response",
            "[FORCED_LOCAL_LLM] PersonalPlex 7B SUCCESS"
        ]
        
        print("✅ Verifica log richiesti:")
        all_logs_found = True
        
        for required_log in required_logs:
            if required_log in log_output:
                print(f"   ✅ {required_log}")
            else:
                print(f"   ❌ {required_log}")
                all_logs_found = False
        
        if all_logs_found:
            print("✅ Tutti i log di forzatura presenti")
            return True
        else:
            print("❌ Log di forzatura mancanti")
            return False
            
    except Exception as e:
        print(f"❌ Errore test log: {e}")
        return False

def test_proactor_bypass():
    """Test che Proactor venga bypassato"""
    
    print("\n🧪 TEST BYPASS PROACTOR")
    print("=" * 30)
    
    try:
        from core.response_generator import ResponseGenerator, FORCE_LOCAL_LLM
        from unittest.mock import patch, MagicMock
        
        generator = ResponseGenerator()
        
        # Mock LocalLLM funzionante
        with patch('core.response_generator.LocalLLM') as mock_local_class:
            mock_local = mock_local_class.return_value
            mock_local.analyze.return_value = {
                "response": "Risposta PersonalPlex",
                "intent": "conversation",
                "confidence": 0.9
            }
            
            # Simula Proactor che dice di non rispondere
            cognitive_state = {"mood": "neutral"}
            recent_memories = []
            relevant_memories = []
            tone = "friendly"
            intent = {
                "type": "conversation", 
                "should_respond": False,  # Proactor dice NO!
                "decision": "silence",
                "reason": "proactor_block"
            }
            
            import asyncio
            response = asyncio.run(generator.generate_response(
                "test input",
                cognitive_state,
                recent_memories,
                relevant_memories,
                tone,
                intent
            ))
            
            # Se FORCE_LOCAL_LLM funziona, dovrebbe ignorare Proactor e rispondere
            if response and "PersonalPlex" in response:
                print("✅ Proactor bypassato correttamente")
                print(f"   Risposta: '{response[:50]}...'")
                return True
            else:
                print("❌ Proactor non bypassato")
                return False
                
    except Exception as e:
        print(f"❌ Errore test bypass: {e}")
        return False

if __name__ == "__main__":
    print("🎯 OBIETTIVO CRITICO: FORZATURA PERSONALPLEX 7B (MOCK)")
    print("=" * 55)
    
    # Esegui tutti i test
    success1 = test_force_local_llm_mock()
    success2 = test_force_local_llm_logs()
    success3 = test_proactor_bypass()
    
    print("\n" + "=" * 55)
    print("📊 RISULTATI FINALI")
    
    tests = [
        ("Forzatura PersonalPlex 7B", success1),
        ("Log forzatura", success2),
        ("Bypass Proactor", success3)
    ]
    
    passed = 0
    for test_name, success in tests:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {test_name}")
        if success:
            passed += 1
    
    print(f"\n🎯 TOTALE: {passed}/{len(tests)} test passati")
    
    if passed == len(tests):
        print("\n🎉 FORZATURA PERSONALPLEX 7B VERIFICATA!")
        print("✅ Modello locale chiamato (log presente)")
        print("✅ Risposte generate (mock)")
        print("✅ Proactor bypassato")
        print("✅ Logging completo")
        print("\n✅ LOGICA DI FORZATURA FUNZIONANTE")
        print("✅ PRONTA PER PERSONALPLEX 7B REALE")
        sys.exit(0)
    else:
        print("\n❌ FORZATURA PERSONALPLEX 7B FALLITA")
        print("⚠️ Risolvere problemi logici")
        sys.exit(1)
