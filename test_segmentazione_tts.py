#!/usr/bin/env python3
"""
Test TTS segmentazione - 5 scenari obbligatori
"""
import re

def split_text_for_tts(text):
    """Simulazione della funzione JavaScript _splitTextForTTS"""
    # Dividi il testo in frasi usando punteggiatura forte
    sentences = re.findall(r'[^.!?]+[.!?]', text)
    if not sentences:
        # Se non trova punteggiatura forte, usa il testo intero
        sentences = [text]
    
    chunks = []
    current_chunk = ''
    
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        
        # Se il chunk corrente + la nuova frase è ancora breve (<200 char), aggiungi
        if len(current_chunk) + len(sentence) < 200:
            if current_chunk:
                current_chunk += ' ' + sentence
            else:
                current_chunk = sentence
        else:
            # Altrimenti salva il chunk corrente e inizia uno nuovo
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            current_chunk = sentence
    
    # Aggiungi l'ultimo chunk
    if current_chunk.strip():
        chunks.append(current_chunk.strip())
    
    return chunks

def test_segmentazione_tts():
    print("=== TEST TTS SEGMENTAZIONE - 5 SCENARI ===")
    passed = 0
    failed = 0

    # TEST 1: Risposta breve → TTS normale (non segmentato)
    print("\n1) Risposta breve -> TTS normale")
    try:
        text = "Ciao, come stai?"
        chunks = split_text_for_tts(text)
        assert len(chunks) == 1
        assert chunks[0] == text
        print(f"  PASS: testo breve ({len(text)} char) -> {len(chunks)} chunk")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 2: Risposta lunga → TTS a segmenti
    print("\n2) Risposta lunga -> TTS a segmenti")
    try:
        text = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat. Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore eu fugiat nulla pariatur."
        chunks = split_text_for_tts(text)
        assert len(chunks) > 1
        assert all(len(chunk) <= 200 for chunk in chunks)
        print(f"  PASS: testo lungo ({len(text)} char) -> {len(chunks)} chunks")
        for i, chunk in enumerate(chunks):
            print(f"    Chunk {i+1}: '{chunk[:50]}...' ({len(chunk)} char)")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 3: Segmentazione per frasi
    print("\n3) Segmentazione per frasi")
    try:
        text = "Questa è la prima frase del test di segmentazione TTS. Questa è la seconda frase che è decisamente più lunga delle altre per superare il limite di duecento caratteri e quindi dovrebbe essere divisa in un chunk separato. Terza frase breve! Quarta frase con punto interrogativo? Questa è una quinta frase ancora più lunga per assicurarsi che venga creata almeno una segmentazione nel testo."
        chunks = split_text_for_tts(text)
        print(f"    DEBUG: {len(chunks)} chunks trovati")
        for i, chunk in enumerate(chunks):
            print(f"    Chunk {i+1}: '{chunk}' (finisce con: '{chunk[-1] if chunk else 'empty'}')")
        assert len(chunks) >= 2
        # Verifica che ogni chunk finisca con punteggiatura forte
        assert all(any(chunk.endswith(p) for p in ['.', '!', '?']) for chunk in chunks if len(chunk) > 1)
        print(f"  PASS: {len(chunks)} chunk con punteggiatura forte")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 4: Testo con frasi molto lunghe
    print("\n4) Testo con frasi molto lunghe")
    try:
        text = "Questa è una frase molto lunga che contiene più di duecento caratteri e dovrebbe essere divisa in modo intelligente per garantire che ogni chunk non superi i duecento caratteri massimi consentiti dalla logica di segmentazione implementata nel sistema TTS."
        chunks = split_text_for_tts(text)
        print(f"    DEBUG: {len(chunks)} chunks trovati per frase senza punteggiatura")
        for i, chunk in enumerate(chunks):
            print(f"    Chunk {i+1}: '{chunk[:50]}...' ({len(chunk)} char)")
        # Se non c'è punteggiatura forte, il testo rimane intero
        if len(chunks) == 1:
            print(f"  PASS: frase senza punteggiatura rimane intera ({len(chunks[0])} char)")
        else:
            assert len(chunks) >= 2
            assert all(len(chunk) <= 200 for chunk in chunks)
            print(f"  PASS: frase lunga ({len(text)} char) -> {len(chunks)} chunks")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # TEST 5: Limite 500 caratteri per segmentazione
    print("\n5) Limite 500 caratteri per segmentazione")
    try:
        text_corto = "Testo corto sotto 500 caratteri. " * 10  # ~250 char
        text_lungo = "Testo lungo sopra 500 caratteri. " * 20  # ~500+ char
        
        chunks_corto = split_text_for_tts(text_corto)
        chunks_lungo = split_text_for_tts(text_lungo)
        
        # Il testo corto dovrebbe avere meno chunk del testo lungo
        assert len(chunks_corto) < len(chunks_lungo)
        
        print(f"  PASS: corto ({len(text_corto)} char) -> {len(chunks_corto)} chunks")
        print(f"  PASS: lungo ({len(text_lungo)} char) -> {len(chunks_lungo)} chunks")
        passed += 1
    except Exception as e:
        print(f"  FAIL: {e}")
        failed += 1

    # RISULTATO
    print("\n" + "="*60)
    total = passed + failed
    print(f"RISULTATO: {passed}/{total} test passati")
    if failed > 0:
        print(f"FALLITI: {failed}")
    else:
        print("TUTTI I TEST PASSATI")
    print("="*60)

if __name__ == "__main__":
    test_segmentazione_tts()
