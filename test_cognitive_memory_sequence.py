import os
from core.cognitive_memory_engine import CognitiveMemoryEngine
from core.context_assembler import ContextAssembler
from core.memory_brain import memory_brain
from core.latent_state import latent_state_engine
import asyncio

# Create test user and memory engine
user_id = "test_user"
cognitive_engine = CognitiveMemoryEngine()

# Test cognitive evaluation sequence
async def test_cognitive_memory_sequence():
    # Test name persistence
    decision = cognitive_engine.evaluate_event(user_id, "Mi chiamo Luca", {})
    assert decision['persist'] == True, "Name should persist"

    # Test profession persistence
    decision = cognitive_engine.evaluate_event(user_id, "Faccio il medico", {})
    assert decision['persist'] == True, "Profession should persist"

    # Test profession query
    context_assembler = ContextAssembler(memory_brain, latent_state_engine)
    context = await context_assembler.build(user_id, "Che lavoro faccio?")
    assert "medico" in context['summary'], "Profession should be 'medico'"

    print("\n✅ COGNITIVE MEMORY SEQUENCE TEST PASSED")

# Run the test
asyncio.run(test_cognitive_memory_sequence())
