import os
from core.cognitive_memory_engine import CognitiveMemoryEngine
from core.context_assembler import ContextAssembler
from core.memory_brain import memory_brain
from core.latent_state import latent_state_engine
from core.storage import storage
import asyncio

# Create test user and memory engine
user_id = "test_user"
cognitive_engine = CognitiveMemoryEngine()

# Test cognitive evaluation sequence
async def test_cognitive_memory_sequence():
    # Test name persistence
    decision = await cognitive_engine.evaluate_event(user_id, "Mi chiamo Luca", {})
    assert decision['persist'] == True, "Name should persist"

    # Test profession persistence
    decision = await cognitive_engine.evaluate_event(user_id, "Faccio il medico", {})
    assert decision['persist'] == True, "Profession should persist"

    # Load and verify persistent storage
    profile = await storage.load(f"long_term_profile:{user_id}", default={})
    assert profile.get("name") == "Luca", "Profile name should be 'Luca'"
    assert profile.get("profession") == "medico", "Profile profession should be 'medico'"

    print("\nSTORAGE_SAVE log and profile loaded successfully")

# Run the test
asyncio.run(test_cognitive_memory_sequence())
