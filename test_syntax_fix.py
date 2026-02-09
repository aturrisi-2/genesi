#!/usr/bin/env python3
"""
TEST SINTASSI CHAT.PY - Verifica che non ci siano errori di sintassi
"""

import ast
import sys
import os

def test_syntax():
    """Testa che api/chat.py abbia sintassi corretta"""
    
    file_path = os.path.join(os.path.dirname(__file__), "api", "chat.py")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            source = f.read()
        
        # Parse del file per verificare sintassi
        ast.parse(source)
        print("Sintassi di api/chat.py corretta")
        
        # Verifica che ChatRequest sia definito
        if "class ChatRequest(BaseModel):" in source:
            print("ChatRequest definito correttamente")
        else:
            print("ChatRequest non trovato")
            return False
        
        # Verifica che non ci siano definizioni duplicate
        chat_request_count = source.count("class ChatRequest(BaseModel):")
        if chat_request_count == 1:
            print("ChatRequest definito una sola volta")
        else:
            print(f"ChatRequest definito {chat_request_count} volte")
            return False
        
        # Verifica che sia usato correttamente
        if "request: ChatRequest" in source:
            print("ChatRequest usato correttamente nelle funzioni")
        else:
            print("ChatRequest non usato correttamente")
            return False
        
        print("Tutti i test sintattici passati")
        return True
        
    except SyntaxError as e:
        print(f"Errore sintassi: {e}")
        return False
    except Exception as e:
        print(f"Errore: {e}")
        return False

if __name__ == "__main__":
    success = test_syntax()
    sys.exit(0 if success else 1)
