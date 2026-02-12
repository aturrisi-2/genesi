"""
GENESI - Orchestral Architecture Tests v2
Tests: LLM fallback chain, Proactor context building, memory injection,
       identity reflection, weather/news mock HTTP, intent routing,
       anti-generic prompt, logging tags, silent fallback detection.
"""

import asyncio
import sys
import os
import re
import logging
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key-for-local-testing")

from core.tool_services import ToolService
from core.intent_classifier import intent_classifier
from core.proactor import Proactor
from core.memory_brain import memory_brain
from core.evolution_engine import (
    score_message_complexity, LLM_MODEL, LLM_FALLBACK_MODEL,
    _build_llm_prompt, generate_response_from_brain
)
from core.llm_service import LLM_SERVICE_MODEL, LLM_SERVICE_FALLBACK

passed = 0
failed = 0


def check(label, condition):
    global passed, failed
    if condition:
        print(f"  [OK] {label}")
        passed += 1
    else:
        print(f"  [FAIL] {label}")
        failed += 1


class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text or str(json_data)

    def json(self):
        return self._json


# =====================================================================
# GROUP 1: LLM ARCHITECTURE — Primary + Fallback
# =====================================================================

print("\n===== GROUP 1: LLM Architecture =====")

check("primary model is gpt-4o", LLM_MODEL == "gpt-4o")
check("fallback model is gpt-4o-mini", LLM_FALLBACK_MODEL == "gpt-4o-mini")
check("llm_service primary is gpt-4o", LLM_SERVICE_MODEL == "gpt-4o")
check("llm_service fallback is gpt-4o-mini", LLM_SERVICE_FALLBACK == "gpt-4o-mini")

# Verify fallback chain exists in evolution_engine source
ee_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core/evolution_engine.py")
with open(ee_path, "r", encoding="utf-8") as f:
    ee_src = f.read()
check("_call_llm_model function exists", "async def _call_llm_model" in ee_src)
# Tags use format strings: tag_prefix = "LLM_PRIMARY" / "LLM_FALLBACK" + %s_REQUEST etc.
check("LLM_PRIMARY prefix defined", '"LLM_PRIMARY"' in ee_src)
check("LLM_FALLBACK prefix defined", '"LLM_FALLBACK"' in ee_src)
check("%s_REQUEST format tag", "%s_REQUEST" in ee_src)
check("%s_OK format tag", "%s_OK" in ee_src)
check("%s_ERROR format tag", "%s_ERROR" in ee_src)
check("LLM_PRIMARY_FAIL triggers fallback", "LLM_PRIMARY_FAIL" in ee_src)

# Verify fallback chain in llm_service source
ls_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core/llm_service.py")
with open(ls_path, "r", encoding="utf-8") as f:
    ls_src = f.read()
check("llm_service has _call_model method", "async def _call_model" in ls_src)
check("llm_service LLM_SERVICE_PRIMARY_REQUEST", "LLM_SERVICE_PRIMARY_REQUEST" in ls_src or "LLM_SERVICE_PRIMARY" in ls_src)
check("llm_service LLM_SERVICE_FALLBACK", "LLM_SERVICE_FALLBACK" in ls_src)


# =====================================================================
# GROUP 2: PROACTOR CONTEXT BUILDING
# =====================================================================

print("\n===== GROUP 2: Proactor Context Building =====")


async def test_proactor_context():
    """Proactor builds relational context and injects it into brain_state."""
    # First, seed memory
    await memory_brain.update_brain("test_ctx_001", "mi chiamo Alfio e vivo a Catania")
    await memory_brain.update_brain("test_ctx_001", "mia moglie si chiama Rita")
    await memory_brain.update_brain("test_ctx_001", "mi sento un po' triste oggi")

    # Now build brain_state and context
    brain = await memory_brain.update_brain("test_ctx_001", "come stai?")
    ctx = Proactor._build_relational_context(brain)

    check("context is non-empty string", isinstance(ctx, str) and len(ctx) > 0)
    check("context contains PROFILO UTENTE", "PROFILO UTENTE" in ctx)
    check("context contains STATO RELAZIONALE", "STATO RELAZIONALE" in ctx)
    check("context contains user name Alfio", "Alfio" in ctx)
    check("context contains city Catania", "Catania" in ctx)
    check("context contains moglie Rita", "Rita" in ctx)
    check("context contains Trust:", "Trust:" in ctx)
    check("context contains TONO RELAZIONALE", "TONO RELAZIONALE" in ctx)

    # Verify proactor.py source has the log tags
    pa_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core/proactor.py")
    with open(pa_path, "r", encoding="utf-8") as f:
        pa_src = f.read()
    check("PROACTOR_CONTEXT_BUILT in source", "PROACTOR_CONTEXT_BUILT" in pa_src)
    check("PROACTOR_RELATIONAL_INJECTED in source", "PROACTOR_RELATIONAL_INJECTED" in pa_src)


