import asyncio
import os

# Usa chiave finta per evitare chiamate vere
os.environ["OPENAI_API_KEY"] = "sk-test-dummy"

from core.proactor import Proactor
from core.memory_brain import memory_brain

async def run_test():

    user_id = "identity_test_user"

    print("\n===== STEP 1: Inserimento Profilo =====")

    # Simula frase utente che salva profilo
    await memory_brain.update_brain(user_id, "Mi chiamo Elena e vivo a Napoli. Faccio l'ingegnere.")

    profile = await memory_brain.semantic.get_profile(user_id)

    print("PROFILE STORED:", profile)

    print("\n===== STEP 2: Test 'Chi sono?' =====")

    proactor = Proactor()
    response = await proactor.handle(user_id, "Chi sono?")

    print("RESPONSE:", response)

    assert "Elena" in response, "Nome non presente"
    assert "Napoli" in response, "Città non presente"

    print("\n===== STEP 3: Test 'Come mi chiamo?' =====")

    response = await proactor.handle(user_id, "Come mi chiamo?")
    print("RESPONSE:", response)

    assert "Elena" in response, "Nome non restituito correttamente"

    print("\n===== STEP 4: Test 'Dove vivo?' =====")

    response = await proactor.handle(user_id, "Dove vivo?")
    print("RESPONSE:", response)

    assert "Napoli" in response, "Città non restituita"

    print("\n===== STEP 5: Test 'Che lavoro faccio?' =====")

    response = await proactor.handle(user_id, "Che lavoro faccio?")
    print("RESPONSE:", response)

    assert "ingegnere" in response.lower(), "Professione non restituita"

    print("\n✅ IDENTITY ROUTE MANUAL TEST PASSED")

asyncio.run(run_test())
