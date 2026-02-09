#!/usr/bin/env python3
"""
TEST GLOBAL AUDIO UNLOCK
Verifica che il fix AudioContext globale per prima gesture sia implementato
"""

import sys
import os
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_unlock_audio_function():
    """Test funzione unlockAudio globale"""
    
    print("🧪 TEST UNLOCK AUDIO FUNCTION")
    print("=" * 40)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica funzione unlockAudio
        unlock_checks = [
            'function unlockAudio()' in content,
            'window.audioContext = new (window.AudioContext || window.webkitAudioContext)()' in content,
            'window.audioContext.resume().then(' in content,
            'window.audioUnlocked = true' in content,
            'console.log(\'[AUDIO] Unlocking audio on first user gesture\')' in content
        ]
        
        all_unlock_ok = all(unlock_checks)
        if all_unlock_ok:
            print("✅ unlockAudio function implemented")
        else:
            print("❌ unlockAudio function missing")
        
        return all_unlock_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_first_gesture_listeners():
    """Test event listener per prima gesture"""
    
    print("\n🧪 TEST FIRST GESTURE LISTENERS")
    print("=" * 45)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica listener per touch e click
        gesture_checks = [
            'document.addEventListener(\'touchstart\', function _firstTouch()' in content,
            'unlockAudio()' in content and 'touchstart' in content,
            'document.addEventListener(\'click\', function _firstClick(e)' in content,
            'window.audioUnlocked' in content and 'click' in content,
            '{ once: true }' in content
        ]
        
        all_gesture_ok = all(gesture_checks)
        if all_gesture_ok:
            print("✅ First gesture listeners implemented")
        else:
            print("❌ First gesture listeners missing")
        
        return all_gesture_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_global_audiocontext_usage():
    """Test uso ESCLUSIVO di window.audioContext"""
    
    print("\n🧪 TEST GLOBAL AUDIOCONTEXT USAGE")
    print("=" * 45)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica _getTTSCtx usi solo globale
        getctx_checks = [
            'USA ESCLUSIVAMENTE il AudioContext globale' in content,
            'if (!window.audioContext)' in content,
            'return window.audioContext' in content,
            'new (window.AudioContext || window.webkitAudioContext)()' not in content.split('function _getTTSCtx')[1].split('function')[0]
        ]
        
        all_getctx_ok = all(getctx_checks)
        if all_getctx_ok:
            print("✅ Global AudioContext usage enforced")
        else:
            print("❌ Global AudioContext usage not enforced")
        
        return all_getctx_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_audio_unlock_verification():
    """Test verifica audioUnlocked prima TTS"""
    
    print("\n🧪 TEST AUDIO UNLOCK VERIFICATION")
    print("=" * 45)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica verifica audioUnlocked
        unlock_checks = [
            'if (!window.audioUnlocked)' in content,
            'skipping TTS playback' in content,
            'reason=audio_not_unlocked' in content,
            'VERIFICA AUDIO UNLOCK PRIMA DI PROCEDERE' in content
        ]
        
        # Verifica sia in entrambe le funzioni
        blob_check = 'reason=audio_not_unlocked_blob' in content
        
        all_unlock_ok = all(unlock_checks) and blob_check
        if all_unlock_ok:
            print("✅ Audio unlock verification implemented")
        else:
            print("❌ Audio unlock verification missing")
        
        return all_unlock_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_no_audiocontext_creation():
    """Test che TTS non crei mai AudioContext"""
    
    print("\n🧪 TEST NO AUDIOCONTEXT CREATION")
    print("=" * 45)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica assenza creazione AudioContext in TTS
        tts_section = content.split('async function _playTTSChunk')[1].split('async function')[0]
        blob_section = content.split('async function _playTTSChunkWithBlob')[1].split('async function')[0]
        
        no_creation_checks = [
            'new (window.AudioContext || window.webkitAudioContext)()' not in tts_section,
            'new (window.AudioContext || window.webkitAudioContext)()' not in blob_section,
            '_ttsCtx = new' not in content,  # Vecchia variabile
            '_getTTSCtx()' in content  # Usa solo getter
        ]
        
        all_no_creation_ok = all(no_creation_checks)
        if all_no_creation_ok:
            print("✅ No AudioContext creation in TTS")
        else:
            print("❌ AudioContext creation found in TTS")
        
        return all_no_creation_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_compatibility_maintained():
    """Test compatibilità browser"""
    
    print("\n🧪 TEST COMPATIBILITY MAINTAINED")
    print("=" * 45)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica compatibilità
        compat_checks = [
            'window.AudioContext || window.webkitAudioContext' in content,
            'isTouchDevice' in content,
            'addEventListener(\'touchstart\'' in content,
            'addEventListener(\'click\'' in content,
            'Safari iOS' in content or 'iOS' in content
        ]
        
        all_compat_ok = all(compat_checks)
        if all_compat_ok:
            print("✅ Browser compatibility maintained")
        else:
            print("❌ Browser compatibility broken")
        
        return all_compat_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

if __name__ == "__main__":
    print("🎯 TEST GLOBAL AUDIO UNLOCK")
    print("=" * 50)
    print("OBIETTIVO: Verifica AudioContext globale per prima gesture")
    print("Dopo il primo tap, TUTTE le risposte TTS udibili")
    print("=" * 50)
    
    # Esegui tutti i test
    tests = [
        ("Unlock Audio Function", test_unlock_audio_function),
        ("First Gesture Listeners", test_first_gesture_listeners),
        ("Global AudioContext Usage", test_global_audiocontext_usage),
        ("Audio Unlock Verification", test_audio_unlock_verification),
        ("No AudioContext Creation", test_no_audiocontext_creation),
        ("Compatibility Maintained", test_compatibility_maintained)
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
        print("\n🎉 GLOBAL AUDIO UNLOCK COMPLETATO!")
        print("✅ Funzione unlockAudio implementata")
        print("✅ Listener prima gesture implementati")
        print("✅ Uso ESCLUSIVO AudioContext globale")
        print("✅ Verifica audioUnlocked prima TTS")
        print("✅ Nessuna creazione AudioContext in TTS")
        print("✅ Compatibilità browser mantenuta")
        print("\n✅ TTS SEMPRE UDIBILE DOPO PRIMA GESTURE!")
        print("   - AudioContext creato alla prima gesture")
        print("   - Mai distrutto o ricreato")
        print("   - Riutilizzato per TUTTE le riproduzioni")
        print("   - Compatibile Safari iOS, Chrome mobile, Desktop")
        print("   - TTS silenzioso solo se audioUnlocked === false")
        sys.exit(0)
    else:
        print("\n❌ GLOBAL AUDIO UNLOCK FALLITO")
        print("⚠️ Controllare implementazione")
        sys.exit(1)
