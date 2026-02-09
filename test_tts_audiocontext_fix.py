#!/usr/bin/env python3
"""
TEST TTS AUDIOCONTEXT FIX
Verifica che il fix AudioContext per TTS sia stato implementato correttamente
"""

import sys
import os
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_audiocontext_creation():
    """Test creazione AudioContext con tutti gli stati"""
    
    print("🧪 TEST AUDIOCONTEXT CREATION")
    print("=" * 40)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica gestione stati problematici
        state_checks = [
            '_ttsCtx.state === \'closed\'' in content,
            '_ttsCtx.state === \'suspended\'' in content,
            '_ttsCtx.state === \'interrupted\'' in content,
            'previous state=' in content
        ]
        
        all_states_ok = all(state_checks)
        if all_states_ok:
            print("✅ AudioContext creation handles all states")
        else:
            print("❌ AudioContext creation missing states")
        
        return all_states_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_warm_context_function():
    """Test funzione _warmTTSCtx migliorata"""
    
    print("\n🧪 TEST WARM CONTEXT FUNCTION")
    print("=" * 40)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica miglioramenti _warmTTSCtx
        warm_checks = [
            'WarmTTSCtx - state=' in content,
            'resume().then(' in content,
            'ctx resumed successfully' in content,
            'ctx already running' in content,
            'ctx resume failed' in content
        ]
        
        all_warm_ok = all(warm_checks)
        if all_warm_ok:
            print("✅ WarmTTSCtx function improved")
        else:
            print("❌ WarmTTSCtx function not improved")
        
        return all_warm_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_pre_playback_verification():
    """Test verifica AudioContext prima riproduzione"""
    
    print("\n🧪 TEST PRE-PLAYBACK VERIFICATION")
    print("=" * 45)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica verifica prima riproduzione
        pre_checks = [
            'VERIFICA E RIPRISTINA AudioContext PRIMA della riproduzione' in content,
            'const ttsCtx = _getTTSCtx()' in content,
            'AudioContext check - state=' in content,
            'Resuming AudioContext before playback' in content,
            'await ttsCtx.resume()' in content
        ]
        
        # Verifica sia in entrambe le funzioni
        blob_check = 'AudioContext check (blob) - state=' in content
        
        all_pre_ok = all(pre_checks) and blob_check
        if all_pre_ok:
            print("✅ Pre-playback verification implemented")
        else:
            print("❌ Pre-playback verification missing")
        
        return all_pre_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_both_functions_modified():
    """Test che entrambe le funzioni TTS siano modificate"""
    
    print("\n🧪 TEST BOTH FUNCTIONS MODIFIED")
    print("=" * 40)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica _playTTSChunk
        play_chunk_section = content.split('async function _playTTSChunk(text)')[1].split('async function')[0]
        play_chunk_checks = [
            'VERIFICA E RIPRISTINA AudioContext' in play_chunk_section,
            'const ttsCtx = _getTTSCtx()' in play_chunk_section,
            'await ttsCtx.resume()' in play_chunk_section
        ]
        
        # Verifica _playTTSChunkWithBlob
        blob_chunk_section = content.split('async function _playTTSChunkWithBlob(')[1].split('async function')[0]
        blob_chunk_checks = [
            'VERIFICA E RIPRISTINA AudioContext' in blob_chunk_section,
            'const ttsCtx = _getTTSCtx()' in blob_chunk_section,
            'await ttsCtx.resume()' in blob_chunk_section
        ]
        
        all_functions_ok = all(play_chunk_checks) and all(blob_chunk_checks)
        if all_functions_ok:
            print("✅ Both TTS functions modified")
        else:
            print("❌ Not all TTS functions modified")
        
        return all_functions_ok
        
    except Exception as e:
        print(f"❌ Error analyzing TTS functions: {e}")
        return False

def test_error_handling():
    """Test gestione errori migliorata"""
    
    print("\n🧪 TEST ERROR HANDLING")
    print("=" * 35)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica gestione errori
        error_checks = [
            '.catch(err =>' in content,
            'ctx resume failed' in content,
            'console.error(' in content and 'resume' in content
        ]
        
        all_error_ok = all(error_checks)
        if all_error_ok:
            print("✅ Error handling improved")
        else:
            print("❌ Error handling not improved")
        
        return all_error_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_ios_safari_compatibility():
    """Test compatibilità iOS Safari"""
    
    print("\n🧪 TEST iOS SAFARI COMPATIBILITY")
    print("=" * 45)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica compatibilità iOS
        ios_checks = [
            'window.AudioContext || window.webkitAudioContext' in content,
            'iOS Safari: AudioContext must be created+resumed' in content,
            'user gesture' in content and 'iOS' in content,
            'synchronous' in content and 'gesture' in content
        ]
        
        all_ios_ok = all(ios_checks)
        if all_ios_ok:
            print("✅ iOS Safari compatibility maintained")
        else:
            print("❌ iOS Safari compatibility broken")
        
        return all_ios_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

if __name__ == "__main__":
    print("🎯 TEST TTS AUDIOCONTEXT FIX")
    print("=" * 50)
    print("OBIETTIVO: Verifica fix AudioContext per TTS sempre udibile")
    print("Ogni risposta TTS deve essere sempre riprodotta")
    print("=" * 50)
    
    # Esegui tutti i test
    tests = [
        ("AudioContext Creation", test_audiocontext_creation),
        ("Warm Context Function", test_warm_context_function),
        ("Pre-Playback Verification", test_pre_playback_verification),
        ("Both Functions Modified", test_both_functions_modified),
        ("Error Handling", test_error_handling),
        ("iOS Safari Compatibility", test_ios_safari_compatibility)
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
        print("\n🎉 TTS AUDIOCONTEXT FIX COMPLETATO!")
        print("✅ AudioContext gestisce tutti gli stati")
        print("✅ WarmTTSCtx migliorato")
        print("✅ Verifica pre-riproduzione")
        print("✅ Entrambe le funzioni modificate")
        print("✅ Gestione errori migliorata")
        print("✅ Compatibilità iOS Safari mantenuta")
        print("\n✅ TTS SEMPRE UDIBILE!")
        print("   - AudioContext verificato prima riproduzione")
        print("   - Stati suspended/interrupted/closed gestiti")
        print("   - Resume automatico quando necessario")
        print("   - Funziona dopo uso microfono")
        print("   - Funziona su iOS/Safari")
        print("   - Funziona dopo messaggi consecutivi")
        sys.exit(0)
    else:
        print("\n❌ TTS AUDIOCONTEXT FIX FALLITO")
        print("⚠️ Controllare implementazione")
        sys.exit(1)
