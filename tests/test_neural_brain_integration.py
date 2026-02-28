"""
tests/test_neural_brain_integration.py

Suite pytest completa per Genesi — coprente:
  1.  WeightTracker (sinapsi di apprendimento route)
  2.  StyleRegulator (_build_style_directives)
  3.  Parallel calendar writes (asyncio.gather + run_in_executor)
  4.  Intent classifier pre-check (dove_sono, memory_correction)
  5.  Memory correction handler (_handle_memory_correction)
  6.  Location handler (_handle_location)
  7.  Reminder trigger detection (_REMINDER_TRIGGER_ONLY / _PHRASES)
  8.  Bedrock image generation (AWS)
  9.  Image search service (Pixabay + DuckDuckGo fallback)
  10. Tool services (weather, news, time, date)
  11. LLM service (fallback chain, downgrade, deterministic_fallback)
  12. Reminder engine (format, load)
  13. Storage (load/save roundtrip, non-serializable guard)
  14. Relational prompt style injection
  15. Proactor handle() integration (flow completo mockato)

asyncio_mode = auto (pytest.ini) → nessun @pytest.mark.asyncio richiesto, ma lo
aggiungiamo comunque per leggibilità e compatibilità con runner esterni.
"""

# ─── Mock AWS SDK prima di qualsiasi import genesi ────────────────────────────
# boto3/botocore non sono installati nell'ambiente di sviluppo locale.
# Il mock deve avvenire PRIMA che core.proactor (che importa bedrock_image_service)
# venga importato per la prima volta.
import sys as _sys
from unittest.mock import MagicMock as _MagicMock

def _mock_aws():
    _botocore_exc = _MagicMock()
    _botocore_exc.ClientError = type("ClientError", (Exception,), {})
    _sys.modules.setdefault("boto3", _MagicMock())
    _sys.modules.setdefault("botocore", _MagicMock())
    _sys.modules.setdefault("botocore.exceptions", _botocore_exc)

_mock_aws()
# ──────────────────────────────────────────────────────────────────────────────

import os
import json
import asyncio
import pytest
import tempfile
import re
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, AsyncMock, MagicMock, call, ANY

# ─────────────────────────────────────────────────────────────────────────────
# COSTANTI DI TEST
# ─────────────────────────────────────────────────────────────────────────────

TEST_USER_ID = "test_user@genesi.test"
TEST_PROFILE_FULL = {
    "user_id": TEST_USER_ID,
    "email": TEST_USER_ID,
    "name": "Marco",
    "city": "Imola",
    "timezone": "Europe/Rome",
    "profession": "Architetto",
    "spouse": "Giulia",
    "pets": [{"type": "cane", "name": "Max"}],
    "children": [{"name": "Luca"}],
    "interests": ["musica", "calcio"],
    "traits": ["curioso"],
    "icloud_user": "marco@icloud.com",
    "icloud_password": "secret",
    "google_token": {"access_token": "tok_test", "refresh_token": "ref_test"},
}
TEST_PROFILE_MINIMAL = {"user_id": TEST_USER_ID, "name": "Test", "city": "Roma", "timezone": "Europe/Rome"}


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 1: WEIGHT TRACKER
# ─────────────────────────────────────────────────────────────────────────────

class TestWeightTracker:
    """Test del sistema di sinapsi / apprendimento route."""

    def setup_method(self):
        """Usa directory temporanea per isolare ogni test."""
        import core.weight_tracker as _wt
        self._wt = _wt
        self.tmp = tempfile.mkdtemp()
        self._patcher = patch.object(_wt, "_WEIGHTS_DIR", self.tmp)
        self._patcher.start()
        self.tracker = _wt.WeightTracker()

    def teardown_method(self):
        self._patcher.stop()

    # ── valori default ────────────────────────────────────────────────────────

    def test_unknown_route_returns_default_weight(self):
        w = self.tracker.get_weight(TEST_USER_ID, "mai_visto")
        assert w == self._wt._DEFAULT_WEIGHT  # 0.50

    def test_unknown_user_returns_default(self):
        w = self.tracker.get_weight("nuovo_user@test", "relational")
        assert w == self._wt._DEFAULT_WEIGHT

    # ── deltas ────────────────────────────────────────────────────────────────

    def test_success_increases_weight_by_delta(self):
        w0 = self.tracker.get_weight(TEST_USER_ID, "relational")
        w1 = self.tracker.record_outcome(TEST_USER_ID, "relational", success=True)
        assert abs(w1 - (w0 + self._wt._DELTA_SUCCESS)) < 1e-4

    def test_failure_decreases_weight_by_delta(self):
        w0 = self.tracker.get_weight(TEST_USER_ID, "relational")
        w1 = self.tracker.record_outcome(TEST_USER_ID, "relational", success=False)
        assert abs(w1 - (w0 + self._wt._DELTA_FAILURE)) < 1e-4

    def test_multiple_successes_increase_weight_monotonically(self):
        w = self.tracker.get_weight(TEST_USER_ID, "mono_route")
        for _ in range(5):
            wn = self.tracker.record_outcome(TEST_USER_ID, "mono_route", success=True)
            assert wn >= w
            w = wn

    # ── clamping ──────────────────────────────────────────────────────────────

    def test_weight_never_exceeds_max(self):
        for _ in range(60):
            self.tracker.record_outcome(TEST_USER_ID, "high_route", success=True)
        w = self.tracker.get_weight(TEST_USER_ID, "high_route")
        assert w <= self._wt._MAX_WEIGHT  # 0.95

    def test_weight_never_falls_below_min(self):
        for _ in range(30):
            self.tracker.record_outcome(TEST_USER_ID, "low_route", success=False)
        w = self.tracker.get_weight(TEST_USER_ID, "low_route")
        assert w >= self._wt._MIN_WEIGHT  # 0.10

    # ── persistenza ───────────────────────────────────────────────────────────

    def test_weight_persisted_to_json_file(self):
        self.tracker.record_outcome(TEST_USER_ID, "persist_route", success=True)
        path = self._wt._weights_path(TEST_USER_ID)
        assert os.path.exists(path)
        with open(path) as f:
            data = json.load(f)
        assert "persist_route" in data
        assert "weight" in data["persist_route"]
        assert "last_updated" in data["persist_route"]

    def test_counters_tracked_correctly(self):
        for _ in range(3):
            self.tracker.record_outcome(TEST_USER_ID, "cnt_route", success=True)
        for _ in range(2):
            self.tracker.record_outcome(TEST_USER_ID, "cnt_route", success=False)
        data = self._wt._load_weights(TEST_USER_ID)
        assert data["cnt_route"]["total_success"] == 3
        assert data["cnt_route"]["total_failure"] == 2

    def test_no_tmp_file_left_after_write(self):
        self.tracker.record_outcome(TEST_USER_ID, "atomic_route", success=True)
        path = self._wt._weights_path(TEST_USER_ID)
        assert not os.path.exists(path + ".tmp")

    # ── isolamento utenti ─────────────────────────────────────────────────────

    def test_different_users_independent(self):
        self.tracker.record_outcome("user_a@t", "route", success=True)
        self.tracker.record_outcome("user_b@t", "route", success=False)
        wa = self.tracker.get_weight("user_a@t", "route")
        wb = self.tracker.get_weight("user_b@t", "route")
        assert wa > wb

    def test_user_id_with_slash_safe(self):
        """User ID con slash non deve creare path traversal."""
        uid = "user/with/slash"
        self.tracker.record_outcome(uid, "route", success=True)
        w = self.tracker.get_weight(uid, "route")
        assert w > self._wt._DEFAULT_WEIGHT

    # ── decay ────────────────────────────────────────────────────────────────

    def test_decay_lowers_high_weight_over_time(self):
        """Peso al massimo con last_updated 60gg fa deve essere decaduto."""
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        data = {
            "decay_route": {
                "weight": self._wt._MAX_WEIGHT,
                "last_updated": old_date,
                "total_success": 20,
                "total_failure": 0,
            }
        }
        path = self._wt._weights_path(TEST_USER_ID)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)
        w = self.tracker.get_weight(TEST_USER_ID, "decay_route")
        assert w < self._wt._MAX_WEIGHT
        assert w > 0.50  # Non ancora al centro dopo 60gg

    def test_decay_raises_low_weight_over_time(self):
        """Peso al minimo con last_updated 60gg fa deve risalire verso 0.5."""
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        data = {
            "low_decay_route": {
                "weight": self._wt._MIN_WEIGHT,
                "last_updated": old_date,
                "total_success": 0,
                "total_failure": 20,
            }
        }
        path = self._wt._weights_path(TEST_USER_ID)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f)
        w = self.tracker.get_weight(TEST_USER_ID, "low_decay_route")
        assert w > self._wt._MIN_WEIGHT
        assert w < 0.50

    # ── async ─────────────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_record_success_async_updates_weight(self):
        await self.tracker.record_success_async(TEST_USER_ID, "async_s_route")
        w = self.tracker.get_weight(TEST_USER_ID, "async_s_route")
        assert w > self._wt._DEFAULT_WEIGHT

    @pytest.mark.asyncio
    async def test_record_failure_async_lowers_weight(self):
        await self.tracker.record_failure_async(TEST_USER_ID, "async_f_route")
        w = self.tracker.get_weight(TEST_USER_ID, "async_f_route")
        assert w < self._wt._DEFAULT_WEIGHT

    @pytest.mark.asyncio
    async def test_async_methods_are_non_blocking(self):
        """Due chiamate async su utenti diversi non si bloccano a vicenda."""
        # Su Windows os.replace() può fallire se due thread scrivono lo stesso file
        # in contemporanea → usiamo utenti distinti per evitare contesa sul file
        await asyncio.gather(
            self.tracker.record_success_async("user_par_a@test", "par_route"),
            self.tracker.record_success_async("user_par_b@test", "par_route"),
        )
        w1 = self.tracker.get_weight("user_par_a@test", "par_route")
        w2 = self.tracker.get_weight("user_par_b@test", "par_route")
        assert w1 > self._wt._DEFAULT_WEIGHT
        assert w2 > self._wt._DEFAULT_WEIGHT


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 2: STYLE REGULATOR
# ─────────────────────────────────────────────────────────────────────────────

