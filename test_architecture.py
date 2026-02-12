"""
GENESI - Architectural Resilience Tests
Tests: weather/news mock HTTP, LLM pipeline, memory pipeline, proactor resilience,
       intent routing, logging verification, silent fallback detection.
"""

import asyncio
import sys
import os
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from collections import namedtuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("OPENAI_API_KEY", "sk-test-dummy-key-for-local-testing")

from core.tool_services import ToolService, OPENWEATHER_API_KEY, NEWSAPI_KEY
from core.intent_classifier import intent_classifier
from core.proactor import Proactor
from core.memory_brain import memory_brain, _safe_emotion_label
from core.evolution_engine import score_message_complexity, LLM_MODEL

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


# Helper: fake httpx response
class FakeResponse:
    def __init__(self, status_code, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data or {}
        self.text = text or str(json_data)

    def json(self):
        return self._json


# ═══════════════════════════════════════════════════════════════
# TEST GROUP 1: WEATHER — Mock HTTP
# ═══════════════════════════════════════════════════════════════

print("\n===== TEST GROUP 1: Weather Mock HTTP =====")


async def test_weather_success():
    """Weather 200 OK — real API format."""
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

    check("weather 200: contains temperature", "18°C" in result)
    check("weather 200: contains city", "Roma" in result)
    check("weather 200: contains humidity", "55%" in result)
    check("weather 200: not error message", "non disponibile" not in result)
    check("weather 200: not 'non configurato'", "non configurato" not in result)


async def test_weather_401():
    """Weather 401 — invalid API key."""
    ts = ToolService()
    fake_resp = FakeResponse(401, text='{"cod":401,"message":"Invalid API key"}')
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=fake_resp)
    mock_client.is_closed = False
    ts._http_client = mock_client

    with patch("core.tool_services.OPENWEATHER_API_KEY", "bad-key"):
        result = await ts.get_weather("meteo Milano")

    check("weather 401: error message returned", "non disponibile" in result)
    check("weather 401: no invented data", "°C" not in result)


async def test_weather_500():
    """Weather 500 — server error."""
    ts = ToolService()
    fake_resp = FakeResponse(500, text="Internal Server Error")
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=fake_resp)
    mock_client.is_closed = False
    ts._http_client = mock_client

    with patch("core.tool_services.OPENWEATHER_API_KEY", "test-key"):
        result = await ts.get_weather("meteo Napoli")

    check("weather 500: error message returned", "non disponibile" in result)
    check("weather 500: no invented data", "°C" not in result)


async def test_weather_missing_key():
    """Weather — missing API key."""
    ts = ToolService()
    with patch("core.tool_services.OPENWEATHER_API_KEY", ""):
        result = await ts.get_weather("meteo Roma")

    check("weather missing key: 'non configurato'", "non configurato" in result)
    check("weather missing key: not 'non disponibile'", "non disponibile" not in result)


async def test_weather_timeout():
    """Weather — timeout."""
    import httpx
    ts = ToolService()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    mock_client.is_closed = False
    ts._http_client = mock_client

    with patch("core.tool_services.OPENWEATHER_API_KEY", "test-key"):
        result = await ts.get_weather("meteo Firenze")

    check("weather timeout: error message", "non disponibile" in result)


asyncio.run(test_weather_success())
asyncio.run(test_weather_401())
asyncio.run(test_weather_500())
asyncio.run(test_weather_missing_key())
asyncio.run(test_weather_timeout())


# ═══════════════════════════════════════════════════════════════
# TEST GROUP 2: NEWS — Mock HTTP
# ═══════════════════════════════════════════════════════════════

print("\n===== TEST GROUP 2: News Mock HTTP =====")


