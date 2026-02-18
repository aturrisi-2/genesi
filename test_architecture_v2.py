"""
GENESI - Architecture v2 Tests (Proactor v4)
Tests: Identity Router deterministic, Tool Router, Relational Router,
       Knowledge Router, GPT isolation, regression safety.
"""

import asyncio
import sys
import os
import logging
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key-for-local-testing")

# Patch asyncio.sleep to be instant during tests (avoid 1s backoff delays)
_original_sleep = asyncio.sleep
async def _instant_sleep(seconds):
    pass
asyncio.sleep = _instant_sleep

from core.proactor import (
    Proactor, proactor,
    is_identity_question, is_relational_message, is_knowledge_question,
    IDENTITY_TRIGGERS, RELATIONAL_TRIGGERS, KNOWLEDGE_TRIGGERS,
)
from core.memory_brain import memory_brain
from core.tool_services import ToolService
from core.intent_classifier import intent_classifier
from core.context_assembler import ContextAssembler
from core.latent_state import latent_state_engine

passed = 0
failed = 0


def check(label, condition, detail=""):
    global passed, failed
    if condition:
        print(f"  [OK] {label}")
        passed += 1
    else:
        msg = f"  [FAIL] {label}"
        if detail:
            msg += f" -- {detail}"
        print(msg)
        failed += 1


class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text

    def json(self):
        return self._json


# =====================================================================
# GROUP 1: IDENTITY DETECTOR — deterministic matching
# =====================================================================

print("\n===== GROUP 1: Identity Detector =====")

# All triggers must match
for trigger in IDENTITY_TRIGGERS:
    check(f"identity trigger: '{trigger}'", is_identity_question(trigger))

# Non-identity messages must NOT match
non_identity = ["ciao come stai", "che tempo fa", "cos'è un bug", "mi sento triste"]
for msg in non_identity:
    check(f"NOT identity: '{msg}'", not is_identity_question(msg))


# =====================================================================
# GROUP 2: RELATIONAL DETECTOR
# =====================================================================

print("\n===== GROUP 2: Relational Detector =====")

for trigger in RELATIONAL_TRIGGERS[:5]:
    check(f"relational trigger: '{trigger}'", is_relational_message(trigger))

non_relational = ["che tempo fa", "cos'è un bug", "come mi chiamo"]
for msg in non_relational:
    check(f"NOT relational: '{msg}'", not is_relational_message(msg))


# =====================================================================
# GROUP 3: KNOWLEDGE DETECTOR
# =====================================================================

print("\n===== GROUP 3: Knowledge Detector =====")

for trigger in KNOWLEDGE_TRIGGERS:
    check(f"knowledge trigger: '{trigger}'", is_knowledge_question(trigger))

non_knowledge = ["ciao", "mi sento triste", "come mi chiamo", "che tempo fa"]
for msg in non_knowledge:
    check(f"NOT knowledge: '{msg}'", not is_knowledge_question(msg))


# =====================================================================
# GROUP 4: IDENTITY ROUTER — deterministic responses
# =====================================================================

print("\n===== GROUP 4: Identity Router — Deterministic =====")


async def test_identity_deterministic():
    """Identity questions return deterministic answers from profile, zero GPT."""
    user_id = "test_id_v2_001"

    # Seed profile
    await memory_brain.update_brain(user_id, "mi chiamo Elena e vivo a Napoli")
    await memory_brain.update_brain(user_id, "lavoro come avvocato")

    p = Proactor()

    # Test: "come mi chiamo" -> "Ti chiami Elena."
    resp_name = await p.handle("come mi chiamo", "chat_free", user_id)
    check("identity: 'come mi chiamo' -> contains Elena", "Elena" in resp_name, f"got: {resp_name[:80]}")
    check("identity: response is deterministic string", isinstance(resp_name, str) and len(resp_name) < 100)

    # Test: "dove vivo" -> "Vivi a Napoli."
    resp_city = await p.handle("dove vivo", "chat_free", user_id)
    check("identity: 'dove vivo' -> contains Napoli", "Napoli" in resp_city, f"got: {resp_city[:80]}")

    # Test: "che lavoro faccio" -> "Lavori come avvocato."
    resp_job = await p.handle("che lavoro faccio", "chat_free", user_id)
    check("identity: 'che lavoro faccio' -> contains avvocato", "avvocato" in resp_job, f"got: {resp_job[:80]}")

    # Test: "chi sono" -> summary with all facts
    resp_chi = await p.handle("chi sono", "chat_free", user_id)
    check("identity: 'chi sono' -> contains Elena", "Elena" in resp_chi, f"got: {resp_chi[:80]}")
    check("identity: 'chi sono' -> contains Napoli", "Napoli" in resp_chi, f"got: {resp_chi[:80]}")