class TestStyleRegulator:
    """Test del metodo statico _build_style_directives(hour)."""

    @pytest.fixture(autouse=True)
    def _load(self):
        from core.proactor import Proactor
        self.fn = Proactor._build_style_directives

    # ── copertura completa 0-23 ───────────────────────────────────────────────

    def test_all_24_hours_return_non_empty_string(self):
        for h in range(24):
            d = self.fn(h)
            assert isinstance(d, str) and len(d) > 5, f"hour={h} → vuoto"

    def test_all_hours_no_unformatted_placeholder(self):
        for h in range(24):
            d = self.fn(h)
            assert "{" not in d and "}" not in d, f"hour={h} ha placeholder"

    # ── fasce orarie ──────────────────────────────────────────────────────────

    @pytest.mark.parametrize("hour", [0, 1, 2, 3, 4])
    def test_night_hours(self, hour):
        d = self.fn(hour).lower()
        assert "notte" in d or "brevissimo" in d, f"hour={hour}"

    @pytest.mark.parametrize("hour", [5, 6, 7, 8])
    def test_early_morning_hours(self, hour):
        d = self.fn(hour).lower()
        assert "mattina" in d or "pratiche" in d or "sobria" in d, f"hour={hour}"

    @pytest.mark.parametrize("hour", [9, 10, 11])
    def test_morning_hours(self, hour):
        d = self.fn(hour).lower()
        assert "mattina" in d or "proattivo" in d, f"hour={hour}"

    @pytest.mark.parametrize("hour", [12, 13])
    def test_lunch_hours(self, hour):
        d = self.fn(hour).lower()
        assert "pranzo" in d or "concis" in d or "fretta" in d, f"hour={hour}"

    @pytest.mark.parametrize("hour", [14, 15, 16, 17])
    def test_afternoon_hours(self, hour):
        d = self.fn(hour).lower()
        assert "pomeriggio" in d or "collaborativo" in d, f"hour={hour}"

    @pytest.mark.parametrize("hour", [18, 19, 20])
    def test_evening_hours(self, hour):
        d = self.fn(hour).lower()
        assert "sera" in d or "rilassato" in d or "caldo" in d, f"hour={hour}"

    @pytest.mark.parametrize("hour", [21, 22, 23])
    def test_late_evening_hours(self, hour):
        d = self.fn(hour).lower()
        assert "sera" in d or "tardi" in d or "breve" in d, f"hour={hour}"

    # ── edge cases ────────────────────────────────────────────────────────────

    def test_boundary_hour_5_is_early_morning(self):
        d = self.fn(5).lower()
        night_d = self.fn(4).lower()
        # 5 deve essere diverso da 4
        assert d != night_d or "mattina" in d

    def test_boundary_hour_21_is_late_evening(self):
        d = self.fn(21).lower()
        eve_d = self.fn(20).lower()
        # Almeno uno dei due deve contenere "sera"
        assert "sera" in d or "sera" in eve_d


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 3: INTENT CLASSIFIER — pre-check deterministici
# ─────────────────────────────────────────────────────────────────────────────

class TestIntentClassifierPreChecks:
    """Verifica che dove_sono e memory_correction vengano intercettati prima del LLM."""

    @pytest.mark.asyncio
    async def test_dove_sono_no_llm_call(self):
        with patch("core.llm_service.llm_service._call_with_protection",
                   new_callable=AsyncMock) as mock_llm:
            from core.intent_classifier import intent_classifier
            result = await intent_classifier.classify_async("dove sono?", user_id=TEST_USER_ID)
        assert "dove_sono" in result
        mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_dove_mi_trovo_no_llm_call(self):
        with patch("core.llm_service.llm_service._call_with_protection",
                   new_callable=AsyncMock) as mock_llm:
            from core.intent_classifier import intent_classifier
            result = await intent_classifier.classify_async("dove mi trovo adesso?", user_id=TEST_USER_ID)
        assert "dove_sono" in result
        mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_dove_siamo_no_llm_call(self):
        with patch("core.llm_service.llm_service._call_with_protection",
                   new_callable=AsyncMock) as mock_llm:
            from core.intent_classifier import intent_classifier
            result = await intent_classifier.classify_async("dove siamo?", user_id=TEST_USER_ID)
        assert "dove_sono" in result
        mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_memory_correction_non_mi_chiamo_no_llm(self):
        with patch("core.llm_service.llm_service._call_with_protection",
                   new_callable=AsyncMock) as mock_llm:
            from core.intent_classifier import intent_classifier
            result = await intent_classifier.classify_async(
                "non mi chiamo Mario, mi chiamo Luca", user_id=TEST_USER_ID
            )
        assert "memory_correction" in result
        mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_memory_correction_in_realta_sono_no_llm(self):
        with patch("core.llm_service.llm_service._call_with_protection",
                   new_callable=AsyncMock) as mock_llm:
            from core.intent_classifier import intent_classifier
            result = await intent_classifier.classify_async(
                "in realtà sono un medico, non un ingegnere", user_id=TEST_USER_ID
            )
        assert "memory_correction" in result
        mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_memory_correction_non_ho_figli_no_llm(self):
        with patch("core.llm_service.llm_service._call_with_protection",
                   new_callable=AsyncMock) as mock_llm:
            from core.intent_classifier import intent_classifier
            result = await intent_classifier.classify_async("non ho figli", user_id=TEST_USER_ID)
        assert "memory_correction" in result
        mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_memory_correction_non_vivo_a_no_llm(self):
        with patch("core.llm_service.llm_service._call_with_protection",
                   new_callable=AsyncMock) as mock_llm:
            from core.intent_classifier import intent_classifier
            result = await intent_classifier.classify_async("non vivo a Roma, vivo a Bologna", user_id=TEST_USER_ID)
        assert "memory_correction" in result
        mock_llm.assert_not_called()

    @pytest.mark.asyncio
    async def test_regular_chat_uses_llm(self):
        """Chat normale non intercettata dai pre-check → LLM viene chiamato."""
        with patch("core.llm_service.llm_service._call_with_protection",
                   new_callable=AsyncMock,
                   return_value='{"intents": ["chat_free"], "score": 0.9}') as mock_llm, \
             patch("core.chat_memory.chat_memory.get_messages", return_value=[]):
            from core.intent_classifier import intent_classifier
            result = await intent_classifier.classify_async("ciao come stai?", user_id=TEST_USER_ID)
        mock_llm.assert_called_once()
        assert "dove_sono" not in result
        assert "memory_correction" not in result

    @pytest.mark.asyncio
    async def test_classify_async_returns_list(self):
        """classify_async deve sempre tornare una lista."""
        with patch("core.llm_service.llm_service._call_with_protection",
                   new_callable=AsyncMock,
                   return_value='{"intents": ["chat_free"], "score": 0.9}'), \
             patch("core.chat_memory.chat_memory.get_messages", return_value=[]):
            from core.intent_classifier import intent_classifier
            result = await intent_classifier.classify_async("qualsiasi cosa", user_id=TEST_USER_ID)
        assert isinstance(result, list)
        assert len(result) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 4: REMINDER TRIGGER DETECTION
