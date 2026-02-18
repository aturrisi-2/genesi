import os
import asyncio
from core.context_assembler import ContextAssembler
from core.memory_brain import memory_brain
from core.latent_state import latent_state_engine

# Create test user and memory engine
user_id = "test_user"

async def test_memory_v2_integration():
    # Set up memory using memory_brain
    await memory_brain.update_brain(user_id, "mi chiamo Marco")
    await memory_brain.update_brain(user_id, "faccio il medico")
    await memory_brain.update_brain(user_id, "mia moglie si chiama Rita")

    # Assemble context
    context_assembler = ContextAssembler(memory_brain, latent_state_engine)
    context = context_assembler.build(user_id, "Chi sono?")

    # Verify memory V2 is prioritized
    assert context['memory_v2']['profile']['name'] == "Marco", "Name mismatch in memory V2"
    assert context['memory_v2']['profile']['profession'] == "medico", "Profession mismatch in memory V2"
    assert context['memory_v2']['profile']['spouse'] == "Rita", "Spouse mismatch in memory V2"

    print("\n✅ MEMORY V2 INTEGRATION TEST PASSED")

# Run the test
asyncio.run(test_memory_v2_integration())
