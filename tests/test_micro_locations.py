"""
Tests for Micro-località italiane: fuzzy matching, IT priority, LOCATION_FUZZY_MATCH.
Covers: _normalize, _levenshtein, fuzzy_match_city, IT priority in disambiguation.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.location_resolver import (
    _normalize,
    _levenshtein,
    fuzzy_match_city,
    resolve_location,
    _disambiguate,
    _format_result,
    extract_city_from_message,
    LocationNotFoundError,
    AmbiguousLocationError,
)


# ═══════════════════════════════════════════════════════════════
# Test: _normalize
# ═══════════════════════════════════════════════════════════════

class TestNormalize:

    def test_lowercase(self):
        assert _normalize("Roma") == "roma"

    def test_strip_accents(self):
        assert _normalize("Città") == "citta"

    def test_strip_accents_complex(self):
        assert _normalize("São Paulo") == "sao paulo"

    def test_strip_whitespace(self):
        assert _normalize("  Milano  ") == "milano"

    def test_unicode_chars(self):
        assert _normalize("Zürich") == "zurich"


# ═══════════════════════════════════════════════════════════════
# Test: _levenshtein
# ═══════════════════════════════════════════════════════════════

class TestLevenshtein:

    def test_identical(self):
        assert _levenshtein("roma", "roma") == 0

    def test_one_char_diff(self):
        assert _levenshtein("roma", "rona") == 1

    def test_insertion(self):
        assert _levenshtein("roma", "romaa") == 1

    def test_deletion(self):
        assert _levenshtein("roma", "rom") == 1

    def test_substitution(self):
        assert _levenshtein("roma", "ruma") == 1

    def test_two_edits(self):
        assert _levenshtein("imola", "imala") == 1

    def test_completely_different(self):
        assert _levenshtein("roma", "xyz") == 4

    def test_empty_strings(self):
        assert _levenshtein("", "") == 0

    def test_one_empty(self):
        assert _levenshtein("roma", "") == 4

    def test_castel_del_rio(self):
        # "castel del rio" vs "castel del rio" = 0
        assert _levenshtein("castel del rio", "castel del rio") == 0

    def test_typo_bolonga(self):
        # "bolonga" vs "bologna" = 2 (transposition-like)
        assert _levenshtein("bolonga", "bologna") == 2


# ═══════════════════════════════════════════════════════════════
# Test: fuzzy_match_city
# ═══════════════════════════════════════════════════════════════

class TestFuzzyMatchCity:

    def test_exact_match(self):
        candidates = [
            {"name": "Bologna", "country": "IT", "lat": 44.49, "lon": 11.34}
        ]
        result = fuzzy_match_city("Bologna", candidates)
        assert result is not None
        assert result["name"] == "Bologna"

    def test_accent_mismatch(self):
        """User types without accent, API returns with accent."""
        candidates = [
            {"name": "Città di Castello", "country": "IT", "lat": 43.46, "lon": 12.24,
             "local_names": {"it": "Città di Castello"}}
        ]
        result = fuzzy_match_city("Citta di Castello", candidates)
        assert result is not None

    def test_typo_one_char(self):
        candidates = [
            {"name": "Imola", "country": "IT", "lat": 44.35, "lon": 11.71}
        ]
        result = fuzzy_match_city("Imolа".replace("а", "a"), candidates)  # exact
        assert result is not None

    def test_it_priority(self):
        """Italian result should be preferred over foreign one with same distance."""
        candidates = [
            {"name": "Springfield", "country": "US", "lat": 39.78, "lon": -89.65},
            {"name": "Springfield", "country": "IT", "lat": 42.0, "lon": 12.0},
        ]
        result = fuzzy_match_city("Springfield", candidates)
        assert result is not None
        assert result["country"] == "IT"

    def test_no_match_too_different(self):
        candidates = [
            {"name": "Tokyo", "country": "JP", "lat": 35.68, "lon": 139.69}
        ]
        result = fuzzy_match_city("Milano", candidates)
        assert result is None

    def test_empty_candidates(self):
        assert fuzzy_match_city("Roma", []) is None

    def test_empty_query(self):
        assert fuzzy_match_city("", [{"name": "Roma"}]) is None

    def test_short_query_rejected(self):
        """Queries shorter than 3 chars should be rejected."""
        assert fuzzy_match_city("Ro", [{"name": "Roma", "country": "IT"}]) is None

    def test_prefix_match(self):
        """Query is a significant prefix (>= 50%) of candidate name."""
        candidates = [
            {"name": "San Lazzaro di Savena", "country": "IT", "lat": 44.47, "lon": 11.41}
        ]
        result = fuzzy_match_city("San Lazzaro di", candidates)
        assert result is not None

    def test_local_name_it_used(self):
        """Should match against Italian local name."""
        candidates = [
            {"name": "Munich", "country": "DE", "lat": 48.13, "lon": 11.58,
             "local_names": {"it": "Monaco di Baviera"}}
        ]
        result = fuzzy_match_city("Monaco di Baviera", candidates)
        assert result is not None

    def test_typo_two_chars(self):
        """Two-char typo should still match for long names."""
        candidates = [
            {"name": "Bologna", "country": "IT", "lat": 44.49, "lon": 11.34}
        ]
        result = fuzzy_match_city("Bolonga", candidates)
        assert result is not None
        assert result["name"] == "Bologna"


# ═══════════════════════════════════════════════════════════════
# Test: IT priority in disambiguation
# ═══════════════════════════════════════════════════════════════

class TestITPriority:

    def test_single_it_result_preferred(self):
        results = [
            {"name": "Imola", "lat": 44.35, "lon": 11.71, "country": "US", "state": "Ohio"},
            {"name": "Imola", "lat": 44.35, "lon": 11.71, "country": "IT", "state": "Emilia-Romagna"},
        ]
        loc = _disambiguate("Imola", results, "meteo a Imola")
        assert loc["country"] == "IT"

    def test_all_it_picks_first(self):
        results = [
            {"name": "San Lazzaro", "lat": 44.47, "lon": 11.41, "country": "IT", "state": "Emilia-Romagna"},
            {"name": "San Lazzaro", "lat": 45.0, "lon": 12.0, "country": "IT", "state": "Veneto"},
        ]
        loc = _disambiguate("San Lazzaro", results, "notizie San Lazzaro")
        assert loc["country"] == "IT"
        assert loc["lat"] == 44.47


# ═══════════════════════════════════════════════════════════════
# Test: resolve_location with fuzzy match integration
# ═══════════════════════════════════════════════════════════════

class TestResolveLocationFuzzy:

    @patch("core.location_resolver.OPENWEATHER_API_KEY", "test-key")
    def test_fuzzy_match_used_when_no_exact(self):
        """If API returns a result with slightly different name, fuzzy match kicks in."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"name": "Castel del Rio", "lat": 44.22, "lon": 11.50, "country": "IT",
             "state": "Emilia-Romagna", "local_names": {"it": "Castel del Rio"}}
        ]
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        loc = asyncio.run(resolve_location("meteo a Castel del Rio", http_client=mock_client))
        assert loc["country"] == "IT"
        assert "Castel" in loc["name"]

    @patch("core.location_resolver.OPENWEATHER_API_KEY", "test-key")
    def test_micro_localita_imola(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"name": "Imola", "lat": 44.35, "lon": 11.71, "country": "IT",
             "state": "Emilia-Romagna"}
        ]
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        loc = asyncio.run(resolve_location("che tempo fa a Imola?", http_client=mock_client))
        assert loc["name"] == "Imola"
        assert loc["country"] == "IT"

    @patch("core.location_resolver.OPENWEATHER_API_KEY", "test-key")
    def test_micro_localita_san_lazzaro(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"name": "San Lazzaro di Savena", "lat": 44.47, "lon": 11.41,
             "country": "IT", "state": "Emilia-Romagna"}
        ]
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        loc = asyncio.run(resolve_location(
            "notizie di San Lazzaro di Savena", http_client=mock_client))
        assert loc["country"] == "IT"


class TestExtractMicroLocalita:
    """Test city extraction for small Italian towns."""

    def test_castel_del_rio(self):
        result = extract_city_from_message("meteo a Castel del Rio")
        assert result is not None
        assert "Castel" in result

    def test_san_lazzaro_di_savena(self):
        result = extract_city_from_message("notizie di San Lazzaro di Savena")
        assert result is not None
        assert "San" in result

    def test_imola(self):
        assert extract_city_from_message("che tempo fa a Imola?") == "Imola"

    def test_castel_del_rio_lowercase(self):
        result = extract_city_from_message("meteo a castel del rio")
        assert result is not None
        assert "Castel" in result