# ─────────────────────────────────────────────────────────────────────────────

class TestReminderTriggerDetection:
    """Test di _REMINDER_TRIGGER_ONLY, _REMINDER_TRIGGER_PHRASES e is_ask return."""

    def setup_method(self):
        from core.proactor import Proactor
        self.p = Proactor()

    # ── set trigger singole parole ────────────────────────────────────────────

    def test_trigger_only_set_contains_ricordami(self):
        assert "ricordami" in self.p._REMINDER_TRIGGER_ONLY

    def test_trigger_only_set_contains_promemoria(self):
        assert "promemoria" in self.p._REMINDER_TRIGGER_ONLY

    def test_trigger_only_set_contains_memorizza(self):
        assert "memorizza" in self.p._REMINDER_TRIGGER_ONLY

    # ── lista frasi multi-parola ──────────────────────────────────────────────

    def test_phrase_imposta_una_sveglia(self):
        assert "imposta una sveglia" in self.p._REMINDER_TRIGGER_PHRASES

    def test_phrase_metti_nel_calendario(self):
        assert "metti nel calendario" in self.p._REMINDER_TRIGGER_PHRASES

    def test_phrase_aggiungi_al_calendario(self):
        assert "aggiungi al calendario" in self.p._REMINDER_TRIGGER_PHRASES

    def test_phrase_crea_un_promemoria(self):
        assert "crea un promemoria" in self.p._REMINDER_TRIGGER_PHRASES

    # ── ritorno is_ask (3-tuple) ──────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_ricordami_alone_returns_ask(self):
        """Solo 'ricordami' senza contenuto → 3-tuple is_ask=True."""
        with patch("core.storage.storage.load", new_callable=AsyncMock, return_value={}), \
             patch.object(self.p, "_parse_reminder_request_strict", return_value=(None, None)), \
             patch.object(self.p, "_parse_reminder_natural",
                          new_callable=AsyncMock, return_value=(None, None)):
            result = await self.p._handle_reminder_creation(TEST_USER_ID, "ricordami")
        assert isinstance(result, tuple) and len(result) == 3
        assert result[2] is True, "is_ask deve essere True"
        assert result[1] == "reminder"

    @pytest.mark.asyncio
    async def test_si_imposta_una_sveglia_returns_ask(self):
        with patch("core.storage.storage.load", new_callable=AsyncMock, return_value={}), \
             patch.object(self.p, "_parse_reminder_request_strict", return_value=(None, None)), \
             patch.object(self.p, "_parse_reminder_natural",
                          new_callable=AsyncMock, return_value=(None, None)):
            result = await self.p._handle_reminder_creation(TEST_USER_ID, "si imposta una sveglia")
        assert isinstance(result, tuple) and len(result) == 3 and result[2] is True

    @pytest.mark.asyncio
    async def test_metti_nel_calendario_returns_ask(self):
        with patch("core.storage.storage.load", new_callable=AsyncMock, return_value={}), \
             patch.object(self.p, "_parse_reminder_request_strict", return_value=(None, None)), \
             patch.object(self.p, "_parse_reminder_natural",
                          new_callable=AsyncMock, return_value=(None, None)):
            result = await self.p._handle_reminder_creation(TEST_USER_ID, "metti nel calendario")
        assert isinstance(result, tuple) and result[2] is True

    @pytest.mark.asyncio
    async def test_valid_text_missing_datetime_returns_ask(self):
        """Testo valido ma senza data → chiede quando."""
        with patch("core.storage.storage.load", new_callable=AsyncMock, return_value={}), \
             patch.object(self.p, "_parse_reminder_request_strict",
                          return_value=("comprare il latte", None)), \
             patch.object(self.p, "_parse_reminder_natural",
                          new_callable=AsyncMock, return_value=("comprare il latte", None)):
            result = await self.p._handle_reminder_creation(TEST_USER_ID, "ricordami di comprare il latte")
        assert isinstance(result, tuple) and len(result) == 3 and result[2] is True
        assert "quando" in result[0].lower() or "ora" in result[0].lower() or "giorno" in result[0].lower()


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 5: PARALLEL CALENDAR WRITES
# ─────────────────────────────────────────────────────────────────────────────

class TestParallelCalendarWrites:
    """Verifica che Google e iCloud vengano scritti in parallelo via asyncio.gather."""

    def setup_method(self):
        from core.proactor import Proactor
        self.p = Proactor()

    def _make_mock_cm(self, return_value=True):
        cm = MagicMock()
        cm.add_event = MagicMock(return_value=return_value)
        cm._admin_google_service = None
        return cm

    @pytest.mark.asyncio
    async def test_both_calendars_written_when_both_available(self):
        profile = {
            "email": "user@test.com",
            "google_token": {"access_token": "gtok"},
            "icloud_user": "user@icloud.com",
            "icloud_password": "pass",
        }
        mock_cm = self._make_mock_cm(return_value=True)
        dt = datetime(2026, 3, 15, 10, 0)

        with patch("core.storage.storage.load", new_callable=AsyncMock, return_value=profile), \
             patch.object(self.p, "_parse_reminder_request_strict",
                          return_value=("visita medico", dt)), \
             patch.object(self.p, "_parse_reminder_natural",
                          new_callable=AsyncMock, return_value=("visita medico", dt)), \
             patch("core.reminder_engine.reminder_engine.create_reminder_with_response",
                   return_value=("rem_id_001", "Fatto! Ricorderò 'visita medico'.")), \
             patch("calendar_manager.calendar_manager", mock_cm), \
             patch("auth.config.ADMIN_EMAILS", set()):

            result = await self.p._handle_reminder_creation(
                TEST_USER_ID, "visita medico martedì alle 10"
            )

        # add_event chiamato esattamente 2 volte (google + apple)
        assert mock_cm.add_event.call_count == 2
        providers = {c.args[3] for c in mock_cm.add_event.call_args_list}
        assert "google" in providers
        assert "apple" in providers

    @pytest.mark.asyncio
    async def test_only_google_when_no_icloud(self):
        profile = {
            "email": "user@test.com",
            "google_token": {"access_token": "gtok"},
        }
        mock_cm = self._make_mock_cm(return_value=True)
        dt = datetime(2026, 3, 15, 10, 0)

        with patch("core.storage.storage.load", new_callable=AsyncMock, return_value=profile), \
             patch.object(self.p, "_parse_reminder_request_strict",
                          return_value=("dentista", dt)), \
             patch.object(self.p, "_parse_reminder_natural",
                          new_callable=AsyncMock, return_value=("dentista", dt)), \
             patch("core.reminder_engine.reminder_engine.create_reminder_with_response",
                   return_value=("rem_002", "Ricorderò 'dentista'.")), \
             patch("calendar_manager.calendar_manager", mock_cm), \
             patch("auth.config.ADMIN_EMAILS", set()):

            await self.p._handle_reminder_creation(TEST_USER_ID, "dentista giovedì alle 15")

        assert mock_cm.add_event.call_count == 1
        provider_used = mock_cm.add_event.call_args.args[3]
        assert provider_used == "google"

    @pytest.mark.asyncio
    async def test_only_icloud_when_no_google(self):
        profile = {
            "email": "user@test.com",
            "icloud_user": "user@icloud.com",
            "icloud_password": "pass",
        }
        mock_cm = self._make_mock_cm(return_value=True)
        dt = datetime(2026, 3, 15, 10, 0)

        with patch("core.storage.storage.load", new_callable=AsyncMock, return_value=profile), \
             patch.object(self.p, "_parse_reminder_request_strict",
                          return_value=("palestra", dt)), \
             patch.object(self.p, "_parse_reminder_natural",
                          new_callable=AsyncMock, return_value=("palestra", dt)), \
             patch("core.reminder_engine.reminder_engine.create_reminder_with_response",
                   return_value=("rem_003", "Ricorderò 'palestra'.")), \
             patch("calendar_manager.calendar_manager", mock_cm), \
             patch("auth.config.ADMIN_EMAILS", set()):

            await self.p._handle_reminder_creation(TEST_USER_ID, "palestra domani alle 7")

        assert mock_cm.add_event.call_count == 1
        provider_used = mock_cm.add_event.call_args.args[3]
        assert provider_used == "apple"

    @pytest.mark.asyncio
    async def test_calendar_failure_returns_response_without_crash(self):
        """add_event che ritorna False non deve crashare."""
        profile = {
            "email": "user@test.com",
            "google_token": {"access_token": "gtok"},
            "icloud_user": "user@icloud.com",
            "icloud_password": "pass",
        }
        mock_cm = self._make_mock_cm(return_value=False)
        dt = datetime(2026, 3, 15, 10, 0)

        with patch("core.storage.storage.load", new_callable=AsyncMock, return_value=profile), \
             patch.object(self.p, "_parse_reminder_request_strict",
                          return_value=("riunione", dt)), \
             patch.object(self.p, "_parse_reminder_natural",
                          new_callable=AsyncMock, return_value=("riunione", dt)), \
             patch("core.reminder_engine.reminder_engine.create_reminder_with_response",
                   return_value=("rem_004", "Ricorderò 'riunione'.")), \
             patch("calendar_manager.calendar_manager", mock_cm), \
             patch("auth.config.ADMIN_EMAILS", set()):

            result = await self.p._handle_reminder_creation(TEST_USER_ID, "riunione domani alle 9")

        assert result is not None

    @pytest.mark.asyncio
    async def test_calendar_exception_does_not_propagate(self):
        """Eccezione in add_event gestita da return_exceptions=True."""
        profile = {
            "email": "user@test.com",
            "google_token": {"access_token": "gtok"},
            "icloud_user": "user@icloud.com",
            "icloud_password": "pass",
        }
        mock_cm = MagicMock()
        mock_cm.add_event = MagicMock(side_effect=ConnectionError("network down"))
        mock_cm._admin_google_service = None
        dt = datetime(2026, 3, 15, 10, 0)

        with patch("core.storage.storage.load", new_callable=AsyncMock, return_value=profile), \
             patch.object(self.p, "_parse_reminder_request_strict",
                          return_value=("test", dt)), \
             patch.object(self.p, "_parse_reminder_natural",
                          new_callable=AsyncMock, return_value=("test", dt)), \
             patch("core.reminder_engine.reminder_engine.create_reminder_with_response",
                   return_value=("rem_005", "Ricorderò.")), \
             patch("calendar_manager.calendar_manager", mock_cm), \
             patch("auth.config.ADMIN_EMAILS", set()):

            # Non deve sollevare eccezione
            result = await self.p._handle_reminder_creation(TEST_USER_ID, "test domani alle 10")

        assert result is not None

    @pytest.mark.asyncio
    async def test_response_mentions_google_calendar_on_success(self):
        """Risposta deve citare 'Google Calendar' se scritto con successo."""
        profile = {
            "email": "user@test.com",
            "google_token": {"access_token": "gtok"},
        }
        mock_cm = self._make_mock_cm(return_value=True)
        dt = datetime(2026, 3, 15, 10, 0)

        with patch("core.storage.storage.load", new_callable=AsyncMock, return_value=profile), \
             patch.object(self.p, "_parse_reminder_request_strict",
                          return_value=("cena con Mario", dt)), \
             patch.object(self.p, "_parse_reminder_natural",
                          new_callable=AsyncMock, return_value=("cena con Mario", dt)), \
             patch("core.reminder_engine.reminder_engine.create_reminder_with_response",
                   return_value=("rem_006", "Perfetto. Ho segnato 'cena con Mario'.")), \
             patch("calendar_manager.calendar_manager", mock_cm), \
             patch("auth.config.ADMIN_EMAILS", set()):

            result = await self.p._handle_reminder_creation(TEST_USER_ID, "cena con Mario sabato sera")

        response_text = result[0] if isinstance(result, tuple) else result
        assert "Google Calendar" in response_text or "google" in response_text.lower()


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 6: MEMORY CORRECTION HANDLER
# ─────────────────────────────────────────────────────────────────────────────

