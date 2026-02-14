"""
TEST NARRATIVE COHERENCE - Genesi
Tests for FASE 1-7: preference split, no-template, no-loop,
narrative continuity, tool weather follow-up.
"""

import pytest
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ═══════════════════════════════════════════════════════════════
# TEST 1: Preference separation music/food/general (FASE 1)
# ═══════════════════════════════════════════════════════════════

class TestPreferenceSeparation:
    """FASE 1: preferences.music / preferences.food / preferences.general"""

    def setup_method(self):
        from core.cognitive_memory_engine import CognitiveMemoryEngine
        self.engine = CognitiveMemoryEngine()

    def test_music_preference_extracted(self):
        result = self.engine._extract_preference("mi piace la musica elettronica")
        assert result is not None
        assert result[0] == "music"
        assert "elettronica" in result[1]

    def test_music_genre_direct(self):
        result = self.engine._extract_preference("mi piace il jazz")
        assert result is not None
        assert result[0] == "music"
        assert "jazz" in result[1]

    def test_music_ascolto(self):
        result = self.engine._extract_preference("ascolto il rock")
        assert result is not None
        assert result[0] == "music"
        assert "rock" in result[1]

    def test_food_preference_mangiare(self):
        result = self.engine._extract_preference("mi piace mangiare la pizza")
        assert result is not None
        assert result[0] == "food"
        assert "pizza" in result[1]

    def test_food_preference_frutto(self):
        result = self.engine._extract_preference("il mio frutto preferito sono le banane")
        assert result is not None
        assert result[0] == "food"
        assert "banane" in result[1]

    def test_food_direct_match(self):
        result = self.engine._extract_preference("mi piacciono le banane")
        assert result is not None
        assert result[0] == "food"
        assert "banane" in result[1]

    def test_general_preference(self):
        result = self.engine._extract_preference("mi piace molto leggere")
        assert result is not None
        assert result[0] == "general"
        assert "leggere" in result[1]

    def test_no_preference_in_greeting(self):
        result = self.engine._extract_preference("ciao come stai")
        assert result is None

    def test_preference_stored_in_profile(self):
        profile = {}
        asyncio.run(self.engine.evaluate_event("test_user", "mi piace la musica elettronica", profile))
        assert "preferences" in profile
        assert isinstance(profile["preferences"], dict)
        assert "music" in profile["preferences"]
        assert "elettronica" in profile["preferences"]["music"]

    def test_music_and_food_separate(self):
        profile = {}
        asyncio.run(self.engine.evaluate_event("test_user", "mi piace la musica elettronica", profile))
        asyncio.run(self.engine.evaluate_event("test_user", "mi piacciono le banane", profile))
        prefs = profile.get("preferences", {})
        assert "music" in prefs
        assert "food" in prefs
        assert "elettronica" in prefs["music"]
        assert "banane" in prefs["food"]


# ═══════════════════════════════════════════════════════════════
# TEST 2: No-template filter (FASE 2 + FASE 6)
# ═══════════════════════════════════════════════════════════════

class TestNoTemplate:
    """FASE 2: blacklisted template phrases are stripped from responses."""

    def test_capisco_stripped(self):
        from core.response_filter import filter_response
        result = filter_response("Capisco, deve essere difficile.", "test")
        assert "capisco," not in result.lower()

    def test_va_bene_stripped(self):
        from core.response_filter import filter_response
        result = filter_response("Va bene, parliamone.", "test_vb")
        assert not result.lower().startswith("va bene,")

    def test_sono_qui_stripped(self):
        from core.response_filter import filter_response
        result = filter_response("Sono qui.", "test_sq")
        # "Sono qui." alone should be stripped
        assert result == "" or "sono qui." not in result.lower()

    def test_non_sono_programmato_stripped(self):
        from core.response_filter import filter_response
        result = filter_response("Non sono programmato per questo.", "test_nsp")
        assert "programmato" not in result.lower()

    def test_non_ho_opinioni_stripped(self):
        from core.response_filter import filter_response
        result = filter_response("Non ho opinioni su questo argomento.", "test_nho")
        assert "non ho opinioni" not in result.lower()

    def test_non_ho_accesso_stripped(self):
        from core.response_filter import filter_response
        result = filter_response("Non ho accesso a queste informazioni.", "test_nha")
        assert "non ho accesso" not in result.lower()

    def test_clean_response_passes(self):
        from core.response_filter import filter_response
        result = filter_response("Che giornata pesante.", "test_clean")
        assert result == "Che giornata pesante."

    def test_motivational_stripped(self):
        from core.response_filter import filter_response
        result = filter_response("Ce la puoi fare, non arrenderti!", "test_mot")
        assert "ce la puoi fare" not in result.lower()
        assert "non arrenderti" not in result.lower()

    def test_contains_blacklisted_function(self):
        from core.response_filter import contains_blacklisted
        assert contains_blacklisted("Capisco, è difficile") is True
        assert contains_blacklisted("Sono programmato per aiutarti") is True
        assert contains_blacklisted("Che giornata") is False