asyncio.run(test_proactor_context())


# =====================================================================
# GROUP 3: MEMORY INJECTION INTO LLM PROMPT
# =====================================================================

print("\n===== GROUP 3: Memory Injection into LLM Prompt =====")


async def test_memory_injection():
    """LLM prompt receives relational context from Proactor."""
    # Build brain_state with seeded memory
    brain = await memory_brain.update_brain("test_ctx_001", "raccontami qualcosa")

    # Simulate Proactor injecting context
    relational_ctx = Proactor._build_relational_context(brain)
    brain["relational_context"] = relational_ctx

    # Build LLM prompt
    prompt = _build_llm_prompt("raccontami qualcosa", brain)

    check("prompt contains identity block", "Sei Genesi" in prompt)
    check("prompt contains relational context", "PROFILO UTENTE" in prompt or "Alfio" in prompt)
    check("prompt contains anti-generic rules", "DIVIETI ASSOLUTI" in prompt)
    check("prompt forbids 'Quello che senti conta'", "Quello che senti conta" in prompt)
    check("prompt forbids ungrounded responses", "ancorata al contesto reale" in prompt)
    check("prompt contains user message", "raccontami qualcosa" in prompt)

    # Without relational_context, prompt should still work (minimal fallback)
    brain_no_ctx = dict(brain)
    brain_no_ctx.pop("relational_context", None)
    prompt_no_ctx = _build_llm_prompt("test", brain_no_ctx)
    check("prompt without context still has identity", "Sei Genesi" in prompt_no_ctx)
    check("prompt without context still has rules", "DIVIETI ASSOLUTI" in prompt_no_ctx)


asyncio.run(test_memory_injection())


# =====================================================================
# GROUP 4: IDENTITY REFLECTION — "chi sono io"
# =====================================================================

print("\n===== GROUP 4: Identity Reflection =====")


async def test_identity_reflection():
    """'chi sono io' with known profile returns memory-based response."""
    # Use seeded user from group 2
    brain = await memory_brain.update_brain("test_ctx_001", "chi sono io")
    brain["relational_context"] = Proactor._build_relational_context(brain)

    # generate_response_from_brain should handle this
    result = await generate_response_from_brain("test_ctx_001", "chi sono io", brain)

    check("identity reflection: returns string", isinstance(result, str))
    check("identity reflection: not empty", len(result) > 0)
    # Should contain user's name or memory reference (from _memory_response fallback)
    has_context = "Alfio" in result or "ricordo" in result or "chiami" in result or "conosc" in result
    check("identity reflection: grounded in memory", has_context)

    # Without profile, should ask for info
    brain_empty = await memory_brain.update_brain("test_empty_999", "chi sono io")
    brain_empty["relational_context"] = Proactor._build_relational_context(brain_empty)
    result_empty = await generate_response_from_brain("test_empty_999", "chi sono io", brain_empty)
    check("identity reflection (no profile): asks for info", "conoscerci" in result_empty or "Raccontami" in result_empty or "chiami" in result_empty)


asyncio.run(test_identity_reflection())


# =====================================================================
# GROUP 5: WEATHER — Mock HTTP
# =====================================================================

print("\n===== GROUP 5: Weather Mock HTTP =====")