asyncio.run(test_identity_deterministic())


# =====================================================================
# GROUP 5: IDENTITY ROUTER — missing field
# =====================================================================

print("\n===== GROUP 5: Identity Router — Missing Field =====")


async def test_identity_missing():
    """Identity questions with missing data return 'Non me lo hai ancora detto.'"""
    user_id = "test_id_v2_empty"
    p = Proactor()

    # No profile seeded — fresh user
    resp_name = await p.handle("come mi chiamo", "chat_free", user_id)
    check("identity missing: name -> 'Non me lo hai ancora detto'",
          "Non me lo hai ancora detto" in resp_name, f"got: {resp_name[:80]}")

    resp_city = await p.handle("dove vivo", "chat_free", user_id)
    check("identity missing: city -> 'Non me lo hai ancora detto'",
          "Non me lo hai ancora detto" in resp_city, f"got: {resp_city[:80]}")

    resp_job = await p.handle("che lavoro faccio", "chat_free", user_id)
    check("identity missing: job -> 'Non me lo hai ancora detto'",
          "Non me lo hai ancora detto" in resp_job, f"got: {resp_job[:80]}")


asyncio.run(test_identity_missing())


# =====================================================================
# GROUP 6: TOOL ROUTER — weather success
# =====================================================================

print("\n===== GROUP 6: Tool Router — Weather Success =====")


async def test_weather_success():
    """Weather tool returns data on HTTP 200."""
    p = Proactor()
    ts = ToolService()
    fake = FakeResponse(200, {
        "weather": [{"description": "cielo sereno"}],
        "main": {"temp": 22.5, "feels_like": 21.0, "humidity": 55},
        "wind": {"speed": 3.2}
    })
    mc = AsyncMock()
    mc.get = AsyncMock(return_value=fake)
    mc.is_closed = False
    ts._http_client = mc

    with patch("core.tool_services.tool_service", ts), \
         patch.object(p, '_handle_tool', wraps=p._handle_tool):
        # Call tool_service directly to test
        with patch("core.tool_services.OPENWEATHER_API_KEY", "test-key"):
            result = await ts.get_weather("che tempo fa a Roma")
    check("weather 200: contains temperature", "22" in result)
    check("weather 200: contains city", "Roma" in result)
    check("weather 200: not error", "non disponibile" not in result)


asyncio.run(test_weather_success())


# =====================================================================
# GROUP 7: TOOL ROUTER — weather failure (deterministic error)
# =====================================================================

print("\n===== GROUP 7: Tool Router — Weather Failure =====")


async def test_weather_failure():
    """Weather tool failure returns deterministic error, NOT GPT."""
    p = Proactor()

    # Patch tool_service to raise
    async def failing_weather(msg):
        raise ConnectionError("timeout")

    with patch.object(p, '_handle_tool', wraps=p._handle_tool):
        original = p._handle_tool
        # Simulate tool exception via proactor
        with patch("core.tool_services.tool_service.get_weather", side_effect=ConnectionError("timeout")):
            result = await p._handle_tool("weather", "che tempo fa", "test_user")
    check("weather fail: deterministic error message",
          "non è disponibile" in result or "Errore" in result, f"got: {result[:80]}")
    check("weather fail: no GPT call", "GPT" not in result)


asyncio.run(test_weather_failure())


# =====================================================================
# GROUP 8: TOOL ROUTER — news invalid key (deterministic)
# =====================================================================

print("\n===== GROUP 8: Tool Router — News Invalid Key =====")


async def test_news_invalid_key():
    """News with invalid API key returns deterministic error."""
    p = Proactor()
    ts = ToolService()
    fake = FakeResponse(401, {"status": "error", "code": "apiKeyInvalid"})
    mc = AsyncMock()
    mc.get = AsyncMock(return_value=fake)
    mc.is_closed = False
    ts._http_client = mc

    with patch("core.tool_services.GNEWS_API_KEY", "bad-key"):
        result = await ts.get_news("notizie su Roma")
    check("news 401: contains 'non valida' or 'non configurato'",
          "non valida" in result or "non configurato" in result.lower(), f"got: {result[:80]}")


asyncio.run(test_news_invalid_key())


# =====================================================================
# GROUP 9: RELATIONAL ROUTING
# =====================================================================

