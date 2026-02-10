#!/usr/bin/env python3
"""
TEST VALIDAZIONE BYPASS Q/A - chat_free senza contaminazione
Verifica che chat_free non abbia formattazione didattica
"""

import sys
import os
import asyncio
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def test_bypass_qa():
    """Test bypass Q/A per chat_free"""
    
    print("TEST BYPASS Q/A - chat_free senza contaminazione")
    print("=" * 50)
    
    try:
        from api.chat import chat_endpoint
        from api.user import User
        from datetime import datetime
        
        # Mock request per chat_free
        class MockRequest:
            def __init__(self, message, user_id):
                self.message = message
                self.user_id = user_id
                self.timestamp = datetime.now().isoformat()
        
        user = User(user_id="test_bypass")
        
        print("\nTest: 'ciao come stai?'")
        print("-" * 30)
        print("Output ATTESO:")
        print("- Una sola frase breve")
        print("- Nessuna domanda non richiesta")
        print("- Nessuna auto-presentazione")
        print("- NESSUN 'Risposta:' o prefissi didattici")
        print("-" * 30)
        
        request = MockRequest("ciao come stai?", "test_bypass")
        response = await chat_endpoint(request, http_request=None)
        
        response_text = response.get('response', '')
        print(f"\nRisposta: '{response_text}'")
        
        # Verifiche critiche
        issues = []
        
        # 1. Controlla prefissi didattici
        forbidden_prefixes = [
            'Risposta:', 'Domanda:', 'Answer:', 'Question:',
            'La risposta è:', 'La domanda è:'
        ]
        
        for prefix in forbidden_prefixes:
            if prefix in response_text:
                issues.append(f"PREFISSO DIDATTICO: {prefix}")
        
        # 2. Controlla domande non richieste
        if '?' in response_text and 'come stai' not in response_text.lower():
            issues.append("DOMANDA NON RICHIESTA")
        
        # 3. Controlla auto-presentazione
        auto_pres_patterns = [
            'sono genesis', 'mi chiamo', 'io sono', 'il mio nome'
        ]
        
        for pattern in auto_pres_patterns:
            if pattern in response_text.lower():
                issues.append(f"AUTO-PRESENTAZIONE: {pattern}")
        
        # 4. Controlla lunghezza (deve essere breve)
        if len(response_text.split()) > 20:
            issues.append("TROPPO LUNGA - possibile spiegazione")
        
        # 5. Controlla tono didattico
        didactic_patterns = [
            'spiegare', 'spiegazione', 'infatti', 'ad esempio',
            'ad esempio', 'cioè', 'in altre parole'
        ]
        
        for pattern in didactic_patterns:
            if pattern in response_text.lower():
                issues.append(f"TONO DIDATTICO: {pattern}")
        
        print(f"\nVERIFICA FINALE:")
        if not issues:
            print("✅ NESSUNA CONTAMINAZIONE Q/A")
            print("✅ NESSUN PREFISSO DIDATTICO")
            print("✅ NESSUNA DOMANDA NON RICHIESTA")
            print("✅ NESSUNA AUTO-PRESENTAZIONE")
            print("✅ RISPOSTA BREVE E DIRETTA")
            return True
        else:
            print("❌ CONTAMINAZIONI RILEVATE:")
            for issue in issues:
                print(f"   - {issue}")
            return False
            
    except Exception as e:
        print(f"❌ Errore: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = asyncio.run(test_bypass_qa())
    print(f"\nRISULTATO FINALE: {'SUCCESSO' if success else 'FALLIMENTO'}")
