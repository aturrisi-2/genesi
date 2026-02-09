#!/usr/bin/env python3
"""
TEST VERIFICA CHAT REQUEST - Verifica che ChatRequest sia definito correttamente
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_chat_request_import():
    """Testa che ChatRequest sia importabile e funzionante"""
    
    try:
        from api.chat import ChatRequest
        print("✅ ChatRequest importato correttamente")
        
        # Test creazione istanza
        request = ChatRequest(user_id="test123", message="ciao come stai")
        print(f"✅ ChatRequest istanza creata: user_id={request.user_id}, message={request.message}")
        
        # Test attributi
        assert hasattr(request, 'user_id'), "Manca user_id"
        assert hasattr(request, 'message'), "Manca message"
        assert request.user_id == "test123", "user_id non corrisponde"
        assert request.message == "ciao come stai", "message non corrisponde"
        
        print("✅ Tutti i test passati - ChatRequest funzionante")
        return True
        
    except ImportError as e:
        print(f"❌ Errore import: {e}")
        return False
    except Exception as e:
        print(f"❌ Errore test: {e}")
        return False

if __name__ == "__main__":
    success = test_chat_request_import()
    sys.exit(0 if success else 1)