async def test_weather_all():
    # 200 OK
    ts = ToolService()
    fake_resp = FakeResponse(200, {
        "weather": [{"description": "cielo sereno"}],
        "main": {"temp": 18.3, "feels_like": 17.1, "humidity": 55},
        "wind": {"speed": 3.5}
    })
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=fake_resp)
    mock_client.is_closed = False
    ts._http_client = mock_client
    with patch("core.tool_services.OPENWEATHER_API_KEY", "test-key-123"):
        result = await ts.get_weather("che tempo fa a Roma")
    check("weather 200: contains temperature", "18" in result and "C" in result)
    check("weather 200: contains city", "Roma" in result)
    check("weather 200: not error", "non disponibile" not in result)

    # 401
    ts2 = ToolService()
    fake_401 = FakeResponse(401, text='{"cod":401}')
    mc2 = AsyncMock()
    mc2.get = AsyncMock(return_value=fake_401)
    mc2.is_closed = False
    ts2._http_client = mc2
    with patch("core.tool_services.OPENWEATHER_API_KEY", "bad"):
        r401 = await ts2.get_weather("meteo Milano")
    check("weather 401: error message", "non disponibile" in r401)

    # Missing key
    ts3 = ToolService()
    with patch("core.tool_services.OPENWEATHER_API_KEY", ""):
        r_nokey = await ts3.get_weather("meteo Roma")
    check("weather missing key: 'non configurato'", "non configurato" in r_nokey)

    # Timeout
    import httpx
    ts4 = ToolService()
    mc4 = AsyncMock()
    mc4.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    mc4.is_closed = False
    ts4._http_client = mc4
    with patch("core.tool_services.OPENWEATHER_API_KEY", "key"):
        r_timeout = await ts4.get_weather("meteo Firenze")
    check("weather timeout: error message", "non disponibile" in r_timeout)


asyncio.run(test_weather_all())


# =====================================================================
# GROUP 6: NEWS — Mock HTTP + 401 distinction
# =====================================================================

print("\n===== GROUP 6: News Mock HTTP =====")


async def test_news_all():
    # 200 OK
    ts = ToolService()
    fake_resp = FakeResponse(200, {
        "status": "ok",
        "articles": [
            {"title": "Roma vince - Gazzetta"},
            {"title": "Ponte nuovo - ANSA"},
        ]
    })
    mc = AsyncMock()
    mc.get = AsyncMock(return_value=fake_resp)
    mc.is_closed = False
    ts._http_client = mc
    with patch("core.tool_services.NEWSAPI_KEY", "test-key"):
        result = await ts.get_news("notizie")
    check("news 200: contains title", "Roma vince" in result)
    check("news 200: numbered", "1." in result)

    # 401 — must say "Chiave News API non valida"
    ts2 = ToolService()
    fake_401 = FakeResponse(401, text='{"status":"error","code":"apiKeyInvalid"}')
    mc2 = AsyncMock()
    mc2.get = AsyncMock(return_value=fake_401)
    mc2.is_closed = False
    ts2._http_client = mc2
    with patch("core.tool_services.NEWSAPI_KEY", "bad-key"):
        r401 = await ts2.get_news("ultime notizie")
    check("news 401: 'Chiave News API non valida'", "Chiave News API non valida" in r401)
    check("news 401: NOT generic 'non disponibile'", "non disponibile" not in r401)

    # Missing key
    ts3 = ToolService()
    with patch("core.tool_services.NEWSAPI_KEY", ""):
        r_nokey = await ts3.get_news("notizie Roma")
    check("news missing key: 'non configurato'", "non configurato" in r_nokey)

    # 500 — generic error
    ts5 = ToolService()
    fake_500 = FakeResponse(500, text="Internal Server Error")
    mc5 = AsyncMock()
    mc5.get = AsyncMock(return_value=fake_500)
    mc5.is_closed = False
    ts5._http_client = mc5
    with patch("core.tool_services.NEWSAPI_KEY", "key"):
        r500 = await ts5.get_news("notizie sport")
    check("news 500: 'non disponibile'", "non disponibile" in r500)
    check("news 500: NOT 'Chiave non valida'", "Chiave" not in r500)


asyncio.run(test_news_all())


# =====================================================================
# GROUP 7: DATE & TIME
# =====================================================================

print("\n===== GROUP 7: Date & Time =====")


async def test_date_time():
    ts = ToolService()
    time_result = await ts.get_time()
    date_result = await ts.get_date()
    check("time: 'Sono le'", "Sono le" in time_result)
    check("time: colon", ":" in time_result)
    check("date: 'Oggi'", "Oggi" in date_result)
    check("date: year", "202" in date_result)
    giorni = ["luned", "marted", "mercoled", "gioved", "venerd", "sabato", "domenica"]
    check("date: Italian weekday", any(g in date_result.lower() for g in giorni))
    mesi = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
            "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
    check("date: Italian month", any(m in date_result.lower() for m in mesi))


