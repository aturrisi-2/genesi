"""
GENESI - Cost Control & Architecture Stabilization Tests
Tests: model_selector, rate limit protection, fallback_knowledge,
       GNews endpoint, strict router isolation, MEMORY_DIRECT_RESPONSE.
"""

import asyncio
import sys
import os
import logging
from unittest.mock import AsyncMock, patch, MagicMock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key-for-local-testing")

from core.llm_service import (
    LLMService, llm_service, model_selector,
    LLM_DEFAULT_MODEL, LLM_UPGRADE_MODEL, LLM_DEEP_MODEL,
    DEEP_ANALYSIS_TRIGGERS,
)
from core.fallback_knowledge import lookup_fallback, KNOWLEDGE_DB, FACTUAL_TRIGGERS
from core.proactor import (
    Proactor, proactor,
    is_identity_question, is_knowledge_question, is_relational_message,
    SKIP_RELATIONAL_INTENTS, KNOWLEDGE_TRIGGERS,
)
from core.tool_services import ToolService, GNEWS_API_KEY
from core.intent_classifier import intent_classifier
from core.memory_brain import memory_brain

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
# GROUP 1: MODEL SELECTOR -- gpt-4o-mini default
# =====================================================================

print("\n===== GROUP 1: Model Selector =====")

check("default model is gpt-4o-mini", LLM_DEFAULT_MODEL == "gpt-4o-mini")
check("upgrade model is gpt-4o", LLM_UPGRADE_MODEL == "gpt-4o")
check("deep model is claude-opus", LLM_DEEP_MODEL == "claude-opus")

# Default selection
m1 = model_selector("ciao come stai", route="general")
check("model_selector: general -> gpt-4o-mini", m1 == "gpt-4o-mini", f"got: {m1}")

m2 = model_selector("cos'e' un algoritmo", route="knowledge")
check("model_selector: knowledge -> gpt-4o-mini", m2 == "gpt-4o-mini", f"got: {m2}")

m3 = model_selector("spiega il codice", route="technical")
check("model_selector: technical -> gpt-4o-mini", m3 == "gpt-4o-mini", f"got: {m3}")

m4 = model_selector("mi sento triste", route="relational")
check("model_selector: short relational -> gpt-4o-mini", m4 == "gpt-4o-mini", f"got: {m4}")

# Long relational -> gpt-4o
long_msg = "mi sento molto triste oggi " * 20  # >200 chars
m5 = model_selector(long_msg, route="relational")
check("model_selector: long relational -> gpt-4o", m5 == "gpt-4o", f"got: {m5}")


# =====================================================================
# GROUP 2: CLAUDE OPUS ONLY WHEN REQUESTED
# =====================================================================

print("\n===== GROUP 2: Claude Opus Only When Requested =====")

for trigger in DEEP_ANALYSIS_TRIGGERS:
    m = model_selector(f"vorrei una {trigger} del mio stato", route="general")
    check(f"deep trigger '{trigger}' -> claude-opus", m == "claude-opus", f"got: {m}")

# Normal messages should NOT trigger Claude
normal_msgs = ["ciao", "che tempo fa", "cos'e' un bug", "mi sento triste", "spiega il codice"]
for msg in normal_msgs:
    m = model_selector(msg, route="general")
    check(f"NOT claude: '{msg}'", m != "claude-opus", f"got: {m}")


# =====================================================================
# GROUP 3: RATE LIMIT PROTECTION
# =====================================================================

print("\n===== GROUP 3: Rate Limit Protection =====")


