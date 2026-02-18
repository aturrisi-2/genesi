import os
import asyncio
from core.cognitive_memory_engine import CognitiveMemoryEngine
from core.memory_engine_v2 import MemoryEngineV2
from core.context_assembler import ContextAssembler
from core.memory_brain import memory_brain
from core.latent_state import latent_state_engine

# Create test user and memory engine
user_id = "test_user"
memory_engine_v2 = MemoryEngineV2()
cognitive_engine = CognitiveMemoryEngine()

# Set up memory V2
memory_engine_v2.update_profile(user_id, "name", "Marco")
memory_engine_v2.update_profile(user_id, "profession", "Pilota")
memory_engine_v2.update_profile(user_id, "profession", "Ingegnere")  # Update profession
memory_engine_v2.update_relational(user_id, "spouse", "Elena")

# Test cognitive evaluation
async def test_cognitive_memory():
    # Test name persistence
    assert (await cognitive_engine.evaluate_event(user_id, "Mi chiamo Marco", {}))['persist'] == True, "Name should persist"

    # Test random comment non-persistence
    assert (await cognitive_engine.evaluate_event(user_id, "Commento casuale", {}))['persist'] == False, "Random comment should not persist"

    # Test relation persistence
    assert (await cognitive_engine.evaluate_event(user_id, "Mia moglie si chiama Elena", {}))['persist'] == True, "Relation should persist"

    # Test profession contradiction
    assert (await cognitive_engine.evaluate_event(user_id, "Sono un Ingegnere", {}))['persist'] == True, "Profession contradiction should update"

    # Test strong emotional event persistence
    assert (await cognitive_engine.evaluate_event(user_id, "Mi sento molto triste", {}))['persist'] == True, "Strong emotional event should persist"

    print("\n✅ COGNITIVE MEMORY TEST PASSED")

# Run the test
async def main():
    await test_cognitive_memory()

asyncio.run(main())