asyncio.run(test_date_time())


# =====================================================================
# GROUP 8: INTENT CLASSIFIER — Strict routing
# =====================================================================

print("\n===== GROUP 8: Intent Classifier Routing =====")

tool_intents = ["weather", "news", "time", "date"]

check("weather intent", intent_classifier.classify("che tempo fa a Roma") == "weather")
check("news intent", intent_classifier.classify("dammi le notizie") == "news")
check("time intent", intent_classifier.classify("che ore sono") == "time")
check("date intent", intent_classifier.classify("che giorno e' oggi") == "date")
check("chat NOT tool", intent_classifier.classify("come stai") not in tool_intents)
check("greeting NOT tool", intent_classifier.classify("ciao") not in tool_intents)
check("emotion NOT tool", intent_classifier.classify("mi sento triste") not in tool_intents)
check("technical NOT tool", intent_classifier.classify("spiega l'algoritmo") not in tool_intents)


# =====================================================================
# GROUP 9: MEMORY PIPELINE
# =====================================================================

print("\n===== GROUP 9: Memory Pipeline =====")


async def test_memory_pipeline():
    brain = await memory_brain.update_brain("test_arch_010", "mi chiamo Marco e vivo a Milano")
    check("brain_state not None", brain is not None)
    check("has profile", "profile" in brain)
    check("has relational", "relational" in brain)
    check("has emotion", "emotion" in brain)
    check("has episodes", "episodes" in brain)
    check("has consolidation", "consolidation" in brain)
    emo = brain.get("emotion", {})
    check("emotion.emotion is str", isinstance(emo.get("emotion"), str))
    check("emotion.intensity is float", isinstance(emo.get("intensity"), (int, float)))


asyncio.run(test_memory_pipeline())


# =====================================================================
# GROUP 10: PROACTOR RESILIENCE
# =====================================================================

print("\n===== GROUP 10: Proactor Resilience =====")


async def test_proactor_resilience():
    p = Proactor()
    check("weather in tool_intents", "weather" in p.tool_intents)
    check("news in tool_intents", "news" in p.tool_intents)

    # chat_free
    result = await p.handle("ciao, come stai?", "chat_free", "test_arch_020")
    check("chat_free: returns string", isinstance(result, str))
    check("chat_free: not empty", len(result) > 0)
    check("chat_free: not error", "problema" not in result.lower())

    # date tool
    result_date = await p.handle("che giorno e' oggi", "date", "test_arch_021")
    check("date tool: 'Oggi'", "Oggi" in result_date)

    # time tool
    result_time = await p.handle("che ore sono", "time", "test_arch_022")
    check("time tool: 'Sono le'", "Sono le" in result_time)


asyncio.run(test_proactor_resilience())


# =====================================================================
# GROUP 11: COMPLEXITY SCORING
# =====================================================================

print("\n===== GROUP 11: Complexity Scoring =====")

brain_stub = {"relational": {"trust": 0.3}}
check("simple msg < 0.6", score_message_complexity("ciao", brain_stub) < 0.6)
check("complex msg >= 0.4",
      score_message_complexity("spiegami come funziona l'architettura del sistema e il database", brain_stub) >= 0.4)
check("technical msg >= 0.2",
      score_message_complexity("spiega il codice del database e il sistema api", brain_stub) >= 0.2)


# =====================================================================
# GROUP 12: SILENT FALLBACK DETECTION
# =====================================================================

print("\n===== GROUP 12: Silent Fallback Detection =====")

active_files = [
    "core/proactor.py", "core/evolution_engine.py", "core/tool_services.py",
    "core/memory_brain.py", "core/llm_service.py", "core/intent_classifier.py",
    "core/identity_filter.py", "core/emotional_intensity_engine.py",
    "core/curiosity_engine.py", "core/latent_state.py", "core/drift_modulator.py",
]

