import os
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
def test_cognitive_memory():
    # Test name persistence
    assert cognitive_engine.evaluate_event(user_id, "Mi chiamo Marco", {}) == True, "Name should persist"

    # Test random comment non-persistence
    assert cognitive_engine.evaluate_event(user_id, "Commento casuale", {}) == False, "Random comment should not persist"

    # Test relation persistence
    assert cognitive_engine.evaluate_event(user_id, "Mia moglie si chiama Elena", {}) == True, "Relation should persist"

    # Test profession contradiction
    assert cognitive_engine.evaluate_event(user_id, "Sono un Ingegnere", {}) == True, "Profession contradiction should update"

    # Test strong emotional event persistence
    assert cognitive_engine.evaluate_event(user_id, "Mi sento molto triste", {}) == True, "Strong emotional event should persist"

    print("\n✅ COGNITIVE MEMORY TEST PASSED")

# Run the test
test_cognitive_memory()
