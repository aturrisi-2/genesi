from core.tts_sanitizer import sanitize_for_tts

def test_sanitization():
    test_cases = [
        ("Ecco la **Guida**.", "Ecco la Guida."),
        ("Link [qui](/guida)", "Link qui"),
        ("* Punto 1\n* Punto 2", "Punto 1 Punto 2"),
        ("> Citazione", "Citazione"),
        ("https://example.com/test", ""),
        ("Slash / slash", "Slash slash"),
        ("Ellissi...", "Ellissi "),
    ]
    
    for input_text, expected in test_cases:
        actual = sanitize_for_tts(input_text)
        if actual.strip() == expected.strip():
            print(f"✅ PASS: '{input_text}' -> '{actual}'")
        else:
            print(f"❌ FAIL: '{input_text}' -> '{actual}' (expected '{expected}')")

if __name__ == "__main__":
    test_sanitization()
