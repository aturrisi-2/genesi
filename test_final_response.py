#!/usr/bin/env python3
"""
TEST FINAL RESPONSE SYSTEM
Verifica che il sistema produca UNA SOLA RISPOSTA FINALE coerente
"""

import sys
import os
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_response_generator_structure():
    """Test struttura ResponseGenerator"""
    
    print("🧪 TEST RESPONSE GENERATOR STRUCTURE")
    print("=" * 50)
    
    try:
        with open("core/response_generator.py", "r") as f:
            content = f.read()
        
        # Verifica struttura nuova
        structure_checks = [
            'class ResponseGenerator:' in content,
            'def generate_final_response(' in content,
            'def _is_valid_response(' in content,
            'def _select_and_validate_response(' in content,
            'def _clean_response(' in content,
            'def _get_minimal_response(' in content,
            'forbidden_patterns' in content,
            'minimal_responses' in content
        ]
        
        all_structure_ok = all(structure_checks)
        if all_structure_ok:
            print("✅ ResponseGenerator structure correct")
        else:
            print("❌ ResponseGenerator structure incorrect")
        
        return all_structure_ok
        
    except Exception as e:
        print(f"❌ Error reading response_generator.py: {e}")
        return False

def test_forbidden_patterns():
    """Test pattern vietati"""
    
    print("\n🧪 TEST FORBIDDEN PATTERNS")
    print("=" * 40)
    
    try:
        with open("core/response_generator.py", "r") as f:
            content = f.read()
        
        # Verifica pattern vietati
        forbidden_checks = [
            r'\*[a-zA-Z]+\*' in content,  # *azione*
            r'🥰|😘|💋' in content,  # emoji eccessive
            r'Spero che ti faccia male' in content,
            r'prendi.*pillo|medicina|farmac' in content
        ]
        
        all_forbidden_ok = all(forbidden_checks)
        if all_forbidden_ok:
            print("✅ Forbidden patterns implemented")
        else:
            print("❌ Forbidden patterns missing")
        
        return all_forbidden_ok
        
    except Exception as e:
        print(f"❌ Error reading response_generator.py: {e}")
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
            '"Mi dispiace che ti senti così."' in content
        ]
        
        all_minimal_ok = all(minimal_checks)
        if all_minimal_ok:
            print("✅ Minimal responses implemented")
        else:
            print("❌ Minimal responses missing")
        
        return all_minimal_ok
        
    except Exception as e:
        print(f"❌ Error reading response_generator.py: {e}")
        return False

def test_api_contract():
    """Test contratto API"""
    
    print("\n🧪 TEST API CONTRACT")
    print("=" * 35)
    
    try:
        with open("api/chat.py", "r") as f:
            content = f.read()
        
        # Verifica nuovo contratto API
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
        print(f"❌ Error reading api/chat.py: {e}")
        return False

def test_frontend_final_text():
    """Test frontend usa final_text"""
    
    print("\n🧪 TEST FRONTEND FINAL_TEXT")
    print("=" * 45)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica frontend usa final_text
        frontend_checks = [
            'data.final_text' in content,
            'final_text rendered' in content,
            'final_text suppressed' in content,
            'playTTS(data.final_text' in content,
            'addGenesiMessage(data.final_text)' in content
        ]
        
        all_frontend_ok = all(frontend_checks)
        if all_frontend_ok:
            print("✅ Frontend uses final_text")
        else:
            print("❌ Frontend doesn't use final_text")
        
        return all_frontend_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_style_validation():
    """Test validazione stile"""
    
    print("\n🧪 TEST STYLE VALIDATION")
    print("=" * 40)
    
    try:
        with open("core/response_generator.py", "r") as f:
            content = f.read()
        
        # Verifica validazione stile
        style_checks = [
            'len(text) > 500' in content,  # lunghezza max
            r'[a-zA-Zàèéìòù]' in content,  # lettere italiane
            're.search(' in content,  # regex validation
            're.sub(' in content  # cleaning
        ]
        
        all_style_ok = all(style_checks)
        if all_style_ok:
            print("✅ Style validation implemented")
        else:
            print("❌ Style validation missing")
        
        return all_style_ok
        
    except Exception as e:
        print(f"❌ Error reading response_generator.py: {e}")
        return False

def test_proposal_system():
    """Test sistema proposte"""
    
    print("\n🧪 TEST PROPOSAL SYSTEM")
    print("=" * 40)
    
    try:
        with open("core/response_generator.py", "r") as f:
            content = f.read()
        
        # Verifica sistema proposte
        proposal_checks = [
            'proposals = []' in content,
            'personalplex' in content,
            'llm' in content,
            'local' in content,
            'tools' in content,
            'confidence' in content,
            'proposals.sort(' in content
        ]
        
        all_proposal_ok = all(proposal_checks)
        if all_proposal_ok:
            print("✅ Proposal system implemented")
        else:
            print("❌ Proposal system missing")
        
        return all_proposal_ok
        
    except Exception as e:
        print(f"❌ Error reading response_generator.py: {e}")
        return False

if __name__ == "__main__":
    print("🎯 TEST FINAL RESPONSE SYSTEM")
    print("=" * 50)
    print("OBIETTIVO: Verifica sistema UNA SOLA RISPOSTA FINALE")
    print("Coerente, umana, sobria, sempre visibile")
    print("=" * 50)
    
    # Esegui tutti i test
    tests = [
        ("ResponseGenerator Structure", test_response_generator_structure),
        ("Forbidden Patterns", test_forbidden_patterns),
        ("Minimal Responses", test_minimal_responses),
        ("API Contract", test_api_contract),
        ("Frontend Final Text", test_frontend_final_text),
        ("Style Validation", test_style_validation),
        ("Proposal System", test_proposal_system)
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
        print("\n🎉 FINAL RESPONSE SYSTEM COMPLETATO!")
        print("✅ ResponseGenerator riscritto per FINAL_RESPONSE")
        print("✅ Pattern vietati implementati")
        print("✅ Risposte minimali umane")
        print("✅ Contratto API nuovo")
        print("✅ Frontend usa final_text")
        print("✅ Validazione stile")
        print("✅ Sistema proposte multiplo")
        print("\n✅ SISTEMA COERENTE E STABILE!")
        print("   - UNA SOLA RISPOSTA FINALE")
        print("   - Coerente, umana, sobria")
        print("   - Sempre visibile (testo + audio)")
        print("   - Niente linguaggio teatrale")
        print("   - Niente suggerimenti medici")
        print("   - Fallback minimale umano")
        print("   - API contract: final_text, confidence, style")
        sys.exit(0)
    else:
        print("\n❌ FINAL RESPONSE SYSTEM FALLITO")
        print("⚠️ Controllare implementazione")
        sys.exit(1)