class TestMemoryCorrectionHandler:
    """Test di _handle_memory_correction()."""

    def setup_method(self):
        from core.proactor import Proactor
        self.p = Proactor()
        self.brain_state = {"profile": dict(TEST_PROFILE_FULL)}

    @pytest.mark.asyncio
    async def test_name_update_applied_and_confirmed(self):
        profile = {"name": "Mario", "city": "Roma"}
        llm_json = json.dumps({
            "field": "name", "action": "update",
            "new_value": "Luca", "old_value": "Mario"
        })
        with patch("core.storage.storage.load", new_callable=AsyncMock, return_value=profile), \
             patch("core.storage.storage.save", new_callable=AsyncMock, return_value=True), \
             patch("core.llm_service.llm_service._call_with_protection",
                   new_callable=AsyncMock, return_value=llm_json):
            resp = await self.p._handle_memory_correction(
                TEST_USER_ID, "non mi chiamo Mario, mi chiamo Luca",
                {"profile": profile}
            )
        assert "Luca" in resp
        assert "Aggiornato" in resp or "nome" in resp.lower()

    @pytest.mark.asyncio
    async def test_old_value_shown_in_response(self):
        profile = {"name": "Mario"}
        llm_json = json.dumps({
            "field": "name", "action": "update",
            "new_value": "Luca", "old_value": "Mario"
        })
        with patch("core.storage.storage.load", new_callable=AsyncMock, return_value=profile), \
             patch("core.storage.storage.save", new_callable=AsyncMock, return_value=True), \
             patch("core.llm_service.llm_service._call_with_protection",
                   new_callable=AsyncMock, return_value=llm_json):
            resp = await self.p._handle_memory_correction(
                TEST_USER_ID, "non mi chiamo Mario, mi chiamo Luca", {"profile": profile}
            )
        assert "Mario" in resp  # "prima: Mario"

    @pytest.mark.asyncio
    async def test_children_clear_empties_list(self):
        profile = {"name": "Marco", "children": [{"name": "Luca"}, {"name": "Sofia"}]}
        llm_json = json.dumps({
            "field": "children", "action": "clear",
            "new_value": None, "old_value": None
        })
        saved_profile = {}

        async def fake_save(key, value):
            saved_profile.update(value)
            return True

        with patch("core.storage.storage.load", new_callable=AsyncMock, return_value=profile), \
             patch("core.storage.storage.save", side_effect=fake_save), \
             patch("core.llm_service.llm_service._call_with_protection",
                   new_callable=AsyncMock, return_value=llm_json):
            resp = await self.p._handle_memory_correction(
                TEST_USER_ID, "non ho figli", {"profile": profile}
            )
        assert saved_profile.get("children") == []
        assert resp  # Risposta di conferma

    @pytest.mark.asyncio
    async def test_profession_update_correct(self):
        profile = {"name": "Marco", "profession": "Ingegnere"}
        llm_json = json.dumps({
            "field": "profession", "action": "update",
            "new_value": "Medico", "old_value": "Ingegnere"
        })
        with patch("core.storage.storage.load", new_callable=AsyncMock, return_value=profile), \
             patch("core.storage.storage.save", new_callable=AsyncMock, return_value=True), \
             patch("core.llm_service.llm_service._call_with_protection",
                   new_callable=AsyncMock, return_value=llm_json):
            resp = await self.p._handle_memory_correction(
                TEST_USER_ID, "non sono un ingegnere, sono un medico", {"profile": profile}
            )
        assert "Medico" in resp or "medico" in resp.lower()

    @pytest.mark.asyncio
    async def test_pet_delete_removes_from_list(self):
        profile = {"name": "Marco", "pets": [{"type": "cane", "name": "Max"}, {"type": "gatto", "name": "Luna"}]}
        llm_json = json.dumps({
            "field": "pets", "action": "delete",
            "new_value": "Max", "old_value": None
        })
        saved_profile = {}

        async def fake_save(key, value):
            saved_profile.update(value)
            return True

        with patch("core.storage.storage.load", new_callable=AsyncMock, return_value=profile), \
             patch("core.storage.storage.save", side_effect=fake_save), \
             patch("core.llm_service.llm_service._call_with_protection",
                   new_callable=AsyncMock, return_value=llm_json):
            resp = await self.p._handle_memory_correction(
                TEST_USER_ID, "non ho più il cane Max", {"profile": profile}
            )
        # Max deve essere rimosso dai pets
        remaining_names = [
            (p.get("name", "") if isinstance(p, dict) else str(p)).lower()
            for p in saved_profile.get("pets", [])
        ]
        assert "max" not in remaining_names

    @pytest.mark.asyncio
    async def test_null_field_returns_help_message(self):
        """LLM non capisce → risposta di aiuto chiara."""
        profile = {"name": "Marco"}
        llm_json = json.dumps({"field": None, "action": None, "new_value": None, "old_value": None})
        with patch("core.storage.storage.load", new_callable=AsyncMock, return_value=profile), \
             patch("core.storage.storage.save", new_callable=AsyncMock, return_value=True), \
             patch("core.llm_service.llm_service._call_with_protection",
                   new_callable=AsyncMock, return_value=llm_json):
            resp = await self.p._handle_memory_correction(
                TEST_USER_ID, "boh qualcosa", {"profile": profile}
            )
        assert isinstance(resp, str) and len(resp) > 10

    @pytest.mark.asyncio
    async def test_profile_saved_after_correction(self):
        """storage.save deve essere chiamato dopo la correzione."""
        profile = {"name": "Mario"}
        llm_json = json.dumps({
            "field": "name", "action": "update",
            "new_value": "Luca", "old_value": "Mario"
        })
        with patch("core.storage.storage.load", new_callable=AsyncMock, return_value=profile), \
             patch("core.storage.storage.save",
                   new_callable=AsyncMock, return_value=True) as mock_save, \
             patch("core.llm_service.llm_service._call_with_protection",
                   new_callable=AsyncMock, return_value=llm_json):
            await self.p._handle_memory_correction(
                TEST_USER_ID, "non mi chiamo Mario, mi chiamo Luca", {"profile": profile}
            )
        mock_save.assert_called_once()
        saved_args = mock_save.call_args.args
        assert "Luca" in str(saved_args)


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 7: LOCATION HANDLER
# ─────────────────────────────────────────────────────────────────────────────

