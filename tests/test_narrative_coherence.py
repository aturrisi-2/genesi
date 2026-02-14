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


# ═══════════════════════════════════════════════════════════════
# TEST 7: Weather forecast detection (new)
# ═══════════════════════════════════════════════════════════════

class TestWeatherForecast:
    """Weather: forecast keyword detection and worldwide city extraction."""

    def setup_method(self):
        from core.tool_services import ToolService
        self.ts = ToolService()

    def test_forecast_detected_domani(self):
        assert self.ts._is_forecast_request("che tempo fa domani a Roma?") is True

    def test_forecast_detected_previsioni(self):
        assert self.ts._is_forecast_request("previsioni meteo Bologna") is True

    def test_forecast_detected_weekend(self):
        assert self.ts._is_forecast_request("meteo nel weekend") is True

    def test_forecast_not_detected_current(self):
        assert self.ts._is_forecast_request("che tempo fa a Roma?") is False

    def test_extract_city_known_italian(self):
        city = self.ts._extract_city("che tempo fa a Bologna?")
        assert city == "Bologna"

    def test_extract_city_known_compound(self):
        city = self.ts._extract_city("meteo a reggio calabria")
        assert city == "Reggio Calabria"

    def test_extract_city_worldwide_capitalized(self):
        city = self.ts._extract_city("che tempo fa a Londra?")
        assert city is not None
        assert "Londra" in city or "londra" in city.lower()

    def test_extract_city_worldwide_paris(self):
        city = self.ts._extract_city("meteo a Parigi")
        assert city is not None

    def test_extract_city_no_city(self):
        city = self.ts._extract_city("che tempo fa?")
        assert city is None


# ═══════════════════════════════════════════════════════════════
# TEST 8: News categorization (new)
# ═══════════════════════════════════════════════════════════════

class TestNewsCategorization:
    """News: category detection from message."""

    def test_sport_detected(self):
        from core.tool_services import NEWS_SECTIONS
        msg = "notizie sport"
        found = None
        for section, keywords in NEWS_SECTIONS.items():
            if any(kw in msg for kw in keywords):
                found = section
                break
        assert found == "sport"

    def test_politica_detected(self):
        from core.tool_services import NEWS_SECTIONS
        msg = "notizie politica"
        found = None
        for section, keywords in NEWS_SECTIONS.items():
            if any(kw in msg for kw in keywords):
                found = section
                break
        assert found == "politica"

    def test_cronaca_detected(self):
        from core.tool_services import NEWS_SECTIONS
        msg = "cronaca locale"
        found = None
        for section, keywords in NEWS_SECTIONS.items():
            if any(kw in msg for kw in keywords):
                found = section
                break
        assert found == "cronaca"

    def test_finanza_detected(self):
        from core.tool_services import NEWS_SECTIONS
        msg = "notizie economia"
        found = None
        for section, keywords in NEWS_SECTIONS.items():
            if any(kw in msg for kw in keywords):
                found = section
                break
        assert found == "finanza"

    def test_no_category_generic(self):
        from core.tool_services import NEWS_SECTIONS
        msg = "ultime notizie"
        found = None
        for section, keywords in NEWS_SECTIONS.items():
            if any(kw in msg for kw in keywords):
                found = section
                break
        assert found is None


# ═══════════════════════════════════════════════════════════════
# TEST 9: Intent override for short contextual follow-ups (new)
# ═══════════════════════════════════════════════════════════════

def _should_override_to_relational(message: str, user_id: str) -> bool:
    """Standalone copy of Proactor._should_override_to_relational for testing."""
    msg_lower = message.lower().strip()
    if len(msg_lower) > 60:
        return False
    contextual_patterns = [
        "perché?", "perche?", "secondo te", "e tu?", "e tu che ne pensi",
        "perché continui", "perche continui", "come mai?",
        "davvero?", "sul serio?", "in che senso", "cioè?", "cioe?",
        "tipo?", "ad esempio?", "e quindi?", "e allora?", "e poi?",
        "non capisco", "non ho capito", "cosa intendi", "cosa vuoi dire",
        "prima", "lamentato", "detto prima", "parlato prima",
        "continua", "continuare",
    ]
    if any(p in msg_lower for p in contextual_patterns):
        return True
    if msg_lower.startswith("perch") and len(msg_lower) < 50:
        return True
    return False


class TestIntentOverride:
    """Conversational fix: short 'perché?' should stay relational."""

    def test_perche_short_overrides(self):
        assert _should_override_to_relational("Perché?", "test") is True

    def test_secondo_te_overrides(self):
        assert _should_override_to_relational("Secondo te perché?", "test") is True

    def test_perche_continui_overrides(self):
        assert _should_override_to_relational("Perché continui?", "test") is True

    def test_come_mai_overrides(self):
        assert _should_override_to_relational("Come mai?", "test") is True

    def test_e_quindi_overrides(self):
        assert _should_override_to_relational("E quindi?", "test") is True

    def test_long_technical_question_no_override(self):
        assert _should_override_to_relational(
            "Perché il protocollo TCP usa un handshake a tre vie per stabilire la connessione?", "test"
        ) is False

    def test_ciao_no_override(self):
        assert _should_override_to_relational("Ciao come stai", "test") is False

    def test_perche_lamentato_prima_overrides(self):
        assert _should_override_to_relational("Perché mi sono lamentato prima?", "test") is True

    def test_continua_overrides(self):
        assert _should_override_to_relational("Continua", "test") is True

    def test_di_cosa_parlato_prima_overrides(self):
        assert _should_override_to_relational("Di cosa abbiamo parlato prima?", "test") is True


