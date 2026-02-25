import asyncio
import os
import sys
from pathlib import Path
import json

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent))

from core.proactor import Proactor
from core.tts_sanitizer import sanitize_for_tts
from core.storage import storage

async def test_scenarios():
    proactor = Proactor()
    test_user = "test_fluidity_user"
    
    # Cleanup storage for test user
    try:
        if os.path.exists(f"memory/profile/{test_user}.json"):
            os.remove(f"memory/profile/{test_user}.json")
    except: pass

    scenarios = [
        {
            "name": "Intelligent Ambiguity (Existing iCloud)",
            "message": "Sincronizza il mio calendario.",
            "setup_profile": {"icloud_user": "alfio@icloud.com"}
        },
        {
            "name": "Explicit iCloud Setup",
            "message": "Ciao Genesi! Mi colleghi il mio account icloud?",
            "expected_intent": "icloud_setup"
        },
        {
            "name": "Ambiguous Calendar (New User)",
            "message": "Voglio configurare il mio calendario.",
            "clear_profile": True
        },
        {
            "name": "Mixed Intent (Weather + Multi-tool)",
            "message": "Che tempo fa a Roma e come posso collegare iCloud?",
            "expected_intent": ["weather", "icloud_setup"]
        },
        {
            "name": "TTS Sanitization Test",
            "message": "Mostrami come fare",
            "simulated_response": "Ecco la **Guida Illustrata** [clicca qui](/guida-icloud). Non leggere gli *asterischi*!",
        }
    ]

    print("=== STARTING GENESI INTELLIGENCE & FLUIDITY TEST ===\n")

    for s in scenarios:
        print(f"--- Scenario: {s['name']} ---")
        
        if s.get("clear_profile"):
            try:
                if os.path.exists(f"memory/profile/{test_user}.json"):
                    os.remove(f"memory/profile/{test_user}.json")
            except: pass
            
        if "setup_profile" in s:
            await storage.save(f"profile:{test_user}", s["setup_profile"])
        
        print(f"User: {s['message']}")
        
        if "simulated_response" in s:
            clean = sanitize_for_tts(s['simulated_response'])
            print(f"Original Response: {s['simulated_response']}")
            print(f"Clean TTS Voice: '{clean}'")
            if "*" in clean or "[" in clean or "/" in clean:
                print("❌ FAIL: Sanitization leaked technical characters!")
            else:
                print("✅ PASS: TTS is clean.")
        else:
            # Real Proactor handle (text only)
            response = await proactor.handle(test_user, s['message'])
            print(f"Genesi: {response}")
            
            # Simple check for intent logic in response
            if s['name'] == "Intelligent Ambiguity (Existing iCloud)":
                if "Ho visto che hai già collegato" in response:
                    print("✅ PASS: Recognized existing account (Intelligence).")
                else:
                    print("❌ FAIL: Did not recognize existing account.")

            if s['name'] == "Ambiguous Calendar (New User)":
                if "Google o iCloud" in response and "Ho visto che" not in response:
                    print("✅ PASS: Correctly asked for clarification for new user.")
                else:
                    print("❌ FAIL: Incorrect clarification logic.")
            
            if s['name'] == "Explicit iCloud Setup":
                if "password specifica" in response:
                    print("✅ PASS: Correctly navigated to iCloud setup instructions.")
                else:
                    print("❌ FAIL: Did not provide setup instructions.")
            
            if s['name'] == "Mixed Intent (Weather + Multi-tool)":
                # Ensure we have weather info and icloud setup info synthesized
                if ("Roma" in response or "meteo" in response.lower()) and "iCloud" in response:
                    print("✅ PASS: Successfully synthesized multiple intents.")
                else:
                    print("❌ FAIL: Missing components in synthesized response.")

        print("\n")

if __name__ == "__main__":
    asyncio.run(test_scenarios())
