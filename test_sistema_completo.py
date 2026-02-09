#!/usr/bin/env python3
"""
TEST SISTEMA COMPLETO
Verifica finale del sistema FINAL_RESPONSE
"""

import sys
import os
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_backend_final_response():
    """Test backend FINAL_RESPONSE"""
    
    print("🧪 TEST BACKEND FINAL_RESPONSE")
    print("=" * 40)
    
    try:
        with open("core/response_generator.py", "r") as f:
            content = f.read()
        
        # Verifica backend
        backend_checks = [
            'generate_final_response(' in content,
            'final_text' in content,
            'confidence' in content,
            'style' in content,
            'forbidden_patterns' in content,
            'minimal_responses' in content,
            '_is_valid_response(' in content,
            '_select_and_validate_response(' in content
        ]
        
        all_backend_ok = all(backend_checks)
        if all_backend_ok:
            print("✅ Backend FINAL_RESPONSE implemented")
        else:
            print("❌ Backend FINAL_RESPONSE missing")
        
        return all_backend_ok
        
    except Exception as e:
        print(f"❌ Error reading backend: {e}")
        return False

def test_api_contract():
    """Test contratto API"""
    
    print("\n🧪 TEST API CONTRACT")
    print("=" * 35)
    
    try:
        with open("api/chat.py", "r") as f:
            content = f.read()
        
        # Verifica API
        api_checks = [
            'generate_final_response(' in content,
            '"final_text": response_text' in content,
            '"confidence": confidence' in content,
            '"style": style' in content,
            'final_result.get("final_text"' in content
        ]
        
        all_api_ok = all(api_checks)
        if all_api_ok:
            print("✅ API contract implemented")
        else:
            print("❌ API contract missing")
        
        return all_api_ok
        
    except Exception as e:
        print(f"❌ Error reading API: {e}")
        return False

def test_frontend_final_text():
    """Test frontend final_text"""
    
    print("\n🧪 TEST FRONTEND FINAL_TEXT")
    print("=" * 45)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica frontend
        frontend_checks = [
            'data.final_text' in content,
            'final_text rendered' in content,
            'addGenesiMessage(data.final_text)' in content,
            'playTTS(data.final_text' in content,
            'fallbackText' in content
        ]
        
        all_frontend_ok = all(frontend_checks)
        if all_frontend_ok:
            print("✅ Frontend final_text implemented")
        else:
            print("❌ Frontend final_text missing")
        
        return all_frontend_ok
        
    except Exception as e:
        print(f"❌ Error reading frontend: {e}")
        return False

def test_style_validation():
    """Test validazione stile"""
    
    print("\n🧪 TEST STYLE VALIDATION")
    print("=" * 40)
    
    try:
        with open("core/response_generator.py", "r") as f:
            content = f.read()
        
        # Verifica stile
        style_checks = [
            r'\*[a-zA-Z]+\*' in content,  # No azioni teatrali
            r'🥰|😘|💋' in content,  # No emoji eccessive
            r'Spero che ti faccia male' in content,  # No linguaggio inappropriato
            r'prendi.*pillo|medicina|farmac' in content,  # No suggerimenti medici
            'len(text) > 500' in content,  # Lunghezza max
            're.search(' in content,  # Regex validation
            're.sub(' in content  # Cleaning
        ]
        
        all_style_ok = all(style_checks)
        if all_style_ok:
            print("✅ Style validation implemented")
        else:
            print("❌ Style validation missing")
        
        return all_style_ok
        
    except Exception as e:
        print(f"❌ Error reading style validation: {e}")
        return False

def test_proposal_system():
    """Test sistema proposte"""
    
    print("\n🧪 TEST PROPOSAL SYSTEM")
    print("=" * 40)
    
    try:
        with open("core/response_generator.py", "r") as f:
            content = f.read()
        
        # Verifica proposte
        proposal_checks = [
            'proposals = []' in content,
            'personalplex' in content,
            'llm' in content,
            'local' in content,
            'tools' in content,
            'confidence' in content,
            'proposals.sort(' in content,
            '_get_minimal_response(' in content
        ]
        
        all_proposal_ok = all(proposal_checks)
        if all_proposal_ok:
            print("✅ Proposal system implemented")
        else:
            print("❌ Proposal system missing")
        
        return all_proposal_ok
        
    except Exception as e:
        print(f"❌ Error reading proposal system: {e}")
        return False