# ═══════════════════════════════════════════════════════════════
# TEST 10: User boundary detection (new)
# ═══════════════════════════════════════════════════════════════

def _detect_user_boundaries(conversation_context: str, message: str) -> str:
    """Standalone copy of Proactor._detect_user_boundaries for testing."""
    boundaries = []
    combined = (conversation_context + " " + message).lower()
    if "non farmi domande" in combined or "non fare domande" in combined:
        boundaries.append("L'utente ha chiesto di NON fare domande. NON chiudere con domande.")
    if "non voglio consigli" in combined or "non darmi consigli" in combined:
        boundaries.append("L'utente ha chiesto di NON ricevere consigli. NON dare suggerimenti.")
    if "non voglio parlare" in combined or "non ne voglio parlare" in combined:
        boundaries.append("L'utente non vuole parlare di questo. Rispetta il confine.")
    if "basta" in message.lower() or "smettila" in message.lower():
        boundaries.append("L'utente vuole che tu smetta. Rispondi brevemente e basta.")
    if boundaries:
        return "\nCONFINI ESPLICITI DELL'UTENTE (RISPETTA OBBLIGATORIAMENTE):\n" + "\n".join(f"- {b}" for b in boundaries)
    return ""


class TestUserBoundaries:
    """Conversational fix: detect 'non farmi domande', 'non voglio consigli'."""

    def test_non_farmi_domande_detected(self):
        result = _detect_user_boundaries("", "Non farmi domande")
        assert "NON fare domande" in result

    def test_non_voglio_consigli_detected(self):
        result = _detect_user_boundaries("", "Non voglio consigli")
        assert "NON ricevere consigli" in result

    def test_basta_detected(self):
        result = _detect_user_boundaries("", "Basta")
        assert "smetta" in result

    def test_normal_message_no_boundary(self):
        result = _detect_user_boundaries("", "Come stai?")
        assert result == ""

    def test_boundary_from_context(self):
        ctx = "utente: non farmi domande\nassistente: ok"
        result = _detect_user_boundaries(ctx, "Sono stanco")
        assert "NON fare domande" in result


# ═══════════════════════════════════════════════════════════════
# TEST 11: New response filter patterns (new)
# ═══════════════════════════════════════════════════════════════

class TestNewFilterPatterns:
    """Response filter: new leaked phrases are caught."""

    def test_mi_fa_piacere_sapere_stripped(self):
        from core.response_filter import filter_response, _last_responses, _repeat_counts
        uid = "nfp_1"
        _last_responses.pop(uid, None)
        _repeat_counts.pop(uid, None)
        result = filter_response("Mi fa piacere sapere che stai bene.", uid)
        assert "mi fa piacere sapere" not in result.lower()

    def test_assistente_virtuale_stripped(self):
        from core.response_filter import filter_response, _last_responses, _repeat_counts
        uid = "nfp_2"
        _last_responses.pop(uid, None)
        _repeat_counts.pop(uid, None)
        result = filter_response("Sono un assistente virtuale progettato per aiutarti.", uid)
        assert "assistente virtuale" not in result.lower()

    def test_se_vuoi_parlare_stripped(self):
        from core.response_filter import filter_response, _last_responses, _repeat_counts
        uid = "nfp_3"
        _last_responses.pop(uid, None)
        _repeat_counts.pop(uid, None)
        result = filter_response("Se vuoi parlare di qualcosa, sono qui.", uid)
        assert "se vuoi parlare di qualcosa" not in result.lower()

    def test_spero_che_possiate_stripped(self):
        from core.response_filter import filter_response, _last_responses, _repeat_counts
        uid = "nfp_4"
        _last_responses.pop(uid, None)
        _repeat_counts.pop(uid, None)
        result = filter_response("Spero che possiate risolvere presto.", uid)
        assert "spero che possiate" not in result.lower()

    def test_non_ho_informazioni_sufficienti_stripped(self):
        from core.response_filter import filter_response, _last_responses, _repeat_counts
        uid = "nfp_5"
        _last_responses.pop(uid, None)
        _repeat_counts.pop(uid, None)
        result = filter_response("Non ho informazioni sufficienti per rispondere.", uid)
        assert "non ho informazioni sufficienti" not in result.lower()


# ═══════════════════════════════════════════════════════════════
# TEST 12: Chat history limit — must be 15, not 6 (new)
# ═══════════════════════════════════════════════════════════════