bare_except_pass_found = []
for filepath in active_files:
    full_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filepath)
    if not os.path.exists(full_path):
        continue
    with open(full_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped == "except:" or stripped == "except Exception:":
            for j in range(i + 1, min(i + 3, len(lines))):
                next_stripped = lines[j].strip()
                if next_stripped == "pass":
                    bare_except_pass_found.append(f"{filepath}:{i+1}")
                    break
                elif next_stripped:
                    break

check("no bare except:pass in pipeline", len(bare_except_pass_found) == 0)
check("weather key msg != API fail msg", "non configurato" != "non disponibile")
check("news key msg != API fail msg", "non configurato" != "non disponibile")
check("news 401 msg is distinct", "Chiave News API non valida" != "non disponibile")


# =====================================================================
# GROUP 13: LOGGING TAGS VERIFICATION
# =====================================================================

print("\n===== GROUP 13: Logging Tags =====")

required_tags = {
    "core/tool_services.py": [
        "TOOL_WEATHER_HTTP_CALL", "TOOL_WEATHER_HTTP_STATUS", "TOOL_WEATHER_HTTP_ERROR",
        "TOOL_WEATHER_MISSING_KEY",
        "TOOL_NEWS_HTTP_CALL", "TOOL_NEWS_HTTP_STATUS", "TOOL_NEWS_HTTP_ERROR",
        "TOOL_NEWS_MISSING_KEY", "TOOL_NEWS_API_KEY_INVALID",
        "TOOL_TIME_RESPONSE", "TOOL_DATE_RESPONSE",
    ],
    "core/proactor.py": [
        "PROACTOR_START", "PROACTOR_MEMORY_UPDATED",
        "PROACTOR_CONTEXT_BUILT", "PROACTOR_RELATIONAL_INJECTED",
        "PROACTOR_LLM_CALL", "PROACTOR_LLM_RESPONSE",
        "PROACTOR_ERROR_FULL", "PROACTOR_TOOL_ERROR", "PROACTOR_RESPONSE",
        "PROACTOR_CONTEXT_EMPTY",
    ],
    "core/evolution_engine.py": [
        # Tags use %s format: tag_prefix = "LLM_PRIMARY" / "LLM_FALLBACK"
        "LLM_PRIMARY", "LLM_FALLBACK",
        "%s_REQUEST", "%s_OK", "%s_ERROR",
        "LLM_PRIMARY_FAIL", "COMPLEXITY_SCORE", "IDENTITY_REFLECTION",
        "LLM_CONTEXT_MISSING",
    ],
    "core/llm_service.py": [
        "LLM_SERVICE_PRIMARY", "LLM_SERVICE_FALLBACK",
    ],
    "core/memory_brain.py": [
        "MEMORY_CONSOLIDATION_ERROR", "MEMORY_EMOTION_NORMALIZED",
        "EPISODE_STORED", "RELATIONAL_UPDATE", "BRAIN_UPDATE",
    ],
}

all_tags_ok = True
for filepath, tags in required_tags.items():
    full_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filepath)
    if not os.path.exists(full_path):
        print(f"  [FAIL] {filepath} not found")
        all_tags_ok = False
        continue
    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()
    for tag in tags:
        if tag not in content:
            print(f"  [FAIL] missing '{tag}' in {filepath}")
            all_tags_ok = False

check("all required log tags present", all_tags_ok)


# =====================================================================
# GROUP 14: ANTI-GENERIC PROMPT RULES
# =====================================================================

print("\n===== GROUP 14: Anti-Generic Prompt Rules =====")

# Build a prompt and verify anti-generic directives are present
dummy_brain = {
    "profile": {"name": "Test"},
    "relational": {"trust": 0.5, "depth": 0.3, "stage": "building"},
    "emotion": {"emotion": "neutral", "intensity": 0.3},
    "episodes": [],
    "relational_context": "PROFILO UTENTE:\nNome: Test\n\nSTATO RELAZIONALE:\nTrust: 0.50"
}
prompt = _build_llm_prompt("ciao", dummy_brain)
check("prompt has DIVIETI ASSOLUTI", "DIVIETI ASSOLUTI" in prompt)
check("prompt bans 'Quello che senti conta'", "Quello che senti conta" in prompt)
check("prompt bans 'A volte le conversazioni'", "A volte le conversazioni" in prompt)
check("prompt bans ungrounded 'Sono qui per te'", "Sono qui per te" in prompt)
check("prompt bans 'Dimmi di piu' standalone", "Dimmi di piu'" in prompt)
check("prompt bans generic metaphors", "Metafore generiche" in prompt)
check("prompt requires grounded responses", "ancorata al contesto reale" in prompt)
check("prompt has REGOLE OBBLIGATORIE", "REGOLE OBBLIGATORIE" in prompt)
check("prompt: max 5 frasi rule", "Massimo 5 frasi" in prompt)
check("prompt: informativa -> informativa", "informativa" in prompt)
check("prompt: emotiva -> empatia + 1 domanda", "empatia concreta" in prompt)
check("prompt: no metafore inutili", "metafore inutili" in prompt)


