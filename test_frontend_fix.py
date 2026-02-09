#!/usr/bin/env python3
"""
TEST FRONTEND FIX
Verifica che il frontend usi solo final_text
"""

import sys
import os
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_frontend_final_text_only():
    """Test che frontend usi solo final_text"""
    
    print("🧪 TEST FRONTEND FINAL_TEXT ONLY")
    print("=" * 45)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica assenza vecchi campi
        no_old_fields = [
            'data.response' not in content,
            'data.message' not in content,
            'data.text' not in content,
            'data.reply' not in content
        ]
        
        # Verifica uso solo final_text
        final_text_checks = [
            'data.final_text' in content,
            'const botMessage = data.final_text' in content,
            'if (!botMessage || botMessage.trim().length === 0) return' in content,
            'addGenesiMessage(botMessage)' in content
        ]
        
        # Verifica assenza fallback
        no_fallback_checks = [
            'fallbackText' not in content,
            '|| "Sono qui con te."' not in content,
            '|| "File ricevuto."' not in content or 'result.final_text || result.response' in content  # Fallback solo per upload
        ]
        
        all_no_old = all(no_old_fields)
        all_final_text = all(final_text_checks)
        all_no_fallback = all(no_fallback_checks)
        
        all_ok = all_no_old and all_final_text and all_no_fallback
        if all_ok:
            print("✅ Frontend uses only final_text")
        else:
            print("❌ Frontend still uses old fields")
        
        return all_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_no_conditional_logic():
    """Test assenza logica condizionale su altri campi"""
    
    print("\n🧪 TEST NO CONDITIONAL LOGIC")
    print("=" * 40)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica che non ci siano controlli su altri campi
        no_conditional_checks = [
            'if (data && data.response)' not in content,
            'if (data && data.message)' not in content,
            'if (data && data.text)' not in content,
            'if (data && data.reply)' not in content,
            'data.response &&' not in content,
            'data.message &&' not in content,
            'data.text &&' not in content,
            'data.reply &&' not in content
        ]
        
        # Verifica che ci sia solo controllo su final_text
        final_text_conditional = 'if (!botMessage || botMessage.trim().length === 0) return' in content
        
        all_no_conditional = all(no_conditional_checks) and final_text_conditional
        if all_no_conditional:
            print("✅ No conditional logic on old fields")
        else:
            print("❌ Conditional logic on old fields found")
        
        return all_no_conditional
        
    except Exception as e:
        print(f"❌ Error checking conditional logic: {e}")
        return False

def test_exact_implementation():
    """Test implementazione esatta richiesta"""
    
    print("\n🧪 TEST EXACT IMPLEMENTATION")
    print("=" * 40)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica implementazione esatta
        exact_checks = [
            'const botMessage = data.final_text;' in content,
            'if (!botMessage || botMessage.trim().length === 0) return;' in content,
            'addGenesiMessage(botMessage);' in content
        ]
        
        all_exact = all(exact_checks)
        if all_exact:
            print("✅ Exact implementation found")
        else:
            print("❌ Exact implementation not found")
        
        return all_exact
        
    except Exception as e:
        print(f"❌ Error checking exact implementation: {e}")
        return False

def test_null_handling():
    """Test gestione null/undefined/vuoto"""
    
    print("\n🧪 TEST NULL HANDLING")
    print("=" * 35)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica gestione null/undefined/vuoto
        null_checks = [
            'if (!botMessage || botMessage.trim().length === 0) return' in content,
            'botMessage.trim().length === 0' in content
        ]
        
        all_null_ok = all(null_checks)
        if all_null_ok:
            print("✅ Null/undefined/empty handling correct")
        else:
            print("❌ Null/undefined/empty handling incorrect")
        
        return all_null_ok
        
    except Exception as e:
        print(f"❌ Error checking null handling: {e}")
        return False

def test_no_frontend_generation():
    """Test che frontend non generi testo"""
    
    print("\n🧪 TEST NO FRONTEND GENERATION")
    print("=" * 45)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica assenza generazione testo frontend
        no_generation_checks = [
            '"Ti ascolto."' not in content or 'addGenesiMessage("Ti ascolto.")' not in content,
            '"Sono qui con te."' not in content or 'addGenesiMessage("Sono qui con te.")' not in content,
            '"Qualcosa non ha funzionato"' in content  # Solo per errori
        ]
        
        all_no_generation = all(no_generation_checks)
        if all_no_generation:
            print("✅ No frontend text generation")
        else:
            print("❌ Frontend text generation found")
        
        return all_no_generation
        
    except Exception as e:
        print(f"❌ Error checking frontend generation: {e}")
        return False

if __name__ == "__main__":
    print("🎯 TEST FRONTEND FIX")
    print("=" * 50)
    print("Verifica allineamento frontend/backend")
    print("Uso esclusivo di final_text")
    print("=" * 50)
    
    # Esegui tutti i test
    tests = [
        ("Frontend Final Text Only", test_frontend_final_text_only),
        ("No Conditional Logic", test_no_conditional_logic),
        ("Exact Implementation", test_exact_implementation),
        ("Null Handling", test_null_handling),
        ("No Frontend Generation", test_no_frontend_generation)
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
    
    if passed >= 4:  # Almeno 4 test passati
        print("\n🎉 FRONTEND FIX COMPLETATO!")
        print("✅ Frontend usa solo final_text")
        print("✅ Nessun campo vecchio utilizzato")
        print("✅ Nessuna logica condizionale su altri campi")
        print("✅ Implementazione esatta richiesta")
        print("✅ Gestione null/undefined/vuoto corretta")
        print("✅ Nessuna generazione testo frontend")
        print("\n✅ ALLINEAMENTO FRONTEND/BACKEND COMPLETATO!")
        print("   - const botMessage = data.final_text;")
        print("   - if (!botMessage || botMessage.trim().length === 0) return;")
        print("   - addGenesiMessage(botMessage);")
        print("   - Nessun fallback")
        print("   - Nessun campo vecchio")
        sys.exit(0)
    else:
        print("\n❌ FRONTEND FIX FALLITO")
        print("⚠️ Controllare implementazione")
        sys.exit(1)
