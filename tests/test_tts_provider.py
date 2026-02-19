import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch
from core.tts_provider import (
    PiperTTSProvider,
    EdgeTTSProvider,
    OpenAITTSProvider,
    get_tts_provider_for_intent,
    CONVERSATIONAL_INTENTS,
    INFORMATIONAL_INTENTS
)

class TestTTSRouting:
    def test_routing_conversational_returns_openai(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            provider = get_tts_provider_for_intent(intent="greeting")
            assert provider.name() == "openai"

    def test_routing_informational_returns_edge(self):
        provider = get_tts_provider_for_intent(intent="weather")
        assert provider.name() == "edge_tts"

    def test_routing_unknown_intent_defaults_conversational(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            provider = get_tts_provider_for_intent(intent="sconosciuto_xyz")
            assert provider.name() == "openai"

    def test_routing_relational_route_returns_openai(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            provider = get_tts_provider_for_intent(route="default_relational")
            assert provider.name() == "openai"

class TestTTSProviderNames:
    def test_piper_name(self):
        assert PiperTTSProvider().name() == "piper"

    def test_edge_name(self):
        assert EdgeTTSProvider().name() == "edge_tts"

    def test_openai_name(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            assert OpenAITTSProvider().name() == "openai"

class TestTTSProviderInstantiation:
    def test_piper_instantiates(self):
        assert PiperTTSProvider() is not None

    def test_edge_instantiates(self):
        assert EdgeTTSProvider() is not None

    def test_openai_instantiates_with_key(self):
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-key'}):
            assert OpenAITTSProvider() is not None

    def test_openai_fails_without_key(self):
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop('OPENAI_API_KEY', None)
            with pytest.raises(RuntimeError):
                OpenAITTSProvider()

class TestConversationalIntents:
    def test_greeting_is_conversational(self):
        assert "greeting" in CONVERSATIONAL_INTENTS

    def test_chat_free_is_conversational(self):
        assert "chat_free" in CONVERSATIONAL_INTENTS

    def test_weather_is_informational(self):
        assert "weather" in INFORMATIONAL_INTENTS

    def test_news_is_informational(self):
        assert "news" in INFORMATIONAL_INTENTS