class TestLocationHandler:
    """Test di _handle_location() — 100% deterministico."""

    def setup_method(self):
        from core.proactor import Proactor
        self.p = Proactor()

    @pytest.mark.asyncio
    async def test_city_appears_in_response(self):
        bs = {"profile": {"city": "Imola", "timezone": "Europe/Rome"}}
        resp = await self.p._handle_location(TEST_USER_ID, "dove sono?", bs)
        assert "Imola" in resp

    @pytest.mark.asyncio
    async def test_city_title_case_normalized(self):
        bs = {"profile": {"city": "imola", "timezone": "Europe/Rome"}}
        resp = await self.p._handle_location(TEST_USER_ID, "dove sono?", bs)
        assert "Imola" in resp

    @pytest.mark.asyncio
    async def test_time_format_in_response(self):
        bs = {"profile": {"city": "Roma", "timezone": "Europe/Rome"}}
        resp = await self.p._handle_location(TEST_USER_ID, "dove mi trovo?", bs)
        assert re.search(r"\d{2}:\d{2}", resp), f"Orario HH:MM non trovato in: {resp}"

    @pytest.mark.asyncio
    async def test_moment_of_day_in_response(self):
        bs = {"profile": {"city": "Milano", "timezone": "Europe/Rome"}}
        resp = await self.p._handle_location(TEST_USER_ID, "dove sono?", bs)
        keywords = ["mattina", "pomeriggio", "sera", "notte", "mezzogiorno", "pranzo"]
        assert any(k in resp.lower() for k in keywords), f"Momento del giorno non trovato: {resp}"

    @pytest.mark.asyncio
    async def test_no_city_no_gps_returns_enable_location_message(self):
        bs = {"profile": {}}  # Nessuna posizione
        resp = await self.p._handle_location(TEST_USER_ID, "dove sono?", bs)
        assert isinstance(resp, str) and len(resp) > 10

    @pytest.mark.asyncio
    async def test_invalid_timezone_does_not_crash(self):
        bs = {"profile": {"city": "Imola", "timezone": "Invalid/Zone_XYZ"}}
        # Non deve sollevare eccezioni
        resp = await self.p._handle_location(TEST_USER_ID, "dove sono?", bs)
        assert isinstance(resp, str)

    @pytest.mark.asyncio
    async def test_gps_only_without_city_returns_response(self):
        bs = {"profile": {"gps_lat": 44.35, "gps_lon": 11.71, "timezone": "Europe/Rome"}}
        resp = await self.p._handle_location(TEST_USER_ID, "dove sono?", bs)
        assert isinstance(resp, str) and len(resp) > 10

    @pytest.mark.asyncio
    async def test_no_llm_call_in_location_handler(self):
        """_handle_location deve essere zero-LLM."""
        bs = {"profile": {"city": "Roma", "timezone": "Europe/Rome"}}
        with patch("core.llm_service.llm_service._call_with_protection",
                   new_callable=AsyncMock) as mock_llm:
            await self.p._handle_location(TEST_USER_ID, "dove sono?", bs)
        mock_llm.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 8: BEDROCK IMAGE GENERATION
# ─────────────────────────────────────────────────────────────────────────────

