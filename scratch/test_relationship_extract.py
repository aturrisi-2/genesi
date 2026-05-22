import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent.absolute()))

# Load env variables
from dotenv import load_dotenv
load_dotenv()

from core.llm_service import llm_service
from core.telegram_group_memory import _RELATIONSHIP_PROMPT
import json

async def test_extraction(first_name, text):
    print(f"\n[TEST] Testing message from {first_name}: '{text}'")
    raw = await llm_service._call_model(
        "openai/gpt-4o-mini",
        _RELATIONSHIP_PROMPT,
        f"Mittente: {first_name}\nMessaggio: {text[:300]}",
        user_id="test",
        route="memory",
    )
    print(f"   LLM Output: {raw.strip()}")
    try:
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        parsed = json.loads(clean.strip())
        print(f"   Parsed JSON: {parsed}")
    except Exception as e:
        print(f"   Failed to parse: {e}")

async def main():
    # Vocatives (should be found=False)
    await test_extraction("Sandra", "Stamattina la connessione ti funziona mamma????")
    await test_extraction("Alfio", "Auguri mamma, ti voglio bene!")
    
    # Declarations (should be found=True)
    await test_extraction("Rita", "Ciao a tutti, qui scrive la mamma! Tutto bene?")
    await test_extraction("Ennio", "Ciao, sono il papà di Alfio. Complimenti per il bot!")

if __name__ == "__main__":
    asyncio.run(main())
