import asyncio
import os
from core.identity_service import handle_identity_question
from core.memory_brain import memory_brain

# Use a fake key to avoid real API calls
os.environ["OPENAI_API_KEY"] = "sk-test-dummy"

async def run_identity_tests():
    user_id = "identity_test_user"

    print("\n===== STEP 1: Insert Profile and Test 'Chi sono?' =====")
    await memory_brain.update_brain(user_id, "Mi chiamo Elena e vivo a Napoli. Faccio l'ingegnere.")
    response = await handle_identity_question(user_id, "Chi sono?")
    print("RESPONSE:", response)
    assert "Elena" in response, "Name not present"
    assert "Napoli" in response, "City not present"
    assert "ingegnere" in response, "Profession not present"

    print("\n===== STEP 2: Test 'Come mi chiamo?' =====")
    response = await handle_identity_question(user_id, "Come mi chiamo?")
    print("RESPONSE:", response)
    assert "Elena" in response, "Name not returned correctly"

    print("\n===== STEP 3: Test 'Dove vivo?' =====")
    response = await handle_identity_question(user_id, "Dove vivo?")
    print("RESPONSE:", response)
    assert "Napoli" in response, "City not returned"

    print("\n===== STEP 4: Test 'Che lavoro faccio?' =====")
    response = await handle_identity_question(user_id, "Che lavoro faccio?")
    print("RESPONSE:", response)
    assert "ingegnere" in response, "Profession not returned"

    print("\n===== STEP 5: Test Identity Before Profile Exists =====")
    new_user_id = "new_identity_test_user"
    response = await handle_identity_question(new_user_id, "Chi sono?")
    print("RESPONSE:", response)
    assert response == "Non me lo hai ancora detto.", "Unexpected response for non-existent profile"

    print("\n✅ IDENTITY ISOLATED TESTS PASSED")

asyncio.run(run_identity_tests())