async def test_rate_limit_protection():
    """Verify rate limit retry, downgrade, and deterministic fallback."""
    svc = LLMService()

    # Simulate all calls failing
    call_count = 0

    async def always_fail(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return None

    svc._call_model = always_fail

    # _call_with_protection should try: primary, retry, downgrade (if different model)
    result = await svc._call_with_protection("gpt-4o", "prompt", "msg", user_id="test")
    check("rate limit: returns None when all fail", result is None)
    check("rate limit: tried 3 times (primary + retry + downgrade)", call_count == 3, f"got: {call_count}")

    # With default model, no downgrade needed (only 2 tries)
    call_count = 0
    result2 = await svc._call_with_protection("gpt-4o-mini", "prompt", "msg", user_id="test")
    check("rate limit: default model tries 2 times (no downgrade)", call_count == 2, f"got: {call_count}")


asyncio.run(test_rate_limit_protection())


async def test_deterministic_fallback():
    """Verify deterministic fallback never returns 'Non riesco a rispondere'."""
    svc = LLMService()

    fb_knowledge = svc._deterministic_fallback("cos'e' la pressione arteriosa", "knowledge")
    check("fallback knowledge: contains factual info", "pressione" in fb_knowledge.lower(), f"got: {fb_knowledge[:80]}")
    check("fallback knowledge: not 'non riesco'", "non riesco" not in fb_knowledge.lower())

    fb_relational = svc._deterministic_fallback("mi sento triste", "relational")
    check("fallback relational: returns empathic response", len(fb_relational) > 10)
    check("fallback relational: not 'non riesco'", "non riesco" not in fb_relational.lower())

    fb_technical = svc._deterministic_fallback("spiega il codice", "technical")
    check("fallback technical: returns response", len(fb_technical) > 10)
    check("fallback technical: not 'non riesco'", "non riesco" not in fb_technical.lower())

    fb_general = svc._deterministic_fallback("ciao", "general")
    check("fallback general: returns response", len(fb_general) > 10)
    check("fallback general: not 'non riesco'", "non riesco" not in fb_general.lower())


asyncio.run(test_deterministic_fallback())


# =====================================================================
# GROUP 4: FALLBACK KNOWLEDGE DICTIONARY
# =====================================================================

print("\n===== GROUP 4: Fallback Knowledge =====")

# All entries in KNOWLEDGE_DB should be retrievable
check("knowledge DB: pressione arteriosa exists", "pressione arteriosa" in KNOWLEDGE_DB)
check("knowledge DB: capitale germania exists", "capitale germania" in KNOWLEDGE_DB)
check("knowledge DB: capitale francia exists", "capitale francia" in KNOWLEDGE_DB)
check("knowledge DB: sistema solare exists", "sistema solare" in KNOWLEDGE_DB)

# lookup_fallback should match
fb1 = lookup_fallback("cos'e' la pressione arteriosa")
check("lookup: pressione arteriosa -> hit", len(fb1) > 0, f"got: {fb1[:60]}")
check("lookup: pressione arteriosa -> correct", "120/80" in fb1)

fb2 = lookup_fallback("che capitale e' la germania")
check("lookup: capitale germania -> hit", len(fb2) > 0, f"got: {fb2[:60]}")
check("lookup: capitale germania -> Berlino", "Berlino" in fb2)

fb3 = lookup_fallback("definisci sistema solare")
check("lookup: sistema solare -> hit", len(fb3) > 0, f"got: {fb3[:60]}")
check("lookup: sistema solare -> pianeti", "pianeti" in fb3.lower())

# Non-matching should return empty
fb_miss = lookup_fallback("ciao come stai")
check("lookup: non-factual -> empty", fb_miss == "")

fb_miss2 = lookup_fallback("cos'e' il quantum computing")
check("lookup: unknown topic -> empty", fb_miss2 == "")


# =====================================================================
# GROUP 5: GNEWS ENDPOINT
# =====================================================================

print("\n===== GROUP 5: GNews Endpoint =====")

# Verify source code uses gnews.io
ts_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core/tool_services.py")
with open(ts_path, "r", encoding="utf-8") as f:
    ts_src = f.read()

check("source: gnews.io/api/v4/search endpoint", "gnews.io/api/v4/search" in ts_src)
check("source: no newsapi.org references", "newsapi.org" not in ts_src)
check("source: GNEWS_API_KEY used", "GNEWS_API_KEY" in ts_src)
check("source: TOOL_GNEWS_HTTP_CALL tag", "TOOL_GNEWS_HTTP_CALL" in ts_src)
check("source: TOOL_GNEWS_HTTP_STATUS tag", "TOOL_GNEWS_HTTP_STATUS" in ts_src)
check("source: _gnews_search method", "_gnews_search" in ts_src)
check("source: _format_gnews_it method", "_format_gnews_it" in ts_src)


async def test_gnews_mock():
    """Verify GNews API integration with mock."""
    ts = ToolService()
    fake = FakeResponse(200, {
        "totalArticles": 2,
        "articles": [
            {"title": "Notizia uno su Roma", "url": "https://example.com/1"},
            {"title": "Notizia due su Roma", "url": "https://example.com/2"},
        ]
    })
    mc = AsyncMock()
    mc.get = AsyncMock(return_value=fake)
    mc.is_closed = False
    ts._http_client = mc

    with patch("core.tool_services.GNEWS_API_KEY", "test-key"):
        result = await ts.get_news("notizie su Roma")
    check("gnews mock: contains Roma", "Roma" in result, f"got: {result[:80]}")
    check("gnews mock: contains notizia", "Notizia" in result or "notizie" in result.lower(), f"got: {result[:80]}")


asyncio.run(test_gnews_mock())


async def test_gnews_invalid_key():
    """GNews with invalid key returns deterministic error."""
    ts = ToolService()
    fake = FakeResponse(401, {"errors": ["Unauthorized"]})
    mc = AsyncMock()
    mc.get = AsyncMock(return_value=fake)
    mc.is_closed = False
    ts._http_client = mc

    with patch("core.tool_services.GNEWS_API_KEY", "bad-key"):
        result = await ts.get_news("notizie su Roma")
    check("gnews 401: contains 'non valida'", "non valida" in result, f"got: {result[:80]}")


asyncio.run(test_gnews_invalid_key())


# =====================================================================
# GROUP 6: STRICT ROUTER ISOLATION
# =====================================================================

print("\n===== GROUP 6: Strict Router Isolation =====")

# Verify SKIP_RELATIONAL_INTENTS
check("skip_relational: tecnica in list", "tecnica" in SKIP_RELATIONAL_INTENTS)
check("skip_relational: debug in list", "debug" in SKIP_RELATIONAL_INTENTS)
check("skip_relational: spiegazione in list", "spiegazione" in SKIP_RELATIONAL_INTENTS)

# Verify proactor source has strict isolation route
pa_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core/proactor.py")
with open(pa_path, "r", encoding="utf-8") as f:
    pa_src = f.read()
check("source: SKIP_RELATIONAL_INTENTS used in handle", "SKIP_RELATIONAL_INTENTS" in pa_src)
check("source: knowledge_strict route", "route=knowledge_strict" in pa_src)
check("source: MEMORY_DIRECT_RESPONSE log", "MEMORY_DIRECT_RESPONSE" in pa_src)
check("source: ARCHITECTURE_MODE=cost_optimized_v1", "ARCHITECTURE_MODE=cost_optimized_v1" in pa_src)
check("source: model_selector imported", "from core.llm_service import" in pa_src and "model_selector" in pa_src)
check("source: lookup_fallback imported", "from core.fallback_knowledge import lookup_fallback" in pa_src)
check("source: KNOWLEDGE_FALLBACK_HIT log", "KNOWLEDGE_FALLBACK_HIT" in pa_src)


# =====================================================================
# GROUP 7: KNOWLEDGE FALLBACK IN PROACTOR
# =====================================================================

print("\n===== GROUP 7: Knowledge Fallback in Proactor =====")


async def test_knowledge_fallback_proactor():
    """Knowledge router uses fallback_knowledge when LLM fails."""
    user_id = "test_kb_fallback"
    p = Proactor()

    # LLM will fail (test key) -> should use fallback_knowledge
    result = await p.handle("cos'e' la pressione arteriosa", "chat_free", user_id)
    check("knowledge fallback: pressione arteriosa -> factual",
          "pressione" in result.lower() or "120/80" in result or "arterie" in result.lower(),
          f"got: {result[:80]}")

    result2 = await p.handle("che capitale e' la germania", "chat_free", user_id)
    check("knowledge fallback: capitale germania -> Berlino",
          "Berlino" in result2 or "berlino" in result2.lower(),
          f"got: {result2[:80]}")


asyncio.run(test_knowledge_fallback_proactor())


# =====================================================================
# GROUP 8: MEMORY DIRECT RESPONSE
# =====================================================================

print("\n===== GROUP 8: Memory Direct Response =====")


async def test_memory_direct():
    """Identity questions return from memory without LLM, with MEMORY_DIRECT_RESPONSE log."""
    user_id = "test_mem_direct"
    await memory_brain.update_brain(user_id, "mi chiamo Paolo e vivo a Firenze")

    gpt_called = False

    async def spy_call(*args, **kwargs):
        nonlocal gpt_called
        gpt_called = True
        return None

    p = Proactor()
    with patch.object(llm_service, '_call_with_protection', spy_call):
        result = await p.handle("come mi chiamo", "chat_free", user_id)

    check("memory direct: contains Paolo", "Paolo" in result, f"got: {result[:80]}")
    check("memory direct: GPT NOT called", not gpt_called)

    gpt_called = False
    with patch.object(llm_service, '_call_with_protection', spy_call):
        result2 = await p.handle("dove vivo", "chat_free", user_id)

    check("memory direct: contains Firenze", "Firenze" in result2, f"got: {result2[:80]}")
    check("memory direct: GPT NOT called for city", not gpt_called)


asyncio.run(test_memory_direct())


# =====================================================================
# GROUP 9: EVOLUTION ENGINE MODEL
# =====================================================================

print("\n===== GROUP 9: Evolution Engine Model =====")

from core.evolution_engine import LLM_MODEL as EVO_MODEL, LLM_FALLBACK_MODEL as EVO_FALLBACK
check("evolution_engine: default model is gpt-4o-mini", EVO_MODEL == "gpt-4o-mini", f"got: {EVO_MODEL}")
check("evolution_engine: fallback model is gpt-4o-mini", EVO_FALLBACK == "gpt-4o-mini", f"got: {EVO_FALLBACK}")


# =====================================================================
# GROUP 10: LLM SERVICE ARCHITECTURE
# =====================================================================

print("\n===== GROUP 10: LLM Service Architecture =====")

ls_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core/llm_service.py")
with open(ls_path, "r", encoding="utf-8") as f:
    ls_src = f.read()

check("llm_service: model_selector function defined", "def model_selector" in ls_src)
check("llm_service: _call_with_protection method", "_call_with_protection" in ls_src)
check("llm_service: _deterministic_fallback method", "_deterministic_fallback" in ls_src)
check("llm_service: RateLimitError handled", "RateLimitError" in ls_src)
check("llm_service: LLM_RATE_LIMIT_RETRY log", "LLM_RATE_LIMIT_RETRY" in ls_src)
check("llm_service: LLM_AUTO_DOWNGRADE log", "LLM_AUTO_DOWNGRADE" in ls_src)
check("llm_service: LLM_MODEL_SELECTED log", "LLM_MODEL_SELECTED" in ls_src)
check("llm_service: asyncio.sleep for backoff", "asyncio.sleep" in ls_src)
check("llm_service: cost_optimized_v1 in init", "cost_optimized_v1" in ls_src)


# =====================================================================
# RESULTS
# =====================================================================
print(f"\n{'='*60}")
print(f"RISULTATI: {passed} passed, {failed} failed")
print(f"{'='*60}")

if failed > 0:
    print("\nFAILED - Ci sono test falliti")
    sys.exit(1)
else:
    print("\nALL PASSED")
    sys.exit(0)
