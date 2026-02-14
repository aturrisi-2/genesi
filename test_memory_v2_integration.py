import os
from core.memory_engine_v2 import MemoryEngineV2
from core.context_assembler import ContextAssembler
from core.memory_brain import memory_brain
from core.latent_state import latent_state_engine

# Create test user and memory engine
user_id = "test_user"
memory_engine = MemoryEngineV2()

# Set up memory V2
memory_engine.update_profile(user_id, "name", "Marco")
memory_engine.update_profile(user_id, "profession", "Medico")
memory_engine.update_relational(user_id, "spouse", "Rita")

# Assemble context
context_assembler = ContextAssembler(memory_brain, latent_state_engine)
context = context_assembler.build(user_id, "Chi sono?")

# Verify memory V2 is prioritized
assert context['memory_v2']['profile']['name'] == "Marco", "Name mismatch in memory V2"
assert context['memory_v2']['profile']['profession'] == "Medico", "Profession mismatch in memory V2"
assert context['memory_v2']['relational']['spouse'] == "Rita", "Spouse mismatch in memory V2"

print("\n✅ MEMORY V2 INTEGRATION TEST PASSED")
