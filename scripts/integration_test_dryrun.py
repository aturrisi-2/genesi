#!/usr/bin/env python3
"""
Genesi Integration Test Suite - Dry Run Mode
Testa la logica dello script senza connessione API.
"""
import asyncio
import sys
import os
from datetime import datetime

# Aggiungi il path del progetto
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_script_logic():
    """Testa la logica dello script senza API."""
    print("🧪 Genesi Integration Test - Dry Run Mode")
    print("=" * 50)
    
    # Test import e costanti
    try:
        from scripts.integration_test import GenesiIntegrationTester, TEST_EMAIL, TEST_PASSWORD
        print("✅ Import e costanti OK")
    except Exception as e:
        print(f"❌ Import fallito: {e}")
        return False
    
    # Test creazione tester
    try:
        tester = GenesiIntegrationTester()
        print("✅ Creazione tester OK")
    except Exception as e:
        print(f"❌ Creazione tester fallita: {e}")
        return False
    
    # Test metodi interni (senza chiamate API)
    try:
        # Test pattern matching
        await tester.test_pattern_matching()
        print("✅ Pattern matching OK")
    except Exception as e:
        print(f"❌ Pattern matching fallito: {e}")
        return False
    
    print("✅ Tutti i test dry-run passati!")
    return True

# Aggiungo metodo di test alla classe
async def test_pattern_matching(self):
    """Test pattern matching senza API."""
    import re
    
    # Test pattern per intent classification
    test_patterns = [
        ("INTENT_CLASSIFIED.*intent=greeting", "INTENT_CLASSIFIED intent=greeting user=test"),
        ("TTS_ROUTING.*provider=openai", "TTS_ROUTING category=conversational provider=openai"),
        ("IDENTITY_EXTRACTOR_RAW.*interests", "IDENTITY_EXTRACTOR_RAW interests=['jazz', 'music']"),
    ]
    
    for pattern, test_string in test_patterns:
        match = bool(re.search(pattern, test_string, re.IGNORECASE))
        if not match:
            raise Exception(f"Pattern non matchato: {pattern} vs {test_string}")

# Monkey patch per test
if __name__ == "__main__":
    import scripts.integration_test
    scripts.integration_test.GenesiIntegrationTester.test_pattern_matching = test_pattern_matching
    
    success = asyncio.run(test_script_logic())
    sys.exit(0 if success else 1)