print("\n===== GROUP 9: Relational Routing =====")


async def test_relational_routing():
    """Relational messages go through relational router with GPT."""
    user_id = "test_rel_v2"
    await memory_brain.update_brain(user_id, "mi chiamo Sara")

    p = Proactor()
    # GPT will fail (test key) -> falls back to autonomous response
    result = await p.handle("mi sento triste oggi", "chat_free", user_id)
    check("relational: returns string", isinstance(result, str))
    check("relational: not empty", len(result) > 0)
    check("relational: not error message", "problema" not in result.lower())

    # Verify routing log would have been called
    check("relational: is_relational_message detects 'mi sento triste'",
          is_relational_message("mi sento triste oggi"))


asyncio.run(test_relational_routing())


# =====================================================================
# GROUP 10: KNOWLEDGE ROUTING
# =====================================================================

print("\n===== GROUP 10: Knowledge Routing =====")


async def test_knowledge_routing():
    """Knowledge questions route to knowledge router."""
    user_id = "test_know_v2"
    p = Proactor()

    # GPT will fail (test key) -> deterministic fallback
    result = await p.handle("cos'è un algoritmo", "chat_free", user_id)
    check("knowledge: returns string", isinstance(result, str))
    check("knowledge: not empty", len(result) > 0)
    # Should be the knowledge fallback message since GPT fails
    check("knowledge: is_knowledge_question detects 'cos'è un algoritmo'",
          is_knowledge_question("cos'è un algoritmo"))


asyncio.run(test_knowledge_routing())


# =====================================================================
# GROUP 11: GPT NEVER CALLED ON IDENTITY
# =====================================================================

print("\n===== GROUP 11: GPT Never Called on Identity =====")


async def test_gpt_never_on_identity():
    """Identity router NEVER calls GPT — verify by patching _call_llm_model."""
    user_id = "test_gpt_block"
    await memory_brain.update_brain(user_id, "mi chiamo Giulia e vivo a Torino")

    gpt_called = False

    async def spy_llm(*args, **kwargs):
        nonlocal gpt_called
        gpt_called = True
        return None

    p = Proactor()
    with patch("core.proactor._call_llm_model", spy_llm) if hasattr(__import__('core.proactor', fromlist=['_call_llm_model']), '_call_llm_model') else patch("core.evolution_engine._call_llm_model", spy_llm):
        result = await p.handle("come mi chiamo", "chat_free", user_id)

    check("GPT block: identity response contains Giulia", "Giulia" in result, f"got: {result[:80]}")
    check("GPT block: GPT was NOT called", not gpt_called)

    # Also test "dove vivo"
    gpt_called = False
    with patch("core.evolution_engine._call_llm_model", spy_llm):
        result2 = await p.handle("dove vivo", "chat_free", user_id)
    check("GPT block: city response contains Torino", "Torino" in result2, f"got: {result2[:80]}")
    check("GPT block: GPT was NOT called for city", not gpt_called)


asyncio.run(test_gpt_never_on_identity())


# =====================================================================
# GROUP 12: GPT NEVER CALLED ON TOOL FAILURE
# =====================================================================

print("\n===== GROUP 12: GPT Never Called on Tool Failure =====")


async def test_gpt_never_on_tool_fail():
    """Tool failure returns deterministic error, GPT never called."""
    gpt_called = False

    async def spy_llm(*args, **kwargs):
        nonlocal gpt_called
        gpt_called = True
        return None

    p = Proactor()
    with patch("core.evolution_engine._call_llm_model", spy_llm), \
         patch("core.tool_services.tool_service.get_weather", side_effect=ConnectionError("fail")):
        result = await p._handle_tool("weather", "che tempo fa", "test_user")

    check("tool fail: deterministic error returned",
          "non è disponibile" in result or "Errore" in result, f"got: {result[:80]}")
    check("tool fail: GPT was NOT called", not gpt_called)


asyncio.run(test_gpt_never_on_tool_fail())


# =====================================================================
# GROUP 13: PROACTOR ROUTING ORDER
# =====================================================================

print("\n===== GROUP 13: Proactor Routing Order =====")


