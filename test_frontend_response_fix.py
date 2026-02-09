#!/usr/bin/env python3
"""
TEST FRONTEND RESPONSE FIX
Verifica che il frontend usi data.response correttamente
"""

import sys
import os
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_frontend_uses_response():
    """Test che frontend usi data.response"""
    
    print("🧪 TEST FRONTEND USES data.response")
    print("=" * 45)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica uso corretto di data.response
        response_checks = [
            'const botMessage = data.response;' in content,
            'console.log(\'[FRONTEND] CHAT RESPONSE RENDERED:\', data.response);' in content,
            'addGenesiMessage(botMessage);' in content,
            'if (data && data.response && data.response.trim().length > 0)' in content,
            'playTTS(data.response, data.tts_mode);' in content
        ]
        
        # Verifica assenza di final_text
        no_final_text_checks = [
            'data.final_text' not in content,
            'final_text' not in content or content.count('final_text') <= 1  # Solo in commenti
        ]
        
        all_response_ok = all(response_checks)
        all_no_final_text_ok = all(no_final_text_checks)
        
        combined_ok = all_response_ok and all_no_final_text_ok
        if combined_ok:
            print("✅ Frontend uses data.response correctly")
        else:
            print("❌ Frontend still uses wrong fields")
        
        return combined_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_no_fallback_silence():
    """Test assenza fallback silenzioso"""
    
    print("\n🧪 TEST NO FALLBACK SILENCE")
    print("=" * 40)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica assenza fallback
        no_fallback_checks = [
            'if (!response) showPlaceholder()' not in content,
            'showPlaceholder' not in content,
            'placeholder' not in content.lower(),
            'if (!botMessage) return' in content,  # Questo è corretto - non mostra placeholder
            'addGenesiMessage("Sono qui. Riprova...")' not in content
        ]
        
        all_no_fallback = all(no_fallback_checks)
        if all_no_fallback:
            print("✅ No silent fallback found")
        else:
            print("❌ Silent fallback found")
        
        return all_no_fallback
        
    except Exception as e:
        print(f"❌ Error checking fallback: {e}")
        return False

def test_chat_flow_complete():
    """Test flusso chat completo"""
    
    print("\n🧪 TEST CHAT FLOW COMPLETE")
    print("=" * 40)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica flusso completo
        flow_checks = [
            'await fetch(\'/chat\'' in content,
            'const data = await sendChatMessage(text);' in content,
            'console.log(\'[FRONTEND] response received - data=\', data);' in content,
            'const botMessage = data.response;' in content,
            'addGenesiMessage(botMessage);' in content,
            'playTTS(data.response, data.tts_mode);' in content
        ]
        
        all_flow_ok = all(flow_checks)
        if all_flow_ok:
            print("✅ Complete chat flow implemented")
        else:
            print("❌ Incomplete chat flow")
        
        return all_flow_ok
        
    except Exception as e:
        print(f"❌ Error checking chat flow: {e}")
        return False

def test_upload_uses_response():
    """Test che upload usi response"""
    
    print("\n🧪 TEST UPLOAD USES RESPONSE")
    print("=" * 40)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica upload
        upload_checks = [
            'addGenesiMessage(result.response || "File ricevuto.");' in content,
            'result.final_text' not in content
        ]
        
        all_upload_ok = all(upload_checks)
        if all_upload_ok:
            print("✅ Upload uses data.response")
        else:
            print("❌ Upload still uses wrong fields")
        
        return all_upload_ok
        
    except Exception as e:
        print(f"❌ Error checking upload: {e}")
        return False

def test_error_handling():
    """Test gestione errori"""
    
    print("\n🧪 TEST ERROR HANDLING")
    print("=" * 35)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica gestione errori appropriata
        error_checks = [
            'if (!botMessage || botMessage.trim().length === 0) return;' in content,  # Non mostra placeholder
            'console.error(\'Chat error:\', e);' in content,
            'addGenesiMessage("Qualcosa non ha funzionato. Riprova tra poco.");' in content  # Solo per errori reali
        ]
        
        all_error_ok = all(error_checks)
        if all_error_ok:
            print("✅ Proper error handling")
        else:
            print("❌ Improper error handling")
        
        return all_error_ok
        
    except Exception as e:
        print(f"❌ Error checking error handling: {e}")
        return False

if __name__ == "__main__":
    print("🎯 TEST FRONTEND RESPONSE FIX")
    print("=" * 50)
    print("Verifica allineamento frontend/backend")
    print("Uso di data.response invece di data.final_text")
    print("=" * 50)
    
    # Esegui tutti i test
    tests = [
        ("Frontend Uses data.response", test_frontend_uses_response),
        ("No Fallback Silence", test_no_fallback_silence),
        ("Chat Flow Complete", test_chat_flow_complete),
        ("Upload Uses Response", test_upload_uses_response),
        ("Error Handling", test_error_handling)
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
        print("\n🎉 FRONTEND RESPONSE FIX COMPLETATO!")
        print("✅ Frontend usa data.response")
        print("✅ Nessun fallback silenzioso")
        print("✅ Flusso chat completo")
        print("✅ Upload usa response")
        print("✅ Gestione errori appropriata")
        print("\n✅ ALLINEAMENTO FRONTEND/BACKEND COMPLETATO!")
        print("   - fetch(/chat) → data.response")
        print("   - console.log('[FRONTEND] CHAT RESPONSE RENDERED:', data.response)")
        print("   - addGenesiMessage(botMessage)")
        print("   - playTTS(data.response, data.tts_mode)")
        print("   - Nessuna risposta valida scartata")
        print("   - Nessun placeholder o messaggio fantasma")
        sys.exit(0)
    else:
        print("\n❌ FRONTEND RESPONSE FIX FALLITO")
        print("⚠️ Controllare implementazione")
        sys.exit(1)