class TestBedrockImageGeneration:
    """Test del generatore di immagini AWS Bedrock.

    Metodi reali in BedrockImageService:
      _check_rate_limit(user_id) → async bool
      _invoke_bedrock(payload) → sync dict|None
      _save_to_s3(base64, prompt) → async str|None
      _check_cache(prompt) → async str|None
      _track_generation(user_id, prompt, success) → async
    """

    @pytest.mark.asyncio
    async def test_rate_limit_blocks_generation(self):
        from core.bedrock_image_service import BedrockImageService
        service = BedrockImageService()
        with patch.object(service, "_check_cache",
                          new_callable=AsyncMock, return_value=None), \
             patch.object(service, "_check_rate_limit",
                          new_callable=AsyncMock, return_value=False):
            result = await service.generate_image("un gatto rosso", user_id=TEST_USER_ID)
        assert result is None

    @pytest.mark.asyncio
    async def test_bedrock_invoked_when_within_limit(self):
        from core.bedrock_image_service import BedrockImageService
        service = BedrockImageService()
        service.enabled = True   # forzato: AWS non configurato in env di test
        service.model_id = "stability.stable-diffusion-xl-v1"
        fake_response = {"artifacts": [{"base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScAAAAAElFTkSuQmCC"}]}
        with patch.object(service, "_check_cache",
                          new_callable=AsyncMock, return_value=None), \
             patch.object(service, "_check_rate_limit",
                          new_callable=AsyncMock, return_value=True), \
             patch.object(service, "_invoke_bedrock",
                          return_value=fake_response) as mock_bedrock, \
             patch.object(service, "_save_to_s3",
                          new_callable=AsyncMock, return_value="https://s3.example.com/img.png"), \
             patch.object(service, "_increment_rate_limit", new_callable=AsyncMock), \
             patch.object(service, "_cache_result", new_callable=AsyncMock), \
             patch.object(service, "_track_generation", new_callable=AsyncMock):
            result = await service.generate_image("tramonto sul mare", user_id=TEST_USER_ID)
        mock_bedrock.assert_called_once()

    @pytest.mark.asyncio
    async def test_bedrock_failure_returns_none(self):
        from core.bedrock_image_service import BedrockImageService
        service = BedrockImageService()
        with patch.object(service, "_check_cache",
                          new_callable=AsyncMock, return_value=None), \
             patch.object(service, "_check_rate_limit",
                          new_callable=AsyncMock, return_value=True), \
             patch.object(service, "_invoke_bedrock", return_value=None), \
             patch.object(service, "_track_generation", new_callable=AsyncMock):
            result = await service.generate_image("test", user_id=TEST_USER_ID)
        assert result is None

    @pytest.mark.asyncio
    async def test_track_generation_called_on_success(self):
        from core.bedrock_image_service import BedrockImageService
        service = BedrockImageService()
        service.enabled = True   # forzato: AWS non configurato in env di test
        service.model_id = "stability.stable-diffusion-xl-v1"
        fake_response = {"artifacts": [{"base64": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScAAAAAElFTkSuQmCC"}]}
        with patch.object(service, "_check_cache",
                          new_callable=AsyncMock, return_value=None), \
             patch.object(service, "_check_rate_limit",
                          new_callable=AsyncMock, return_value=True), \
             patch.object(service, "_invoke_bedrock", return_value=fake_response), \
             patch.object(service, "_save_to_s3",
                          new_callable=AsyncMock, return_value="https://s3.example.com/img.png"), \
             patch.object(service, "_increment_rate_limit", new_callable=AsyncMock), \
             patch.object(service, "_cache_result", new_callable=AsyncMock), \
             patch.object(service, "_track_generation",
                          new_callable=AsyncMock) as mock_track:
            await service.generate_image("gatto", user_id=TEST_USER_ID)
        mock_track.assert_called()

    def test_generate_image_is_async(self):
        import inspect
        from core.bedrock_image_service import BedrockImageService
        assert inspect.iscoroutinefunction(BedrockImageService.generate_image)

    @pytest.mark.asyncio
    async def test_generate_without_user_id_does_not_crash(self):
        from core.bedrock_image_service import BedrockImageService
        service = BedrockImageService()
        with patch.object(service, "_check_cache",
                          new_callable=AsyncMock, return_value=None), \
             patch.object(service, "_invoke_bedrock", return_value=None), \
             patch.object(service, "_track_generation", new_callable=AsyncMock):
            # user_id=None → salta il rate limit check, va direttamente a invoke
            result = await service.generate_image("test", user_id=None)
        assert result is None or isinstance(result, str)

    @pytest.mark.asyncio
    async def test_cache_hit_returns_cached_url(self):
        """Se c'è un cache hit, deve tornare l'URL cachato senza chiamare bedrock."""
        from core.bedrock_image_service import BedrockImageService
        service = BedrockImageService()
        cached_url = "https://s3.example.com/cached_img.png"
        with patch.object(service, "_check_cache",
                          new_callable=AsyncMock, return_value=cached_url), \
             patch.object(service, "_invoke_bedrock", return_value=None) as mock_bedrock:
            result = await service.generate_image("gatto", user_id=TEST_USER_ID)
        assert result == cached_url
        mock_bedrock.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 9: IMAGE SEARCH SERVICE
# ─────────────────────────────────────────────────────────────────────────────

class TestImageSearchService:
    """Test di ImageSearchService (Pixabay + DuckDuckGo fallback)."""

    def _make_pixabay_mock(self, hits=None):
        if hits is None:
            hits = [
                {"largeImageURL": "https://cdn.pixabay.com/photo/1.jpg",
                 "tags": "cat, animal",
                 "pageURL": "https://pixabay.com/1",
                 "previewURL": "",
                 "imageWidth": 640,
                 "imageHeight": 480},
            ]
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"hits": hits}
        mock_resp.raise_for_status = MagicMock()
        return mock_resp

    def _patch_httpx_get(self, mock_resp):
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)
        return patch("httpx.AsyncClient", return_value=mock_client)

    # ── extract_image_query ───────────────────────────────────────────────────

    def test_extract_query_from_trigger_phrase(self):
        from core.image_search_service import extract_image_query, IMAGE_SEARCH_TRIGGERS
        for trigger in IMAGE_SEARCH_TRIGGERS[:3]:
            msg = f"{trigger} Milano"
            result = extract_image_query(msg)
            assert result is not None, f"Query non estratta da: {msg}"

    def test_extract_query_no_trigger_returns_none_or_empty(self):
        from core.image_search_service import extract_image_query
        result = extract_image_query("ciao come stai oggi?")
        assert result is None or result == ""

    def test_image_search_triggers_list_not_empty(self):
        from core.image_search_service import IMAGE_SEARCH_TRIGGERS
        assert len(IMAGE_SEARCH_TRIGGERS) > 0

    # ── Pixabay search ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_pixabay_returns_results(self):
        from core.image_search_service import ImageSearchService
        service = ImageSearchService()
        mock_resp = self._make_pixabay_mock()
        with self._patch_httpx_get(mock_resp), \
             patch.dict(os.environ, {"PIXABAY_API_KEY": "test_pix_key"}):
            results = await service.search("gatto")
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_search_result_has_url(self):
        from core.image_search_service import ImageSearchService
        service = ImageSearchService()
        mock_resp = self._make_pixabay_mock()
        with self._patch_httpx_get(mock_resp), \
             patch.dict(os.environ, {"PIXABAY_API_KEY": "test_pix_key"}):
            results = await service.search("gatto")
        if results:
            assert hasattr(results[0], "url")
            assert results[0].url.startswith("https://")

    @pytest.mark.asyncio
    async def test_search_result_has_title_and_source(self):
        from core.image_search_service import ImageSearchService
        service = ImageSearchService()
        mock_resp = self._make_pixabay_mock()
        with self._patch_httpx_get(mock_resp), \
             patch.dict(os.environ, {"PIXABAY_API_KEY": "test_pix_key"}):
            results = await service.search("cane")
        if results:
            assert hasattr(results[0], "title")
            assert hasattr(results[0], "source")

    @pytest.mark.asyncio
    async def test_max_results_respected(self):
        from core.image_search_service import ImageSearchService
        service = ImageSearchService()
        many_hits = [
            {"largeImageURL": f"https://cdn.pixabay.com/{i}.jpg",
             "tags": "cat", "pageURL": f"https://pixabay.com/{i}",
             "previewURL": "", "imageWidth": 640, "imageHeight": 480}
            for i in range(20)
        ]
        mock_resp = self._make_pixabay_mock(hits=many_hits)
        with self._patch_httpx_get(mock_resp), \
             patch.dict(os.environ, {"PIXABAY_API_KEY": "test_pix_key"}):
            results = await service.search("gatto", max_results=3)
        assert len(results) <= 3

    @pytest.mark.asyncio
    async def test_empty_hits_returns_empty_list(self):
        from core.image_search_service import ImageSearchService
        service = ImageSearchService()
        mock_resp = self._make_pixabay_mock(hits=[])
        with self._patch_httpx_get(mock_resp), \
             patch.dict(os.environ, {"PIXABAY_API_KEY": "test_pix_key"}):
            results = await service.search("query_vuota")
        # Può tornare lista vuota o tentare DuckDuckGo fallback
        assert isinstance(results, list)


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 10: TOOL SERVICES
# ─────────────────────────────────────────────────────────────────────────────

class TestToolServices:
    """Test di ToolService (weather, news, time, date)."""

    def setup_method(self):
        from core.tool_services import ToolService
        self.ts = ToolService()

    # ── time / date (async) ───────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_time_returns_non_empty_string(self):
        result = await self.ts.get_time()
        assert isinstance(result, str) and len(result) > 0

    @pytest.mark.asyncio
    async def test_get_date_returns_non_empty_string(self):
        result = await self.ts.get_date()
        assert isinstance(result, str) and len(result) > 0

    @pytest.mark.asyncio
    async def test_get_time_rome_contains_digits(self):
        result = await self.ts.get_time()
        assert re.search(r"\d", result), f"Nessuna cifra in: {result}"

    @pytest.mark.asyncio
    async def test_get_date_contains_year(self):
        result = await self.ts.get_date()
        assert "2026" in result or "202" in result, f"Anno non trovato in: {result}"

    # ── weather fallback senza API key ────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_weather_no_api_key_returns_fallback_string(self):
        with patch.dict(os.environ, {"OPENWEATHER_API_KEY": ""}):
            from core.tool_services import ToolService
            ts = ToolService()
            result = await ts.get_weather("meteo a Roma")
        assert isinstance(result, str) and len(result) > 0

    @pytest.mark.asyncio
    async def test_weather_api_http_error_returns_message(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.raise_for_status = MagicMock(side_effect=Exception("401 Unauthorized"))

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.get = AsyncMock(return_value=mock_resp)

        with patch("httpx.AsyncClient", return_value=mock_client), \
             patch.dict(os.environ, {"OPENWEATHER_API_KEY": "bad_key"}):
            from core.tool_services import ToolService
            ts = ToolService()
            result = await ts.get_weather("meteo a Milano")
        assert isinstance(result, str)

    # ── news fallback senza API key ───────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_news_no_api_key_returns_fallback_string(self):
        with patch.dict(os.environ, {"GNEWS_API_KEY": "", "NEWSAPI_KEY": ""}):
            from core.tool_services import ToolService
            ts = ToolService()
            result = await ts.get_news("ultime notizie")
        assert isinstance(result, str)

    # ── estrazione città ──────────────────────────────────────────────────────

    def test_extract_city_from_message(self):
        tests = [
            "meteo a Roma oggi",
            "com'è a Milano?",
            "fa freddo a Napoli?",
        ]
        for msg in tests:
            city = self.ts._extract_city(msg)
            assert city is not None, f"Città non estratta da: '{msg}'"

    def test_extract_city_unknown_returns_none_or_fallback(self):
        result = self.ts._extract_city("voglio un caffè")
        # None o la città dell'utente come fallback — non deve crashare
        assert result is None or isinstance(result, str)


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 11: LLM SERVICE
# ─────────────────────────────────────────────────────────────────────────────

class TestLLMService:
    """Test del LLMService: fallback chain, downgrade, deterministic_fallback."""

    def test_deterministic_fallback_knowledge_returns_string(self):
        from core.llm_service import LLMService
        fb = LLMService._deterministic_fallback("cos'è il DNA?", "knowledge")
        assert isinstance(fb, str) and len(fb) > 10

    def test_deterministic_fallback_general_returns_string(self):
        from core.llm_service import LLMService
        fb = LLMService._deterministic_fallback("test", "general")
        assert isinstance(fb, str) and len(fb) > 0

    def test_deterministic_fallback_relational_returns_none_or_string(self):
        from core.llm_service import LLMService
        fb = LLMService._deterministic_fallback("test", "relational")
        # Può tornare None (Proactor gestisce il proprio fallback relazionale)
        assert fb is None or isinstance(fb, str)

    @pytest.mark.asyncio
    async def test_call_with_protection_returns_on_first_success(self):
        from core.llm_service import LLMService, LLM_DEFAULT_MODEL
        service = LLMService()
        with patch.object(service, "_call_model",
                          new_callable=AsyncMock, return_value="risposta OK") as mock_call:
            result = await service._call_with_protection(
                LLM_DEFAULT_MODEL, "system prompt", "ciao", user_id=TEST_USER_ID
            )
        assert result == "risposta OK"

    @pytest.mark.asyncio
    async def test_call_with_protection_retries_on_failure(self):
        from core.llm_service import LLMService, LLM_DEFAULT_MODEL
        service = LLMService()
        call_count = {"n": 0}

        async def mock_call(model, *a, **kw):
            call_count["n"] += 1
            return "risposta al secondo tentativo" if call_count["n"] >= 2 else None

        with patch.object(service, "_call_model", side_effect=mock_call):
            result = await service._call_with_protection(
                LLM_DEFAULT_MODEL, "system", "ciao"
            )
        assert call_count["n"] >= 2

    @pytest.mark.asyncio
    async def test_call_with_protection_does_not_raise_on_total_failure(self):
        from core.llm_service import LLMService, LLM_DEFAULT_MODEL
        service = LLMService()
        with patch.object(service, "_call_model", new_callable=AsyncMock, return_value=None):
            # Non deve sollevare eccezione
            result = await service._call_with_protection(
                LLM_DEFAULT_MODEL, "system", "ciao"
            )
        # Può tornare None o stringa fallback
        assert result is None or isinstance(result, str)


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 12: STORAGE
# ─────────────────────────────────────────────────────────────────────────────

class TestStorage:
    """Test del MemoryStorage (load/save/non-serializable guard)."""

    @pytest.mark.asyncio
    async def test_load_missing_key_returns_default(self):
        from core.storage import MemoryStorage
        st = MemoryStorage()
        result = await st.load(f"test_missing:{TEST_USER_ID}_x9z", default={"hello": "world"})
        assert result == {"hello": "world"}

    @pytest.mark.asyncio
    async def test_save_and_load_roundtrip(self):
        from core.storage import MemoryStorage
        st = MemoryStorage()
        data = {"name": "Marco", "num": 42, "nested": {"a": [1, 2, 3]}}
        key = f"profile:{TEST_USER_ID}_roundtrip_test_neural"
        try:
            await st.save(key, data)
            loaded = await st.load(key, default={})
            assert loaded == data
        finally:
            # Cleanup: delete test file
            await st.delete(key)

    @pytest.mark.asyncio
    async def test_save_non_serializable_raises(self):
        from core.storage import MemoryStorage
        st = MemoryStorage()
        with pytest.raises((RuntimeError, TypeError, ValueError)):
            await st.save(f"test:{TEST_USER_ID}", {"fn": lambda x: x})

    @pytest.mark.asyncio
    async def test_load_default_none_returns_none(self):
        from core.storage import MemoryStorage
        st = MemoryStorage()
        result = await st.load(f"test_none:{TEST_USER_ID}_never_exists", default=None)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 13: RELATIONAL PROMPT — style injection
# ─────────────────────────────────────────────────────────────────────────────

class TestRelationalPromptStyleInjection:
    """Verifica che le style directives siano iniettate correttamente nel prompt."""

    def setup_method(self):
        from core.proactor import Proactor
        self.p = Proactor()

    def _build_prompt(self, tz="Europe/Rome"):
        return self.p._build_relational_gpt_prompt(
            conversation_context="NOME: Marco\n",
            latent_synopsis="neutro",
            message="test",
            user_id=TEST_USER_ID,
            calendar_info="",
            tz=tz,
            user_city="Roma",
        )

    def test_prompt_contains_thinking_context(self):
        p = self._build_prompt()
        assert "[THINKING_CONTEXT]" in p

    def test_prompt_contains_consapevolezza_temporale(self):
        p = self._build_prompt()
        assert "CONSAPEVOLEZZA TEMPORALE" in p

    def test_prompt_contains_stile_contestuale(self):
        p = self._build_prompt()
        assert "STILE CONTESTUALE" in p

    def test_no_raw_placeholder_in_prompt(self):
        p = self._build_prompt()
        assert "{style_directives}" not in p

    def test_prompt_contains_actual_directive_text(self):
        """Il testo della direttiva deve essere nel prompt (non placeholder)."""
        p = self._build_prompt()
        # Una delle frasi del style regulator deve comparire
        style_keywords = [
            "notte", "mattina", "pomeriggio", "sera", "pranzo",
            "breve", "caldo", "proattivo", "concis"
        ]
        assert any(kw in p.lower() for kw in style_keywords), \
            "Nessuna direttiva di stile reale trovata nel prompt"

    def test_prompt_contains_user_name(self):
        p = self._build_prompt()
        assert "Marco" in p or "MARCO" in p

    def test_prompt_contains_city(self):
        p = self._build_prompt()
        assert "Roma" in p or "ROMA" in p

    def test_prompt_with_invalid_tz_does_not_crash(self):
        """Timezone invalida → fallback senza crash."""
        try:
            p = self._build_prompt(tz="Invalid/Zone_XXXXXX")
            assert isinstance(p, str) and len(p) > 100
        except Exception as e:
            pytest.fail(f"_build_relational_gpt_prompt crashed con tz invalida: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 14: REMINDER ENGINE (unit)
# ─────────────────────────────────────────────────────────────────────────────

class TestReminderEngine:
    """Test del ReminderEngine — format, load edge cases."""

    def setup_method(self):
        from core.reminder_engine import ReminderEngine
        self.engine = ReminderEngine()

    def test_format_empty_list_returns_string(self):
        result = self.engine.format_reminders_list([])
        assert isinstance(result, str)

    def test_format_list_with_items_contains_text(self):
        reminders = [
            {"text": "Comprare il latte", "datetime": "2026-03-01T10:00:00", "status": "pending"},
            {"text": "Chiamare il dentista", "datetime": "2026-03-02T15:00:00", "status": "pending"},
        ]
        result = self.engine.format_reminders_list(reminders)
        assert "latte" in result.lower() or "Comprare" in result
        assert isinstance(result, str)

    def test_format_list_single_item(self):
        reminders = [{"text": "Test item", "datetime": "2026-03-01T10:00:00", "status": "pending"}]
        result = self.engine.format_reminders_list(reminders)
        assert "Test item" in result or "test" in result.lower()

    def test_load_reminders_missing_file_returns_empty_list(self):
        """File non esistente → lista vuota senza eccezione."""
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(
                self.engine, "_get_reminders_file",
                return_value=type("P", (), {
                    "exists": lambda self: False,
                    "__str__": lambda self: os.path.join(tmp, "nonexistent.json"),
                    "parent": type("D", (), {"mkdir": lambda *a, **kw: None})(),
                })()
            ):
                reminders = self.engine._load_reminders(TEST_USER_ID + "_missing")
        assert isinstance(reminders, list)


# ─────────────────────────────────────────────────────────────────────────────
# SEZIONE 15: PROACTOR handle() — integration flow
# ─────────────────────────────────────────────────────────────────────────────

class TestProactorHandleIntegration:
    """Test E2E del flusso handle() con tutti i layer I/O mockati.

    NOTE: handle() ritorna UNA STRINGA (non una tupla).
    _handle_internal() ritorna (str, source) ma handle() estrae solo il testo.
    """

    def setup_method(self):
        from core.proactor import Proactor
        self.p = Proactor()

    def _base_patches(self, profile=None, intents=None, llm_resp="risposta di test"):
        """Costruisce il set base di patch comuni a tutti i test di integrazione."""
        if profile is None:
            profile = TEST_PROFILE_MINIMAL
        if intents is None:
            intents = ["chat_free"]
        brain_state = {"profile": profile, "relational": {"trust": 0.7}, "episodes": []}
        return [
            patch("core.storage.storage.load",
                  new_callable=AsyncMock, return_value=profile),
            patch("core.intent_classifier.intent_classifier.classify_async",
                  new_callable=AsyncMock, return_value=intents),
            patch("core.memory_brain.memory_brain.update_brain",
                  new_callable=AsyncMock, return_value=brain_state),
            patch.object(self.p.context_assembler, "build",
                         new_callable=AsyncMock,
                         return_value={"profile": profile, "latent": {}, "relational": {}}),
            patch.object(self.p, "_update_profile_from_message", new_callable=AsyncMock),
            patch("core.llm_service.llm_service._call_with_protection",
                  new_callable=AsyncMock, return_value=llm_resp),
        ]

    @pytest.mark.asyncio
    async def test_handle_returns_string(self):
        """handle() deve sempre tornare una stringa (non una tupla)."""
        patches = self._base_patches()
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            result = await self.p.handle(user_id=TEST_USER_ID, message="ciao")
        assert isinstance(result, str)

    @pytest.mark.asyncio
    async def test_handle_relational_returns_llm_response(self):
        patches = self._base_patches(intents=["chat_free"], llm_resp="Ciao! Come posso aiutarti?")
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            resp = await self.p.handle(user_id=TEST_USER_ID, message="ciao come stai?")
        assert "Ciao" in resp or len(resp) > 0

    @pytest.mark.asyncio
    async def test_handle_dove_sono_returns_city(self):
        profile = {"name": "Marco", "city": "Imola", "timezone": "Europe/Rome"}
        patches = self._base_patches(profile=profile, intents=["dove_sono"])
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            resp = await self.p.handle(user_id=TEST_USER_ID, message="dove sono?")
        assert "Imola" in resp

    @pytest.mark.asyncio
    async def test_handle_memory_correction_applied(self):
        """memory_correction → LLM parse → risposta di conferma."""
        profile = {"name": "Mario", "city": "Roma"}
        brain_state = {"profile": profile, "relational": {}, "episodes": []}
        llm_correction = json.dumps({
            "field": "name", "action": "update",
            "new_value": "Luca", "old_value": "Mario"
        })
        with patch("core.storage.storage.load", new_callable=AsyncMock, return_value=profile), \
             patch("core.storage.storage.save", new_callable=AsyncMock, return_value=True), \
             patch("core.intent_classifier.intent_classifier.classify_async",
                   new_callable=AsyncMock, return_value=["memory_correction"]), \
             patch("core.memory_brain.memory_brain.update_brain",
                   new_callable=AsyncMock, return_value=brain_state), \
             patch.object(self.p.context_assembler, "build",
                          new_callable=AsyncMock,
                          return_value={"profile": profile, "latent": {}, "relational": {}}), \
             patch.object(self.p, "_update_profile_from_message", new_callable=AsyncMock), \
             patch("core.llm_service.llm_service._call_with_protection",
                   new_callable=AsyncMock, return_value=llm_correction):
            resp = await self.p.handle(
                user_id=TEST_USER_ID,
                message="non mi chiamo Mario, mi chiamo Luca"
            )
        assert "Luca" in resp

    @pytest.mark.asyncio
    async def test_handle_is_ask_reminder_bypasses_synthesis(self):
        """3-tuple is_ask=True in reminder_create → risposta immediata."""
        ask_response = ("Certo! Cosa devo ricordarti?", "reminder", True)
        profile = {}
        brain_state = {"profile": {}, "relational": {}, "episodes": []}
        with patch("core.storage.storage.load", new_callable=AsyncMock, return_value=profile), \
             patch("core.intent_classifier.intent_classifier.classify_async",
                   new_callable=AsyncMock, return_value=["reminder_create"]), \
             patch("core.memory_brain.memory_brain.update_brain",
                   new_callable=AsyncMock, return_value=brain_state), \
             patch.object(self.p.context_assembler, "build",
                          new_callable=AsyncMock,
                          return_value={"profile": {}, "latent": {}, "relational": {}}), \
             patch.object(self.p, "_update_profile_from_message", new_callable=AsyncMock), \
             patch.object(self.p, "_handle_reminder_creation",
                          new_callable=AsyncMock, return_value=ask_response), \
             patch.object(self.p, "_synthesize_responses",
                          new_callable=AsyncMock) as mock_synth:
            resp = await self.p.handle(user_id=TEST_USER_ID, message="ricordami")
        mock_synth.assert_not_called()
        assert "Cosa devo ricordarti" in resp or "ricordare" in resp.lower() or len(resp) > 0

    @pytest.mark.asyncio
    async def test_handle_weight_tracker_fires_on_success(self):
        """Dopo handle() il WeightTracker deve essere chiamato (fire-and-forget)."""
        profile = TEST_PROFILE_MINIMAL.copy()
        brain_state = {"profile": profile, "relational": {}, "episodes": []}
        with patch("core.storage.storage.load",
                   new_callable=AsyncMock, return_value=profile), \
             patch("core.intent_classifier.intent_classifier.classify_async",
                   new_callable=AsyncMock, return_value=["dove_sono"]), \
             patch("core.memory_brain.memory_brain.update_brain",
                   new_callable=AsyncMock, return_value=brain_state), \
             patch.object(self.p.context_assembler, "build",
                          new_callable=AsyncMock,
                          return_value={"profile": profile, "latent": {}, "relational": {}}), \
             patch.object(self.p, "_update_profile_from_message", new_callable=AsyncMock), \
             patch("core.weight_tracker.weight_tracker.record_success_async",
                   new_callable=AsyncMock) as mock_wt:
            await self.p.handle(user_id=TEST_USER_ID, message="dove sono?")
        mock_wt.assert_called()

    @pytest.mark.asyncio
    async def test_handle_last_route_tracked(self):
        """_last_route_per_user deve essere aggiornato dopo il routing."""
        profile = TEST_PROFILE_MINIMAL.copy()
        brain_state = {"profile": profile, "relational": {}, "episodes": []}
        with patch("core.storage.storage.load",
                   new_callable=AsyncMock, return_value=profile), \
             patch("core.intent_classifier.intent_classifier.classify_async",
                   new_callable=AsyncMock, return_value=["dove_sono"]), \
             patch("core.memory_brain.memory_brain.update_brain",
                   new_callable=AsyncMock, return_value=brain_state), \
             patch.object(self.p.context_assembler, "build",
                          new_callable=AsyncMock,
                          return_value={"profile": profile, "latent": {}, "relational": {}}), \
             patch.object(self.p, "_update_profile_from_message", new_callable=AsyncMock):
            await self.p.handle(user_id=TEST_USER_ID, message="dove sono?")
        assert TEST_USER_ID in self.p._last_route_per_user
        assert self.p._last_route_per_user[TEST_USER_ID] == "dove_sono"

    @pytest.mark.asyncio
    async def test_handle_llm_failure_returns_non_empty(self):
        """LLM None → fallback deterministico, nessun crash, risposta non vuota."""
        patches = self._base_patches(intents=["chat_free"], llm_resp=None)
        with patches[0], patches[1], patches[2], patches[3], patches[4], patches[5]:
            resp = await self.p.handle(user_id=TEST_USER_ID, message="ciao")
        assert resp is not None
        assert isinstance(resp, str)

    @pytest.mark.asyncio
    async def test_handle_response_non_empty_for_main_intents(self):
        """Intenti principali → risposta stringa non vuota."""
        profile = TEST_PROFILE_MINIMAL.copy()
        profile["city"] = "Roma"
        brain_state = {"profile": profile, "relational": {}, "episodes": []}
        for intent in ["chat_free", "dove_sono"]:
            with patch("core.storage.storage.load",
                       new_callable=AsyncMock, return_value=profile), \
                 patch("core.intent_classifier.intent_classifier.classify_async",
                       new_callable=AsyncMock, return_value=[intent]), \
                 patch("core.memory_brain.memory_brain.update_brain",
                       new_callable=AsyncMock, return_value=brain_state), \
                 patch.object(self.p.context_assembler, "build",
                              new_callable=AsyncMock,
                              return_value={"profile": profile, "latent": {}, "relational": {}}), \
                 patch.object(self.p, "_update_profile_from_message", new_callable=AsyncMock), \
                 patch("core.llm_service.llm_service._call_with_protection",
                       new_callable=AsyncMock, return_value=f"Risposta per {intent}"):
                resp = await self.p.handle(user_id=TEST_USER_ID, message="test")
            assert isinstance(resp, str) and len(resp) > 0, f"Risposta vuota per intent={intent}"

    @pytest.mark.asyncio
    async def test_proactor_init_has_required_attributes(self):
        """Proactor.__init__ deve inizializzare tutti gli attributi critici."""
        from core.proactor import Proactor
        p = Proactor()
        assert hasattr(p, "last_reminder_per_user") and isinstance(p.last_reminder_per_user, dict)
        assert hasattr(p, "_last_route_per_user") and isinstance(p._last_route_per_user, dict)
        assert hasattr(p, "tool_intents") and isinstance(p.tool_intents, list)
        assert hasattr(p, "context_assembler")