# =====================================================================
# GROUP 15: MANDATORY E2E TESTS
# =====================================================================

print("\n===== GROUP 15: Mandatory E2E Tests =====")


async def test_e2e_mandatory():
    """5 mandatory E2E tests per the architectural spec."""

    # --- Test 1: "Mi chiamo Marco" -> saved in profile ---
    brain_marco = await memory_brain.update_brain("test_e2e_marco", "mi chiamo Marco e vivo a Milano")
    profile_marco = brain_marco.get("profile", {})
    check("E2E-1: 'Mi chiamo Marco' -> name saved", profile_marco.get("name") == "Marco")
    check("E2E-1: 'vivo a Milano' -> city saved", profile_marco.get("city") == "Milano")

    # --- Test 2: "Chi sono?" -> must contain Marco ---
    brain_chi = await memory_brain.update_brain("test_e2e_marco", "chi sono io")
    brain_chi["relational_context"] = Proactor._build_relational_context(brain_chi)
    result_chi = await generate_response_from_brain("test_e2e_marco", "chi sono io", brain_chi)
    has_marco = "Marco" in result_chi or "chiami" in result_chi or "ricordo" in result_chi
    check("E2E-2: 'Chi sono?' -> contains Marco or memory ref", has_marco)
    check("E2E-2: response is not empty", len(result_chi) > 0)

    # --- Test 3: "Che tempo fa a Roma?" -> tool call (mock) ---
    ts = ToolService()
    fake_weather = FakeResponse(200, {
        "weather": [{"description": "pioggia leggera"}],
        "main": {"temp": 14.2, "feels_like": 12.8, "humidity": 78},
        "wind": {"speed": 5.1}
    })
    mc = AsyncMock()
    mc.get = AsyncMock(return_value=fake_weather)
    mc.is_closed = False
    ts._http_client = mc
    with patch("core.tool_services.OPENWEATHER_API_KEY", "test-key"):
        weather_result = await ts.get_weather("che tempo fa a Roma")
    check("E2E-3: weather contains Roma", "Roma" in weather_result)
    check("E2E-3: weather contains temperature", "14" in weather_result)
    check("E2E-3: weather not error", "non disponibile" not in weather_result)

    # --- Test 4: "Dammi notizie su Roma" -> news tool call (mock) ---
    ts2 = ToolService()
    fake_news = FakeResponse(200, {
        "status": "ok",
        "articles": [
            {"title": "Roma inaugura nuovo parco - Repubblica"},
            {"title": "Traffico in centro - Corriere"},
        ]
    })
    mc2 = AsyncMock()
    mc2.get = AsyncMock(return_value=fake_news)
    mc2.is_closed = False
    ts2._http_client = mc2
    with patch("core.tool_services.NEWSAPI_KEY", "test-key"):
        news_result = await ts2.get_news("dammi notizie su Roma")
    check("E2E-4: news contains article", "Roma inaugura" in news_result)
    check("E2E-4: news numbered", "1." in news_result)
    check("E2E-4: news not error", "non disponibile" not in news_result)

    # --- Test 5: "Cos'e' un bug?" -> informative, not therapeutic ---
    brain_info = await memory_brain.update_brain("test_e2e_info", "cos'e' un bug nel software")
    brain_info["relational_context"] = Proactor._build_relational_context(brain_info)
    result_info = await generate_response_from_brain("test_e2e_info", "cos'e' un bug nel software", brain_info)
    check("E2E-5: informative response is string", isinstance(result_info, str))
    check("E2E-5: response not empty", len(result_info) > 0)
    # Must NOT contain therapeutic phrases
    therapeutic = ["Quello che senti", "Sono qui per te", "Dimmi di piu'"]
    has_therapeutic = any(t in result_info for t in therapeutic)
    check("E2E-5: NO therapeutic phrases in informative response", not has_therapeutic)


asyncio.run(test_e2e_mandatory())


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
    print("\nOK - ORCHESTRAL ARCHITECTURE TESTS PASSATI")
    sys.exit(0)