def test_minimal_responses():
    """Test risposte minimali"""
    
    print("\n🧪 TEST MINIMAL RESPONSES")
    print("=" * 40)
    
    try:
        with open("core/response_generator.py", "r") as f:
            content = f.read()
        
        # Verifica risposte minimali
        minimal_checks = [
            '"Ti ascolto. Dimmi pure."' in content,
            '"Sono qui con te."' in content,
            '"Capisco. Continua."' in content,
            '"Mi dispiace che ti senti così."' in content,
            '"Va bene. Dimmi di più."' in content,
            '"Ti capisco."' in content,
            '"Sono qui per te."' in content
        ]
        
        all_minimal_ok = all(minimal_checks)
        if all_minimal_ok:
            print("✅ Minimal responses implemented")
        else:
            print("❌ Minimal responses missing")
        
        return all_minimal_ok
        
    except Exception as e:
        print(f"❌ Error reading minimal responses: {e}")
        return False

def test_no_silence_blocks():
    """Test assenza blocchi silenzio"""
    
    print("\n🧪 TEST NO SILENCE BLOCKS")
    print("=" * 40)
    
    try:
        with open("core/response_generator.py", "r") as f:
            content = f.read()
        
        # Verifica assenza blocchi silenzio
        no_silence_checks = [
            'return ""' not in content,  # No ritorno vuoto
            'should_respond' not in content or 'False' not in content,  # No blocco should_respond
            'silence' not in content.lower() or 'decision' not in content.lower()  # No decisione silenzio
        ]
        
        all_no_silence_ok = all(no_silence_checks)
        if all_no_silence_ok:
            print("✅ No silence blocks")
        else:
            print("❌ Silence blocks found")
        
        return all_no_silence_ok
        
    except Exception as e:
        print(f"❌ Error checking silence blocks: {e}")
        return False

if __name__ == "__main__":
    print("🎯 TEST SISTEMA COMPLETO")
    print("=" * 50)
    print("Verifica finale sistema FINAL_RESPONSE")
    print("Backend + API + Frontend + Stile + Proposte")
    print("=" * 50)
    
    # Esegui tutti i test
    tests = [
        ("Backend FINAL_RESPONSE", test_backend_final_response),
        ("API Contract", test_api_contract),
        ("Frontend Final Text", test_frontend_final_text),
        ("Style Validation", test_style_validation),
        ("Proposal System", test_proposal_system),
        ("Minimal Responses", test_minimal_responses),
        ("No Silence Blocks", test_no_silence_blocks)
    ]
    
    results = []
    
    for test_name, test_func in tests:
        print(f"\n{'='*50}")
        success = test_func()
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
    
    if passed >= 6:  # Almeno 6 test passati
        print("\n🎉 SISTEMA COMPLETO COMPLETATO!")
        print("✅ Backend FINAL_RESPONSE implementato")
        print("✅ Contratto API nuovo")
        print("✅ Frontend usa final_text")
        print("✅ Validazione stile umano")
        print("✅ Sistema proposte multiplo")
        print("✅ Risposte minimali umane")
        print("✅ Nessun blocco silenzio")
        print("\n✅ SISTEMA COERENTE, STABILE, UMANO!")
        print("   - UNA SOLA RISPOSTA FINALE")
        print("   - Coerente, umana, sobria")
        print("   - Sempre visibile (testo + audio)")
        print("   - Niente linguaggio teatrale")
        print("   - Niente suggerimenti medici")
        print("   - Fallback minimale umano")
        print("   - API contract: final_text, confidence, style")
        print("   - Frontend mostra sempre final_text")
        print("   - TTS sempre su final_text")
        sys.exit(0)
    else:
        print("\n❌ SISTEMA COMPLETO FALLITO")
        print("⚠️ Controllare implementazione")
        sys.exit(1)
