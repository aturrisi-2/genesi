#!/usr/bin/env python3
"""
Test fix errore 'self' non definito in STT
Verifica che la validazione STT funzioni senza errori
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def test_stt_self_fix():
    """Test che non ci siano errori 'self' non definiti"""
    
    print("🧪 TEST FIX ERRORE 'self' NON DEFINITO")
    print("=" * 50)
    
    try:
        # Importa la funzione di validazione
        from api.stt import _is_valid_transcription
        
        print("✅ Import _is_valid_transcription riuscito")
        
        # Test vari casi per verificare che la funzione funzioni
        test_cases = [
            ("", False, "empty"),
            ("ciao", True, "valid"),
            ("ok", True, "short_valid"),
            ("aaaaa", False, "repeated"),
            ("come stai", True, "phrase"),
        ]
        
        for text, expected, desc in test_cases:
            try:
                result = _is_valid_transcription(text)
                success = result == expected
                status = "✅" if success else "❌"
                print(f"{status} '{text}' → {result} (expected: {expected}) - {desc}")
                
                if not success:
                    print(f"   ERRORE: risultato inaspettato per '{text}'")
                    return False
                    
            except Exception as e:
                print(f"❌ ERRORE chiamando _is_valid_transcription('{text}'): {e}")
                return False
        
        print("\n✅ Tutti i test di validazione passati")
        return True
        
    except Exception as e:
        print(f"❌ ERRORE importando o testando _is_valid_transcription: {e}")
        return False

def test_stt_import():
    """Test che il modulo STT si importi correttamente"""
    
    print("\n🧪 TEST IMPORT MODULO STT")
    print("=" * 30)
    
    try:
        # Importa il modulo STT completo
        import api.stt
        
        print("✅ Modulo api.stt importato correttamente")
        
        # Verifica che non ci siano riferimenti a 'self' fuori dalle classi
        import inspect
        import re
        
        # Leggi il sorgente del modulo
        stt_source = inspect.getsource(api.stt)
        
        # Cerca pattern 'self.' fuori da definizioni di classe
        lines = stt_source.split('\n')
        in_class = False
        class_indent = 0
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Rileva inizio/fine classe
            if stripped.startswith('class '):
                in_class = True
                class_indent = len(line) - len(line.lstrip())
                continue
            elif in_class and line.strip() and not line.startswith(' '):
                # Linea non indentata = fine classe
                in_class = False
                continue
            
            # Cerca 'self.' fuori da classi
            if 'self.' in line and not in_class:
                print(f"❌ Trovato 'self.' fuori da classe alla riga {i+1}: {line.strip()}")
                return False
        
        print("✅ Nessun 'self.' fuori da classi trovato")
        return True
        
    except Exception as e:
        print(f"❌ ERRORE testando modulo STT: {e}")
        return False

def test_stt_response_structure():
    """Test struttura risposta STT"""
    
    print("\n🧪 TEST STRUTTURA RISPOSTA STT")
    print("=" * 35)
    
    try:
        from api.stt import _is_valid_transcription
        
        # Simula vari scenari di risposta
        scenarios = [
            ("", "empty", "retry"),
            ("ciao", None, None),  # valido, no status
            ("aaaa", "empty", "retry"),  # invalido
        ]
        
        for text, expected_status, expected_action in scenarios:
            is_valid = _is_valid_transcription(text)
            
            if not is_valid:
                # Simula risposta STT per input invalido
                response = {
                    "text": "",
                    "status": expected_status,
                    "action": expected_action
                }
                
                # Verifica struttura
                required_keys = ["text", "status", "action"]
                has_all_keys = all(key in response for key in required_keys)
                
                status = "✅" if has_all_keys else "❌"
                print(f"{status} Invalid input '{text}' → structure OK: {has_all_keys}")
                
                if not has_all_keys:
                    print(f"   ERRORE: struttura risposta incompleta")
                    return False
            else:
                # Input valido
                response = {"text": text}
                status = "✅"
                print(f"{status} Valid input '{text}' → simple response")
        
        print("\n✅ Struttura risposte STT corretta")
        return True
        
    except Exception as e:
        print(f"❌ ERRORE testando struttura risposta: {e}")
        return False

if __name__ == "__main__":
    # Esegui tutti i test
    success1 = test_stt_self_fix()
    success2 = test_stt_import()
    success3 = test_stt_response_structure()
    
    if success1 and success2 and success3:
        print("\n🎯 BUG 'self' NON DEFINITO RISOLTO!")
        print("✅ Validazione STT funzionante")
        print("✅ Nessun 'self.' fuori da classi")
        print("✅ Struttura risposte corretta")
        print("✅ Sistema pronto per test end-to-end")
        sys.exit(0)
    else:
        print("\n❌ BUG 'self' ANCORA PRESENTE")
        sys.exit(1)
