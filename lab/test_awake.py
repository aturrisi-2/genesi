
import asyncio
import os
import sys
from datetime import datetime

# Aggiungi il percorso del progetto per gli import
sys.path.append(os.getcwd())

from core.location_resolver import extract_city_from_message
from core.intent_classifier import intent_classifier
from core.proactor import proactor

async def test_intelligence_v2():
    print("--- TEST INTELLIGENCE V2: AWAKE & OPERATIVE ---")
    
    # 1. Test Location Resolver Fix
    print("\n1. Test Location Resolver (Weather parsing fix):")
    messages = [
        "che tempo farà domani a roma",
        "meteo stasera a milano",
        "previsioni per dopodomani a napoli"
    ]
    for msg in messages:
        city = extract_city_from_message(msg)
        print(f"Msg: '{msg}' -> City: '{city}'")
        if city and "Farà" in city:
            print(f"❌ FAIL: Captured 'Farà' in city name")
        elif city == "Roma" or city == "Milano" or city == "Napoli":
            print(f"✅ PASS")
        else:
            print(f"⚠️ Result: {city}")

    # 2. Test Intent Classifier (Impegni & Frustration)
    print("\n2. Test Intent Classifier (Impegni & Frustration):")
    test_cases = [
        "quali sono i miei impegni?",
        "perchè prima non mi hai risposto?",
        "ho degli appuntamenti domani?"
    ]
    for msg in test_cases:
        intents = await intent_classifier.classify_async(msg, "test_user")
        print(f"Msg: '{msg}' -> Intents: {intents}")
        
    # 3. Test Proactor "Awake" Response (Empty list suggestion)
    print("\n3. Test Proactor (Empty list suggestion):")
    # Simulate user without iCloud/Google
    user_id = "new_test_user_unique_123"
    # Ensure profile is clean
    from core.storage import storage
    await storage.save(f"profile:{user_id}", {"name": "TestUser"})
    
    response = await proactor.handle(user_id, "quali sono i miei impegni?")
    print(f"Response: {response}")
    if "iCloud" in response or "Google" in response:
        print("✅ PASS: Suggestion injected for unconfigured user")
    else:
        print("❌ FAIL: No suggestion injected")

if __name__ == "__main__":
    asyncio.run(test_intelligence_v2())