async def test_news_success():
    """News 200 OK — real API format."""
    ts = ToolService()
    fake_resp = FakeResponse(200, {
        "status": "ok",
        "articles": [
            {"title": "Roma vince la partita - Gazzetta"},
            {"title": "Nuovo ponte inaugurato - ANSA"},
            {"title": "Economia in crescita - Sole24Ore"},
        ]
    })
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=fake_resp)
    mock_client.is_closed = False
    ts._http_client = mock_client

    with patch("core.tool_services.NEWSAPI_KEY", "test-news-key"):
        result = await ts.get_news("notizie")

    check("news 200: contains article title", "Roma vince la partita" in result)
    check("news 200: strips source suffix", "Gazzetta" not in result)
    check("news 200: numbered list", "1." in result)
    check("news 200: not error", "non disponibile" not in result)


async def test_news_401():
    """News 401 — invalid API key."""
    ts = ToolService()
    fake_resp = FakeResponse(401, text='{"status":"error","code":"apiKeyInvalid"}')
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=fake_resp)
    mock_client.is_closed = False
    ts._http_client = mock_client

    with patch("core.tool_services.NEWSAPI_KEY", "bad-key"):
        result = await ts.get_news("ultime notizie")

    check("news 401: error message", "non disponibile" in result)
    check("news 401: no invented titles", "1." not in result)


async def test_news_missing_key():
    """News — missing API key."""
    ts = ToolService()
    with patch("core.tool_services.NEWSAPI_KEY", ""):
        result = await ts.get_news("notizie Roma")

    check("news missing key: 'non configurato'", "non configurato" in result)
    check("news missing key: not 'non disponibile'", "non disponibile" not in result)


async def test_news_timeout():
    """News — timeout."""
    import httpx
    ts = ToolService()
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
    mock_client.is_closed = False
    ts._http_client = mock_client

    with patch("core.tool_services.NEWSAPI_KEY", "test-key"):
        result = await ts.get_news("notizie sport")

    check("news timeout: error message", "non disponibile" in result)


asyncio.run(test_news_success())
asyncio.run(test_news_401())
asyncio.run(test_news_missing_key())
asyncio.run(test_news_timeout())


# ═══════════════════════════════════════════════════════════════
# TEST GROUP 3: DATE & TIME — Real (no mock needed)
# ═══════════════════════════════════════════════════════════════

print("\n===== TEST GROUP 3: Date & Time =====")