# ═══════════════════════════════════════════════════════════════
# TEST 3: No-loop (FASE 4)
# ═══════════════════════════════════════════════════════════════

class TestNoLoop:
    """FASE 4: identical consecutive responses are blocked."""

    def test_first_response_passes(self):
        from core.response_filter import filter_response, _last_responses, _repeat_counts
        uid = "loop_test_1"
        _last_responses.pop(uid, None)
        _repeat_counts.pop(uid, None)
        result = filter_response("Ciao, come stai?", uid)
        assert result == "Ciao, come stai?"

    def test_identical_response_blocked(self):
        from core.response_filter import filter_response, _last_responses, _repeat_counts
        uid = "loop_test_2"
        _last_responses.pop(uid, None)
        _repeat_counts.pop(uid, None)
        r1 = filter_response("Ciao, come stai?", uid)
        assert r1 == "Ciao, come stai?"
        r2 = filter_response("Ciao, come stai?", uid)
        assert r2 == ""  # Blocked — empty signals regeneration

    def test_different_response_passes(self):
        from core.response_filter import filter_response, _last_responses, _repeat_counts
        uid = "loop_test_3"
        _last_responses.pop(uid, None)
        _repeat_counts.pop(uid, None)
        r1 = filter_response("Ciao, come stai?", uid)
        assert r1 == "Ciao, come stai?"
        r2 = filter_response("Tutto bene, grazie.", uid)
        assert r2 == "Tutto bene, grazie."


# ═══════════════════════════════════════════════════════════════
# TEST 4: Narrative continuity "stanco / non dormito" (FASE 3)
# ═══════════════════════════════════════════════════════════════

class TestNarrativeContinuity:
    """FASE 3: semantically related messages trigger continuity directive."""

    def test_stanco_non_dormito_linked(self):
        from core.context_assembler import _detect_narrative_continuity
        history = [{"user_message": "sono stanco"}]
        result = _detect_narrative_continuity("non ho dormito", history)
        assert "CONTINUITA' NARRATIVA OBBLIGATORIA" in result
        assert "stanchezza" in result

    def test_triste_piango_linked(self):
        from core.context_assembler import _detect_narrative_continuity
        history = [{"user_message": "sono triste"}]
        result = _detect_narrative_continuity("piango spesso", history)
        assert "CONTINUITA' NARRATIVA OBBLIGATORIA" in result
        assert "tristezza" in result

    def test_unrelated_messages_no_continuity(self):
        from core.context_assembler import _detect_narrative_continuity
        history = [{"user_message": "che tempo fa"}]
        result = _detect_narrative_continuity("mi piace la pizza", history)
        assert result == ""

    def test_empty_history_no_continuity(self):
        from core.context_assembler import _detect_narrative_continuity
        result = _detect_narrative_continuity("sono stanco", [])
        assert result == ""

    def test_lavoro_colleghi_linked(self):
        from core.context_assembler import _detect_narrative_continuity
        history = [{"user_message": "il lavoro mi stressa"}]
        result = _detect_narrative_continuity("il mio capo è insopportabile", history)
        assert "CONTINUITA' NARRATIVA OBBLIGATORIA" in result
        assert "lavoro" in result

    def test_ansia_preoccupazione_linked(self):
        from core.context_assembler import _detect_narrative_continuity
        history = [{"user_message": "sono ansioso"}]
        result = _detect_narrative_continuity("ho paura di tutto", history)
        assert "CONTINUITA' NARRATIVA OBBLIGATORIA" in result
        assert "ansia" in result


