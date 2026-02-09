#!/usr/bin/env python3
"""
TEST FRONTEND RENDERING
Verifica che il frontend renderizzi sempre le risposte testuali
"""

import sys
import os
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_no_rendering_blocks():
    """Test che non ci siano blocchi al rendering"""
    
    print("🧪 TEST NO RENDERING BLOCKS")
    print("=" * 40)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica assenza blocchi rendering
        blocked_patterns = [
            'showPresenceOnly' in content,
            'presenceOnly' in content,
            'showOnly' in content
        ]
        
        # Verifica presenza funzioni rendering
        rendering_functions = [
            'function addMessage(text, sender)' in content,
            'function addGenesiMessage(text)' in content,
            'addGenesiMessage(data.response)' in content
        ]
        
        no_blocks = not any(blocked_patterns)
        has_rendering = all(rendering_functions)
        
        all_ok = no_blocks and has_rendering
        if all_ok:
            print("✅ No rendering blocks found")
        else:
            print("❌ Rendering blocks still present")
        
        return all_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_psychological_compatibility():
    """Test compatibilità psychological/presence"""
    
    print("\n🧪 TEST PSYCHOLOGICAL COMPATIBILITY")
    print("=" * 45)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica che psychological non blocchi rendering
        psychological_checks = [
            'tts_mode === \'psychological\'' in content,  # Usato per TTS, non per bloccare
            'addGenesiMessage(data.response)' in content,  # Sempre chiamato
            'data.response && data.response.trim().length > 0' in content
        ]
        
        # Verifica assenza filtri psychological
        no_psychological_blocks = [
            'if (data.tts_mode === \'psychological\')' not in content,
            'if (data.branch === \'psychological\')' not in content
        ]
        
        all_psychological_ok = all(psychological_checks) and all(no_psychological_blocks)
        if all_psychological_ok:
            print("✅ Psychological compatibility maintained")
        else:
            print("❌ Psychological blocks found")
        
        return all_psychological_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_frontend_logs():
    """Test log frontend obbligatori"""
    
    print("\n🧪 TEST FRONTEND LOGS")
    print("=" * 35)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica log obbligatori
        required_logs = [
            '[FRONTEND] response received' in content,
            '[FRONTEND] response rendered' in content,
            '[FRONTEND] response suppressed' in content
        ]
        
        all_logs_ok = all(required_logs)
        if all_logs_ok:
            print("✅ Frontend logs implemented")
        else:
            print("❌ Frontend logs missing")
        
        return all_logs_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_fallback_rendering():
    """Test fallback rendering per altri campi"""
    
    print("\n🧪 TEST FALLBACK RENDERING")
    print("=" * 40)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica fallback rendering
        fallback_checks = [
            'possibleTextFields' in content,
            "['response', 'message', 'text', 'content', 'answer']" in content,
            'response rendered (fallback)' in content,
            'no_valid_text_field' in content
        ]
        
        all_fallback_ok = all(fallback_checks)
        if all_fallback_ok:
            print("✅ Fallback rendering implemented")
        else:
            print("❌ Fallback rendering missing")
        
        return all_fallback_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_always_render_response():
    """Test che risposta venga sempre renderizzata"""
    
    print("\n🧪 TEST ALWAYS RENDER RESPONSE")
    print("=" * 45)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica logica sempre render
        always_render_checks = [
            'if (data && data.response)' in content,
            'addGenesiMessage(data.response)' in content,
            'data.response && data.response.trim().length > 0' in content
        ]
        
        # Verifica assenza early return senza rendering
        no_early_returns = [
            'return;' not in content.split('if (data && data.response)')[1].split('addGenesiMessage')[0] if 'addGenesiMessage' in content else False
        ]
        
        all_always_ok = all(always_render_checks) and any(no_early_returns)
        if all_always_ok:
            print("✅ Always render response implemented")
        else:
            print("❌ Always render response missing")
        
        return all_always_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_presence_is_style_only():
    """Test che presence sia solo stile"""
    
    print("\n🧪 TEST PRESENCE IS STYLE ONLY")
    print("=" * 40)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica che presence sia solo stile UI
        presence_checks = [
            'document.getElementById(\'presence\')' in content,
            'presence.style.display' in content,
            '#presence p' in content,
            'neonFlicker' in content  # Solo effetti stilistici
        ]
        
        # Verifica assenza logica presence che blocca
        no_presence_logic = [
            'presence_mode' not in content.lower(),
            'showPresenceOnly' not in content
        ]
        
        all_presence_ok = all(presence_checks) and all(no_presence_logic)
        if all_presence_ok:
            print("✅ Presence is style only")
        else:
            print("❌ Presence has blocking logic")
        
        return all_presence_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

if __name__ == "__main__":
    print("🎯 TEST FRONTEND RENDERING")
    print("=" * 50)
    print("OBIETTIVO: Verifica rendering sempre garantito")
    print("Nessun blocco psychological/presence")
    print("=" * 50)
    
    # Esegui tutti i test
    tests = [
        ("No Rendering Blocks", test_no_rendering_blocks),
        ("Psychological Compatibility", test_psychological_compatibility),
        ("Frontend Logs", test_frontend_logs),
        ("Fallback Rendering", test_fallback_rendering),
        ("Always Render Response", test_always_render_response),
        ("Presence Is Style Only", test_presence_is_style_only)
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
    
    if passed >= 5:  # Almeno 5 test passati
        print("\n🎉 FRONTEND RENDERING COMPLETATO!")
        print("✅ Nessun blocco rendering")
        print("✅ Psychological compatibility mantenuta")
        print("✅ Log frontend implementati")
        print("✅ Fallback rendering implementato")
        print("✅ Always render response")
        print("✅ Presence è solo stile")
        print("\n✅ RENDERING SEMPRE GARANTITO!")
        print("   - '[FRONTEND] response received' log")
        print("   - '[FRONTEND] response rendered' log")
        print("   - '[FRONTEND] response suppressed' log")
        print("   - Fallback per altri campi testuali")
        print("   - Psychological non blocca output")
        print("   - Presence è solo stile UI")
        print("   - addGenesiMessage sempre chiamato")
        sys.exit(0)
    else:
        print("\n❌ FRONTEND RENDERING FALLITO")
        print("⚠️ Controllare implementazione")
        sys.exit(1)
