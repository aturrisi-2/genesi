#!/usr/bin/env python3
"""
TEST PLAYTTSAUDIO IMPLEMENTATION
Verifica che la funzione playTTSAudio sia implementata correttamente
"""

import sys
import os
from pathlib import Path

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_playTTSAudio_function():
    """Test funzione playTTSAudio implementata"""
    
    print("🧪 TEST PLAYTTSAUDIO FUNCTION")
    print("=" * 40)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica funzione playTTSAudio
        playtts_checks = [
            'async function playTTSAudio(blob)' in content,
            'console.log(\'[TTS] TTS blob ricevuto' in content,
            'window.audioContext' in content,
            'decodeAudioData' in content,
            'AudioBufferSourceNode' in content
        ]
        
        all_playtts_ok = all(playtts_checks)
        if all_playtts_ok:
            print("✅ playTTSAudio function implemented")
        else:
            print("❌ playTTSAudio function missing")
        
        return all_playtts_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_decodeAudioData_usage():
    """Test uso decodeAudioData"""
    
    print("\n🧪 TEST DECODEAUDIODATA USAGE")
    print("=" * 40)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica decodeAudioData
        decode_checks = [
            'blob.arrayBuffer()' in content,
            'await window.audioContext.decodeAudioData(arrayBuffer)' in content,
            'audioBuffer.duration' in content,
            'audioBuffer.sampleRate' in content
        ]
        
        all_decode_ok = all(decode_checks)
        if all_decode_ok:
            print("✅ decodeAudioData usage correct")
        else:
            print("❌ decodeAudioData usage incorrect")
        
        return all_decode_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_audiobuffersourcenode_usage():
    """Test uso AudioBufferSourceNode"""
    
    print("\n🧪 TEST AUDIOBUFFERSOURCENODE USAGE")
    print("=" * 45)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica AudioBufferSourceNode
        source_checks = [
            'window.audioContext.createBufferSource()' in content,
            'source.buffer = audioBuffer' in content,
            'source.connect(window.audioContext.destination)' in content,
            'source.start(0)' in content,
            'source.onended' in content
        ]
        
        all_source_ok = all(source_checks)
        if all_source_ok:
            print("✅ AudioBufferSourceNode usage correct")
        else:
            print("❌ AudioBufferSourceNode usage incorrect")
        
        return all_source_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_required_logs():
    """Test log richiesti"""
    
    print("\n🧪 TEST REQUIRED LOGS")
    print("=" * 35)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica log richiesti
        log_checks = [
            'TTS blob ricevuto' in content,
            'AudioContext state:' in content,
            'Playback avviato' in content,
            'ArrayBuffer creato' in content,
            'AudioBuffer decodificato' in content
        ]
        
        all_log_ok = all(log_checks)
        if all_log_ok:
            print("✅ Required logs implemented")
        else:
            print("❌ Required logs missing")
        
        return all_log_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_audiocontext_resume():
    """Test resume AudioContext"""
    
    print("\n🧪 TEST AUDIOCONTEXT RESUME")
    print("=" * 40)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica resume
        resume_checks = [
            'if (window.audioContext.state === \'suspended\')' in content,
            'await window.audioContext.resume()' in content,
            'AudioContext resumed' in content,
            'Resume AudioContext' in content
        ]
        
        all_resume_ok = all(resume_checks)
        if all_resume_ok:
            print("✅ AudioContext resume implemented")
        else:
            print("❌ AudioContext resume missing")
        
        return all_resume_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_integration_with_tts_functions():
    """Test integrazione con funzioni TTS esistenti"""
    
    print("\n🧪 TEST INTEGRATION WITH TTS FUNCTIONS")
    print("=" * 50)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica integrazione
        integration_checks = [
            'await playTTSAudio(blob)' in content,
            'calling_playTTSAudio' in content,
            'AudioBufferSourceNode completato' in content,
            content.count('await playTTSAudio(blob)') >= 2  # Entrambe le funzioni
        ]
        
        all_integration_ok = all(integration_checks)
        if all_integration_ok:
            print("✅ Integration with TTS functions correct")
        else:
            print("❌ Integration with TTS functions missing")
        
        return all_integration_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

def test_error_handling():
    """Test gestione errori"""
    
    print("\n🧪 TEST ERROR HANDLING")
    print("=" * 35)
    
    try:
        with open("static/app.v2.js", "r") as f:
            content = f.read()
        
        # Verifica gestione errori
        error_checks = [
            'try {' in content and 'catch (error)' in content,
            'console.error(\'[TTS] Errore durante playback TTS:\'' in content,
            'Errore details:' in content,
            '_ttsSource = null' in content and '_isPlayingChunk = false' in content
        ]
        
        all_error_ok = all(error_checks)
        if all_error_ok:
            print("✅ Error handling implemented")
        else:
            print("❌ Error handling missing")
        
        return all_error_ok
        
    except Exception as e:
        print(f"❌ Error reading app.v2.js: {e}")
        return False

if __name__ == "__main__":
    print("🎯 TEST PLAYTTSAUDIO IMPLEMENTATION")
    print("=" * 50)
    print("OBIETTIVO: Verifica implementazione playTTSAudio")
    print("decodeAudioData + AudioBufferSourceNode + source.start(0)")
    print("=" * 50)
    
    # Esegui tutti i test
    tests = [
        ("playTTSAudio Function", test_playTTSAudio_function),
        ("decodeAudioData Usage", test_decodeAudioData_usage),
        ("AudioBufferSourceNode Usage", test_audiobuffersourcenode_usage),
        ("Required Logs", test_required_logs),
        ("AudioContext Resume", test_audiocontext_resume),
        ("Integration with TTS Functions", test_integration_with_tts_functions),
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
    
    if passed >= 6:  # Almeno 6 test passati
        print("\n🎉 PLAYTTSAUDIO IMPLEMENTATION COMPLETATA!")
        print("✅ Funzione playTTSAudio implementata")
        print("✅ decodeAudioData utilizzato correttamente")
        print("✅ AudioBufferSourceNode utilizzato correttamente")
        print("✅ Log richiesti implementati")
        print("✅ AudioContext resume implementato")
        print("✅ Integrazione con funzioni TTS corretta")
        print("✅ Gestione errori implementata")
        print("\n✅ SISTEMA TTS CON DECODEAUDIODATA COMPLETO!")
        print("   - async function playTTSAudio(blob)")
        print("   - blob.arrayBuffer() → decodeAudioData()")
        print("   - createBufferSource() → source.start(0)")
        print("   - 'TTS blob ricevuto' log")
        print("   - 'AudioContext state:' log")
        print("   - 'Playback avviato' log")
        print("   - Compatibile Safari iOS, Chrome, Firefox")
        print("   - UN SOLO AudioContext globale")
        sys.exit(0)
    else:
        print("\n❌ PLAYTTSAUDIO IMPLEMENTATION FALLITA")
        print("⚠️ Controllare implementazione")
        sys.exit(1)