# ═══════════════════════════════════════════════════════════════
# TEST 5: Tool weather follow-up (FASE 5)
# ═══════════════════════════════════════════════════════════════

class TestToolWeatherFollowUp:
    """FASE 5: tool context memory for elliptical weather follow-ups."""

    def test_save_and_get_context(self):
        from core.tool_context import save_tool_context, get_tool_context
        save_tool_context("user_wx", "weather", city="Roma")
        ctx = get_tool_context("user_wx")
        assert ctx is not None
        assert ctx["intent"] == "weather"
        assert ctx["city"] == "Roma"

    def test_elliptical_detection(self):
        from core.tool_context import is_elliptical_weather_followup
        assert is_elliptical_weather_followup("e domani?") is True
        assert is_elliptical_weather_followup("e lì vicino?") is True
        assert is_elliptical_weather_followup("e stasera?") is True
        assert is_elliptical_weather_followup("ciao") is False
        assert is_elliptical_weather_followup("che tempo fa") is False

    def test_resolve_city_after_weather(self):
        from core.tool_context import save_tool_context, resolve_elliptical_city
        save_tool_context("user_resolve", "weather", city="Milano")
        city = resolve_elliptical_city("user_resolve", "e domani?")
        assert city == "Milano"

    def test_resolve_city_no_context(self):
        from core.tool_context import resolve_elliptical_city
        city = resolve_elliptical_city("user_no_ctx", "e domani?")
        assert city is None

    def test_resolve_city_wrong_intent(self):
        from core.tool_context import save_tool_context, resolve_elliptical_city
        save_tool_context("user_news", "news", topic="sport")
        city = resolve_elliptical_city("user_news", "e domani?")
        assert city is None

    def test_non_elliptical_no_resolve(self):
        from core.tool_context import save_tool_context, resolve_elliptical_city
        save_tool_context("user_ne", "weather", city="Torino")
        city = resolve_elliptical_city("user_ne", "ciao come stai")
        assert city is None


# ═══════════════════════════════════════════════════════════════
# TEST 6: Context assembler preference rendering (FASE 1)
# ═══════════════════════════════════════════════════════════════

class TestContextAssemblerPreferences:
    """FASE 1: preferences rendered as separate categories, not flat list."""

    def test_categorized_preferences_rendered_separately(self):
        from core.context_assembler import ContextAssembler
        assembler = ContextAssembler(None, None)
        profile = {
            "name": "Marco",
            "preferences": {
                "music": ["elettronica"],
                "food": ["banane"],
                "general": ["leggere"]
            }
        }
        summary = assembler._summarize_profile(profile)
        assert "Musica preferita: elettronica" in summary
        assert "Cibo preferito: banane" in summary
        assert "Preferenze: leggere" in summary
        # Must NOT have a flat mixed list
        assert "banane, elettronica" not in summary
        assert "elettronica, banane" not in summary

    def test_legacy_flat_preferences_still_work(self):
        from core.context_assembler import ContextAssembler
        assembler = ContextAssembler(None, None)
        profile = {
            "name": "Luca",
            "preferences": ["calcio", "cinema"]
        }
        summary = assembler._summarize_profile(profile)
        assert "Preferenze: calcio, cinema" in summary

    def test_empty_preferences_no_crash(self):
        from core.context_assembler import ContextAssembler
        assembler = ContextAssembler(None, None)
        profile = {"name": "Anna", "preferences": {}}
        summary = assembler._summarize_profile(profile)
        assert "Anna" in summary
        assert "Preferenze" not in summary
        assert "Musica" not in summary