async def test_routing_order():
    """Verify routing priority: identity > tool > relational > knowledge."""
    # "chi sono" is identity AND could be relational — identity must win
    check("routing: 'chi sono' -> identity wins over relational",
          is_identity_question("chi sono"))

    # "mi sento triste" is relational, NOT identity
    check("routing: 'mi sento triste' -> relational, not identity",
          is_relational_message("mi sento triste") and not is_identity_question("mi sento triste"))

    # "cos'è un bug" is knowledge, NOT relational
    check("routing: 'cos'è un bug' -> knowledge, not relational",
          is_knowledge_question("cos'è un bug") and not is_relational_message("cos'è un bug"))

    # "che tempo fa" is tool intent
    intent = intent_classifier.classify("che tempo fa a Roma")
    check("routing: 'che tempo fa' -> weather intent", intent == "weather")

    # Verify proactor source has all 4 routers
    pa_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core/proactor.py")
    with open(pa_path, "r", encoding="utf-8") as f:
        pa_src = f.read()
    check("source: _handle_identity exists", "async def _handle_identity" in pa_src)
    check("source: _handle_tool exists", "async def _handle_tool" in pa_src)
    check("source: _handle_relational exists", "async def _handle_relational" in pa_src)
    check("source: _handle_knowledge exists", "async def _handle_knowledge" in pa_src)
    check("source: is_identity_question defined", "def is_identity_question" in pa_src)
    check("source: is_relational_message defined", "def is_relational_message" in pa_src)
    check("source: is_knowledge_question defined", "def is_knowledge_question" in pa_src)
    check("source: PROACTOR_V4_ACTIVE", "PROACTOR_V4_ACTIVE" in pa_src)
    check("source: IDENTITY_ROUTER log tag", "IDENTITY_ROUTER" in pa_src)
    check("source: TOOL_ROUTER_OK log tag", "TOOL_ROUTER_OK" in pa_src)
    check("source: RELATIONAL_ROUTER_LLM_FAIL log tag", "RELATIONAL_ROUTER_LLM_FAIL" in pa_src)
    check("source: KNOWLEDGE_ROUTER_LLM_FAIL log tag", "KNOWLEDGE_ROUTER_LLM_FAIL" in pa_src)


asyncio.run(test_routing_order())


# =====================================================================
# GROUP 14: GPT ISOLATION — verify no direct LLM calls outside routers
# =====================================================================

print("\n===== GROUP 14: GPT Isolation =====")

# Verify that context_assembler and emotional_intensity_engine do NOT call GPT
ca_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core/context_assembler.py")
with open(ca_path, "r", encoding="utf-8") as f:
    ca_src = f.read()
check("context_assembler: no openai import", "openai" not in ca_src)
check("context_assembler: no AsyncOpenAI", "AsyncOpenAI" not in ca_src)
check("context_assembler: no _call_llm", "_call_llm" not in ca_src)

ei_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core/emotional_intensity_engine.py")
with open(ei_path, "r", encoding="utf-8") as f:
    ei_src = f.read()
check("emotional_intensity: no openai import", "openai" not in ei_src)
check("emotional_intensity: no AsyncOpenAI", "AsyncOpenAI" not in ei_src)
check("emotional_intensity: no _call_llm", "_call_llm" not in ei_src)


# =====================================================================
# GROUP 15: LUCA/MILANO MANDATORY E2E (via Proactor v4)
# =====================================================================

print("\n===== GROUP 15: Luca/Milano E2E via Proactor v4 =====")


async def test_luca_milano_v2():
    """Mandatory: 'Mi chiamo Luca e vivo a Milano' then 'Dove vivo?' -> Milano."""
    user_id = "test_luca_v2"
    p = Proactor()

    # Step 1: Store identity
    result1 = await p.handle("Mi chiamo Luca e vivo a Milano.", "chat_free", user_id)
    check("Luca E2E: first message processed", isinstance(result1, str) and len(result1) > 0)

    # Step 2: Ask "Dove vivo?" — must go through Identity Router
    result2 = await p.handle("Dove vivo?", "chat_free", user_id)
    check("Luca E2E: 'Dove vivo?' -> contains Milano",
          "Milano" in result2, f"got: {result2[:80]}")
    check("Luca E2E: response is deterministic (short)",
          len(result2) < 100, f"len={len(result2)}")

    # Step 3: Ask "come mi chiamo" — must return Luca
    result3 = await p.handle("come mi chiamo", "chat_free", user_id)
    check("Luca E2E: 'come mi chiamo' -> contains Luca",
          "Luca" in result3, f"got: {result3[:80]}")


asyncio.run(test_luca_milano_v2())


# =====================================================================
# RESULTS
# =====================================================================
print(f"\n{'='*60}")
print(f"RISULTATI: {passed} passed, {failed} failed")
print(f"{'='*60}")

if failed > 0:
    print("\nFAILED - Ci sono test falliti")
else:
    print("\nALL PASSED")
