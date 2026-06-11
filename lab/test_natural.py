"""
TEST NATURAL INTELLIGENCE SYSTEM
Verifica la qualità delle risposte relazionali di Genesi v5.
"""

import asyncio
import sys
import os

# Aggiungi root al path per importare core
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from core.proactor import proactor
from core.storage import storage
from core.chat_memory import chat_memory
from core.log import log

async def run_test(test_id, user_id, message, expected_traits=None):
    print(f"\n--- TEST {test_id}: \"{message}\" ---")
    
    # 1. Reset memory for controlled test
    chat_memory.clear_messages(user_id)
    
    # 2. Mock profile if needed
    profile = await storage.load(f"profile:{user_id}", default={})
    if not profile.get("name"):
        profile["name"] = "Alfio"
        profile["city"] = "Roma"
        await storage.save(f"profile:{user_id}", profile)
    
    # 3. Call proactor
    response = await proactor.handle(user_id, message)
    
    print(f"GENESI: {response}")
    
    # 4. Basic heuristic verification
    passed = True
    reasons = []
    
    if len(response.split('.')) > 5:
        passed = False
        reasons.append("Risposta troppo lunga/prolissa")
        
    if any(bot_word in response.lower() for bot_word in ["sono un'ia", "come modello", "mi scuso per il disagio"]):
        passed = False
        reasons.append("Linguaggio da chatbot rilevato")
        
    # Check for naturalness (at least one punctuation variety or conversational filler)
    conversational_markers = ["...", "!", "?", "dai", "figo", "uff", "vero", "su"]
    if not any(marker in response.lower() for marker in conversational_markers):
        # Non è un fallimento bloccante ma lo segnaliamo
        print("NOTA: Mancano marcatori colloquiali forti, ma potrebbe essere ok.")

    if passed:
        print(f"✅ TEST {test_id} PASS")
    else:
        print(f"❌ TEST {test_id} FAIL: {', '.join(reasons)}")
    return passed

async def main():
    user_id = "test_alfio_natural"
    
    tests = [
        (1, "Ehilà Genesi, cosa ho da fare domani?"),
        (2, "Sono stanco morto oggi, non ne posso più."),
        (3, "Mostrami i miei promemoria, vediamo se siamo a posto.")
    ]
    
    all_passed = True
    for tid, msg in tests:
        res = await run_test(tid, user_id, msg)
        if not res:
            all_passed = False
            
    if all_passed:
        print("\n🚀 RISULTATO FINALE: 100% SUCCESS - Genesi Upgrade Verificato!")
    else:
        print("\n⚠️ RISULTATO FINALE: Alcuni test falliti. Controllare i prompt.")

if __name__ == "__main__":
    asyncio.run(main())