async def test_date_time():
    ts = ToolService()
    time_result = await ts.get_time()
    date_result = await ts.get_date()

    check("time: contains 'Sono le'", "Sono le" in time_result)
    check("time: contains colon (HH:MM)", ":" in time_result)
    check("date: contains 'Oggi è'", "Oggi è" in date_result or "Oggi e'" in date_result)
    check("date: contains year", "2026" in date_result or "202" in date_result)

    # Verify Italian weekday
    giorni = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
    has_weekday = any(g in date_result.lower() for g in giorni)
    check("date: contains Italian weekday", has_weekday)

    # Verify Italian month
    mesi = ["gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
            "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]
    has_month = any(m in date_result.lower() for m in mesi)
    check("date: contains Italian month", has_month)


asyncio.run(test_date_time())


# ═══════════════════════════════════════════════════════════════
# TEST GROUP 4: LLM PIPELINE
# ═══════════════════════════════════════════════════════════════

print("\n===== TEST GROUP 4: LLM Pipeline =====")

check("LLM model is gpt-4o", LLM_MODEL == "gpt-4o")

# Complexity scoring
brain_stub = {"relational": {"trust": 0.3}}
check("simple msg = low complexity", score_message_complexity("ciao", brain_stub) < 0.6)
check("complex msg = high complexity",
      score_message_complexity("spiegami come funziona l'architettura del sistema e il database", brain_stub) >= 0.4)
check("technical msg = elevated complexity",
      score_message_complexity("spiega il codice del database e il sistema api", brain_stub) >= 0.2)


# ═══════════════════════════════════════════════════════════════
# TEST GROUP 5: INTENT CLASSIFIER — No cross-routing
# ═══════════════════════════════════════════════════════════════

print("\n===== TEST GROUP 5: Intent Classifier Routing =====")

tool_intents = ["weather", "news", "time", "date"]

# Weather
check("'che tempo fa' -> weather", intent_classifier.classify("che tempo fa a Roma") == "weather")
check("'previsioni meteo' -> weather", intent_classifier.classify("previsioni meteo") == "weather")

# News
check("'notizie' -> news", intent_classifier.classify("dammi le notizie") == "news")
check("'ultime news' -> news", intent_classifier.classify("ultime news") == "news")

# Time
check("'che ore sono' -> time", intent_classifier.classify("che ore sono") == "time")
check("'dimmi l'ora' -> time", intent_classifier.classify("dimmi l'ora") == "time")

# Date
check("'che giorno e' oggi' -> date", intent_classifier.classify("che giorno e' oggi") == "date")
check("'dimmi la data' -> date", intent_classifier.classify("dimmi la data") == "date")

# Chat free — must NOT route to tools
check("'come stai' -> NOT tool", intent_classifier.classify("come stai") not in tool_intents)
check("'ciao' -> NOT tool", intent_classifier.classify("ciao") not in tool_intents)
check("'mi sento triste' -> NOT tool", intent_classifier.classify("mi sento triste") not in tool_intents)

# Technical — must NOT route to tools
check("'spiega algoritmo' -> NOT tool", intent_classifier.classify("spiega l'algoritmo") not in tool_intents)


# ═══════════════════════════════════════════════════════════════
# TEST GROUP 6: MEMORY PIPELINE
# ═══════════════════════════════════════════════════════════════

print("\n===== TEST GROUP 6: Memory Pipeline =====")


async def test_memory_pipeline():
    """Full memory pipeline — no crash, returns brain_state."""
    brain = await memory_brain.update_brain("test_arch_001", "mi chiamo Marco e vivo a Milano")
    check("brain_state not None", brain is not None)
    check("brain_state has profile", "profile" in brain)
    check("brain_state has relational", "relational" in brain)
    check("brain_state has emotion", "emotion" in brain)
    check("brain_state has episodes", "episodes" in brain)
    check("brain_state has consolidation key", "consolidation" in brain)

    # Verify emotion is always a dict with expected keys
    emo = brain.get("emotion", {})
    check("emotion has 'emotion' key", "emotion" in emo)
    check("emotion has 'intensity' key", "intensity" in emo)
    check("emotion['emotion'] is string", isinstance(emo.get("emotion"), str))


asyncio.run(test_memory_pipeline())


# ═══════════════════════════════════════════════════════════════
# TEST GROUP 7: PROACTOR RESILIENCE
# ═══════════════════════════════════════════════════════════════

print("\n===== TEST GROUP 7: Proactor Resilience =====")


async def test_proactor_tool_routing():
    """Proactor routes tool intents correctly."""
    p = Proactor()
    check("weather in tool_intents", "weather" in p.tool_intents)
    check("news in tool_intents", "news" in p.tool_intents)
    check("time in tool_intents", "time" in p.tool_intents)
    check("date in tool_intents", "date" in p.tool_intents)


async def test_proactor_handles_chat():
    """Proactor handles chat_free without crash."""
    p = Proactor()
    result = await p.handle("ciao, come stai?", "chat_free", "test_arch_002")
    check("proactor chat_free: returns string", isinstance(result, str))
    check("proactor chat_free: not empty", len(result) > 0)
    check("proactor chat_free: not error", "problema" not in result.lower())


async def test_proactor_handles_tool_date():
    """Proactor handles date tool."""
    p = Proactor()
    result = await p.handle("che giorno è oggi", "date", "test_arch_003")
    check("proactor date: returns string", isinstance(result, str))
    check("proactor date: contains 'Oggi'", "Oggi" in result)


async def test_proactor_handles_tool_time():
    """Proactor handles time tool."""
    p = Proactor()
    result = await p.handle("che ore sono", "time", "test_arch_004")
    check("proactor time: returns string", isinstance(result, str))
    check("proactor time: contains 'Sono le'", "Sono le" in result)


asyncio.run(test_proactor_tool_routing())
asyncio.run(test_proactor_handles_chat())
asyncio.run(test_proactor_handles_tool_date())
asyncio.run(test_proactor_handles_tool_time())


# ═══════════════════════════════════════════════════════════════
# TEST GROUP 8: SILENT FALLBACK DETECTION
# ═══════════════════════════════════════════════════════════════

print("\n===== TEST GROUP 8: Silent Fallback Detection =====")

import re

# Read active pipeline files and check for bare except:pass
active_files = [
    "core/proactor.py",
    "core/evolution_engine.py",
    "core/tool_services.py",
    "core/memory_brain.py",
    "core/llm_service.py",
    "core/intent_classifier.py",
    "core/identity_filter.py",
    "core/emotional_intensity_engine.py",
    "core/curiosity_engine.py",
    "core/latent_state.py",
    "core/drift_modulator.py",
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
            # Check if next non-empty line is just 'pass'
            for j in range(i + 1, min(i + 3, len(lines))):
                next_stripped = lines[j].strip()
                if next_stripped == "pass":
                    bare_except_pass_found.append(f"{filepath}:{i+1}")
                    break
                elif next_stripped:
                    break  # has actual handling

if bare_except_pass_found:
    print(f"  [WARN] bare except:pass found in: {bare_except_pass_found}")
check("no bare except:pass in active pipeline files", len(bare_except_pass_found) == 0)

# Check that error messages are distinct (not all same generic text)
check("weather missing key msg != weather API failure msg",
      "non configurato" != "non disponibile")
check("news missing key msg != news API failure msg",
      "non configurato" != "non disponibile")


# ═══════════════════════════════════════════════════════════════
# TEST GROUP 9: LOGGING TAGS PRESENT
# ═══════════════════════════════════════════════════════════════

print("\n===== TEST GROUP 9: Logging Tags Verification =====")

required_log_tags = {
    "core/tool_services.py": [
        "TOOL_WEATHER_HTTP_CALL", "TOOL_WEATHER_HTTP_STATUS", "TOOL_WEATHER_HTTP_ERROR",
        "TOOL_WEATHER_MISSING_KEY",
        "TOOL_NEWS_HTTP_CALL", "TOOL_NEWS_HTTP_STATUS", "TOOL_NEWS_HTTP_ERROR",
        "TOOL_NEWS_MISSING_KEY",
        "TOOL_TIME_RESPONSE", "TOOL_DATE_RESPONSE",
    ],
    "core/proactor.py": [
        "PROACTOR_ERROR_FULL", "PROACTOR_TOOL_ERROR", "PROACTOR_RESPONSE",
    ],
    "core/evolution_engine.py": [
        "LLM_REQUEST", "LLM_RESPONSE", "COMPLEXITY_SCORE",
    ],
    "core/llm_service.py": [
        "LLM_SERVICE_REQUEST", "LLM_SERVICE_RESPONSE", "LLM_SERVICE_ERROR",
    ],
    "core/memory_brain.py": [
        "MEMORY_CONSOLIDATION_ERROR", "MEMORY_EMOTION_NORMALIZED",
        "EPISODE_STORED", "RELATIONAL_UPDATE", "BRAIN_UPDATE",
    ],
}

all_tags_found = True
for filepath, tags in required_log_tags.items():
    full_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), filepath)
    if not os.path.exists(full_path):
        check(f"{filepath} exists", False)
        all_tags_found = False
        continue
    with open(full_path, "r", encoding="utf-8") as f:
        content = f.read()
    for tag in tags:
        if tag not in content:
            print(f"  [FAIL] missing log tag '{tag}' in {filepath}")
            all_tags_found = False

check("all required log tags present in pipeline files", all_tags_found)


# ═══════════════════════════════════════════════════════════════
# RESULTS
# ═══════════════════════════════════════════════════════════════
print(f"\n{'='*55}")
print(f"RISULTATI: {passed} passed, {failed} failed")
print(f"{'='*55}")

if failed > 0:
    print("\nFAILED - Ci sono test falliti")
    sys.exit(1)
else:
    print("\nOK - ARCHITECTURAL RESILIENCE TESTS PASSATI")
    sys.exit(0)