class TestChatHistoryLimit:
    """Chat history must include at least 15 messages in the conversation context."""

    def test_build_conversation_context_uses_15_messages(self):
        from core.chat_memory import chat_memory
        from core.context_assembler import build_conversation_context
        uid = "test_history_15"
        # Clear any existing messages
        chat_memory.clear_messages(uid)
        # Add 15 messages
        for i in range(15):
            chat_memory.add_message(uid, f"msg_{i}", f"resp_{i}", "chat_free")
        ctx = build_conversation_context(uid, "nuovo messaggio", {})
        # All 15 messages should be present
        for i in range(15):
            assert f"msg_{i}" in ctx, f"msg_{i} missing from context"
        # Cleanup
        chat_memory.clear_messages(uid)

    def test_old_limit_6_is_gone(self):
        from core.chat_memory import chat_memory
        from core.context_assembler import build_conversation_context
        uid = "test_history_not_6"
        chat_memory.clear_messages(uid)
        for i in range(10):
            chat_memory.add_message(uid, f"turn_{i}", f"answer_{i}", "chat_free")
        ctx = build_conversation_context(uid, "test", {})
        # Message 0 through 9 should ALL be present (old limit=6 would drop 0-3)
        for i in range(10):
            assert f"turn_{i}" in ctx, f"turn_{i} missing — old limit=6 bug still present"
        chat_memory.clear_messages(uid)

    def test_weather_city_visible_in_history(self):
        """After asking weather for Tokyo, the city must appear in conversation context."""
        from core.chat_memory import chat_memory
        from core.context_assembler import build_conversation_context
        uid = "test_tokyo_visible"
        chat_memory.clear_messages(uid)
        chat_memory.add_message(uid, "Che tempo fa a Tokyo?",
                                "A Tokyo: cielo sereno, 8°C, umidità 69%", "weather")
        chat_memory.add_message(uid, "Bello!", "Sì, giornata limpida.", "chat_free")
        ctx = build_conversation_context(uid, "Per quale città ti ho chiesto le previsioni?", {})
        assert "Tokyo" in ctx, "Tokyo must be visible in conversation context"
        chat_memory.clear_messages(uid)


# ═══════════════════════════════════════════════════════════════
# TEST 13: Elliptical news follow-up (new)
# ═══════════════════════════════════════════════════════════════

class TestEllipticalNewsFollowUp:
    """'E di politica?' after news should resolve to news follow-up."""

    def test_is_elliptical_news_detected(self):
        from core.tool_context import is_elliptical_news_followup
        assert is_elliptical_news_followup("e di politica?") is True

    def test_is_elliptical_news_sport(self):
        from core.tool_context import is_elliptical_news_followup
        assert is_elliptical_news_followup("e di sport?") is True

    def test_is_elliptical_news_cronaca(self):
        from core.tool_context import is_elliptical_news_followup
        assert is_elliptical_news_followup("e la cronaca?") is True

    def test_not_elliptical_news(self):
        from core.tool_context import is_elliptical_news_followup
        assert is_elliptical_news_followup("che notizie ci sono?") is False

    def test_resolve_news_after_context(self):
        from core.tool_context import save_tool_context, resolve_elliptical_news
        uid = "test_news_resolve"
        save_tool_context(uid, "news")
        topic = resolve_elliptical_news(uid, "e di politica?")
        assert topic is not None
        assert "politica" in topic

    def test_resolve_news_no_context(self):
        from core.tool_context import resolve_elliptical_news
        topic = resolve_elliptical_news("no_ctx_user_xyz", "e di politica?")
        assert topic is None

    def test_resolve_news_wrong_intent(self):
        from core.tool_context import save_tool_context, resolve_elliptical_news
        uid = "test_news_wrong_intent"
        save_tool_context(uid, "weather", city="Roma")
        topic = resolve_elliptical_news(uid, "e di politica?")
        assert topic is None


# ═══════════════════════════════════════════════════════════════
# TEST 14: Narrative continuity across intents (new)
# ═══════════════════════════════════════════════════════════════

class TestNarrativeContinuityAcrossIntents:
    """Messages like 'Secondo te perché?' after 'Sono stanco' + 'Non ho dormito'
    must have access to the full conversation thread."""

    def test_stanco_dormito_perche_context_present(self):
        """Simulate: 'Sono stanco' -> 'Non ho dormito' -> 'Secondo te perché?'
        The context for the third message must contain both previous messages."""
        from core.chat_memory import chat_memory
        from core.context_assembler import build_conversation_context
        uid = "test_continuity_perche"
        chat_memory.clear_messages(uid)
        chat_memory.add_message(uid, "Sono stanco", "Hai avuto una giornata pesante?", "chat_free")
        chat_memory.add_message(uid, "Non ho dormito", "Se non hai dormito è normale sentirti così.", "chat_free")
        ctx = build_conversation_context(uid, "Secondo te perché?", {})
        assert "Sono stanco" in ctx
        assert "Non ho dormito" in ctx
        chat_memory.clear_messages(uid)

    def test_perche_override_fires_for_lamentato(self):
        """'Perché mi sono lamentato prima?' must trigger override."""
        assert _should_override_to_relational("Perché mi sono lamentato prima?", "test") is True

    def test_continua_override_fires(self):
        """'Continua' must trigger override."""
        assert _should_override_to_relational("Continua", "test") is True
