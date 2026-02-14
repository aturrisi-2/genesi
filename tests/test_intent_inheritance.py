"""
Tests for Intent Inheritance — geographic follow-up detection.
Covers: is_geo_followup, resolve_inherited_intent, strong intent protection.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from core.tool_context import (
    is_geo_followup,
    resolve_inherited_intent,
    save_tool_context,
    get_tool_context,
    _tool_contexts,
    INHERITABLE_INTENTS,
)


class TestIsGeoFollowup:
    """Test geographic follow-up pattern detection."""

    def test_e_a_city(self):
        assert is_geo_followup("e a Milano?") is True

    def test_e_per_city(self):
        assert is_geo_followup("e per Napoli?") is True

    def test_a_city_capitalized(self):
        assert is_geo_followup("a Roma") is True

    def test_bare_city_name(self):
        assert is_geo_followup("Firenze") is True

    def test_bare_compound_city(self):
        assert is_geo_followup("San Lazzaro") is True

    def test_e_city(self):
        assert is_geo_followup("e Bologna?") is True

    def test_anche_a_city(self):
        assert is_geo_followup("anche a Torino") is True

    def test_pure_a_city(self):
        assert is_geo_followup("pure a Genova") is True

    def test_long_message_rejected(self):
        assert is_geo_followup("vorrei sapere che tempo fa a Milano domani pomeriggio") is False

    def test_generic_question_rejected(self):
        assert is_geo_followup("come stai oggi?") is False

    def test_empty_rejected(self):
        assert is_geo_followup("") is False

    def test_six_words_rejected(self):
        assert is_geo_followup("dimmi il meteo per la città") is False

    def test_five_words_accepted(self):
        assert is_geo_followup("e a Castel del Rio") is True

    def test_di_city(self):
        assert is_geo_followup("di Lugano") is True

    def test_in_city(self):
        assert is_geo_followup("in Svizzera") is True


class TestResolveInheritedIntent:
    """Test intent inheritance logic."""

    def setup_method(self):
        _tool_contexts.clear()

    def test_inherits_weather(self):
        save_tool_context("u1", "weather", city="Roma")
        result = resolve_inherited_intent("u1", "e a Milano?", "relazionale")
        assert result == "weather"

    def test_inherits_news(self):
        save_tool_context("u1", "news")
        result = resolve_inherited_intent("u1", "e a Napoli?", "relazionale")
        assert result == "news"

    def test_no_context_returns_none(self):
        result = resolve_inherited_intent("u1", "e a Milano?", None)
        assert result is None

    def test_non_inheritable_last_intent(self):
        save_tool_context("u1", "time")
        result = resolve_inherited_intent("u1", "e a Milano?", None)
        assert result is None

    def test_strong_intent_not_overridden(self):
        save_tool_context("u1", "weather", city="Roma")
        result = resolve_inherited_intent("u1", "e a Milano?", "identity")
        assert result is None

    def test_time_intent_not_overridden(self):
        save_tool_context("u1", "weather", city="Roma")
        result = resolve_inherited_intent("u1", "e a Milano?", "time")
        assert result is None

    def test_date_intent_not_overridden(self):
        save_tool_context("u1", "weather", city="Roma")
        result = resolve_inherited_intent("u1", "e a Milano?", "date")
        assert result is None

    def test_already_weather_no_double_inherit(self):
        save_tool_context("u1", "weather", city="Roma")
        result = resolve_inherited_intent("u1", "e a Milano?", "weather")
        assert result is None

    def test_already_news_no_double_inherit(self):
        save_tool_context("u1", "news")
        result = resolve_inherited_intent("u1", "e a Napoli?", "news")
        assert result is None

    def test_non_geo_message_no_inherit(self):
        save_tool_context("u1", "weather", city="Roma")
        result = resolve_inherited_intent("u1", "come stai?", None)
        assert result is None

    def test_long_message_no_inherit(self):
        save_tool_context("u1", "weather", city="Roma")
        result = resolve_inherited_intent("u1", "vorrei sapere il meteo per domani a Milano", None)
        assert result is None

    def test_bare_city_inherits(self):
        save_tool_context("u1", "weather", city="Roma")
        result = resolve_inherited_intent("u1", "Firenze", None)
        assert result == "weather"

    def test_tecnica_not_overridden(self):
        save_tool_context("u1", "weather", city="Roma")
        result = resolve_inherited_intent("u1", "e a Milano?", "tecnica")
        assert result is None

    def test_debug_not_overridden(self):
        save_tool_context("u1", "weather", city="Roma")
        result = resolve_inherited_intent("u1", "e a Milano?", "debug")
        assert result is None
