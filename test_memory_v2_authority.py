import os
import asyncio
from core.context_assembler import ContextAssembler
from core.memory_brain import memory_brain
from core.latent_state import latent_state_engine

# Create test user and memory engine
user_id = "test_user"

async def test_memory_v2_authority():
    # Set up memory using memory_brain
    await memory_brain.update_brain(user_id, "mi chiamo Elena")
    await memory_brain.update_brain(user_id, "vivo a Napoli")
    await memory_brain.update_brain(user_id, "lavoro come Ingegnere")
    await memory_brain.update_brain(user_id, "mia moglie si chiama Elena")

    # Assemble context
    context_assembler = ContextAssembler(memory_brain, latent_state_engine)
    context = context_assembler.build(user_id, "Chi sono?")

    # Verify memory V2 authority
    assert context['memory_v2']['profile']['profession'] == "Ingegnere", "Profession mismatch in memory V2"
    assert context['memory_v2']['profile']['spouse'] == "Elena", "Spouse mismatch in memory V2"

    print("\n✅ MEMORY V2 AUTHORITY TEST PASSED")

# Run the test
asyncio.run(test_memory_v2_authority())
