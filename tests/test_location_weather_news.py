"""
Tests for Location Resolver, Weather Tool, and News Tool.
Covers: city extraction, geocoding disambiguation, weather coord calls,
news RSS fallback chain, and error handling.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
import httpx

from core.location_resolver import (
    extract_city_from_message,
    resolve_location,
    _disambiguate,
    _format_result,
    _title_case_city,
    LocationNotFoundError,
    AmbiguousLocationError,
)


# ═══════════════════════════════════════════════════════════════
# Test: extract_city_from_message
# ═══════════════════════════════════════════════════════════════

class TestCityExtraction:

    def test_capitalized_city(self):
        assert extract_city_from_message("che tempo fa a Milano?") == "Milano"

    def test_capitalized_city_trailing(self):
        assert extract_city_from_message("meteo a Roma") == "Roma"

    def test_compound_city_lowercase(self):
        result = extract_city_from_message("meteo a reggio calabria")
        assert result == "Reggio Calabria"

    def test_compound_city_with_connector(self):
        result = extract_city_from_message("notizie di San Lazzaro di Savena")
        assert result is not None
        assert "San" in result or "san" in result.lower()

    def test_no_city(self):
        assert extract_city_from_message("che tempo fa?") is None

    def test_no_city_generic(self):
        assert extract_city_from_message("come stai?") is None

    def test_worldwide_paris(self):
        result = extract_city_from_message("meteo a Parigi")
        assert result == "Parigi"

    def test_worldwide_london(self):
        result = extract_city_from_message("che tempo fa a Londra?")
        assert result == "Londra"

    def test_worldwide_kyoto(self):
        result = extract_city_from_message("meteo a Kyoto")
        assert result == "Kyoto"

    def test_worldwide_bangkok(self):
        result = extract_city_from_message("notizie da Bangkok")
        assert result == "Bangkok"

    def test_direct_pattern(self):
        result = extract_city_from_message("previsioni Tokyo")
        assert result == "Tokyo"

    def test_skip_common_words(self):
        assert extract_city_from_message("dimmi di domani") is None

    def test_castel_del_rio(self):
        result = extract_city_from_message("meteo a Castel del Rio")
        assert result is not None
        assert "Castel" in result

    def test_imola(self):
        result = extract_city_from_message("che tempo fa a Imola?")
        assert result == "Imola"

    def test_innsbruck(self):
        result = extract_city_from_message("meteo a Innsbruck")
        assert result == "Innsbruck"

    def test_lugano(self):
        result = extract_city_from_message("notizie di Lugano")
        assert result == "Lugano"

    def test_miami(self):
        result = extract_city_from_message("che tempo fa a Miami?")
        assert result == "Miami"


# ═══════════════════════════════════════════════════════════════
# Test: _title_case_city
# ═══════════════════════════════════════════════════════════════

class TestTitleCaseCity:

    def test_simple(self):
        assert _title_case_city("roma") == "Roma"

    def test_compound_with_connector(self):
        assert _title_case_city("castel del rio") == "Castel del Rio"

    def test_compound_no_connector(self):
        assert _title_case_city("reggio calabria") == "Reggio Calabria"

    def test_san_lazzaro(self):
        result = _title_case_city("san lazzaro di savena")
        assert result == "San Lazzaro di Savena"


# ═══════════════════════════════════════════════════════════════
# Test: _disambiguate
# ═══════════════════════════════════════════════════════════════

class TestDisambiguate:

    def test_single_result(self):
        results = [{"name": "Milano", "lat": 45.46, "lon": 9.19, "country": "IT", "state": "Lombardy"}]
        loc = _disambiguate("Milano", results, "meteo a Milano")
        assert loc["name"] == "Milano"
        assert loc["country"] == "IT"

    def test_prefer_it_when_available(self):
        results = [
            {"name": "Springfield", "lat": 39.78, "lon": -89.65, "country": "US", "state": "Illinois"},
            {"name": "Springfield", "lat": 42.1, "lon": 12.5, "country": "IT", "state": "Lazio"},
        ]
        loc = _disambiguate("Springfield", results, "meteo a Springfield")
        assert loc["country"] == "IT"

    def test_same_country_picks_first(self):
        results = [
            {"name": "Springfield", "lat": 39.78, "lon": -89.65, "country": "US", "state": "Illinois"},
            {"name": "Springfield", "lat": 37.21, "lon": -93.29, "country": "US", "state": "Missouri"},
        ]
        loc = _disambiguate("Springfield", results, "weather Springfield")
        assert loc["country"] == "US"
        assert loc["lat"] == 39.78  # first result

    def test_ambiguous_many_countries(self):
        results = [
            {"name": "Springfield", "lat": 39.78, "lon": -89.65, "country": "US", "state": "Illinois"},
            {"name": "Springfield", "lat": 51.7, "lon": -1.2, "country": "GB", "state": ""},
            {"name": "Springfield", "lat": -37.0, "lon": 145.0, "country": "AU", "state": "Victoria"},
        ]
        with pytest.raises(AmbiguousLocationError) as exc_info:
            _disambiguate("Springfield", results, "meteo Springfield")
        assert len(exc_info.value.candidates) >= 3


# ═══════════════════════════════════════════════════════════════
# Test: _format_result
# ═══════════════════════════════════════════════════════════════

class TestFormatResult:

    def test_basic(self):
        r = {"name": "Roma", "lat": 41.89, "lon": 12.49, "country": "IT", "state": "Lazio"}
        loc = _format_result(r)
        assert loc["name"] == "Roma"
        assert loc["lat"] == 41.89
        assert loc["country"] == "IT"

    def test_italian_local_name(self):
        r = {"name": "Munich", "lat": 48.13, "lon": 11.58, "country": "DE",
             "state": "Bavaria", "local_names": {"it": "Monaco di Baviera"}}
        loc = _format_result(r)
        assert loc["name"] == "Monaco di Baviera"


# ═══════════════════════════════════════════════════════════════
# Test: resolve_location (async, mocked HTTP)
# ═══════════════════════════════════════════════════════════════

class TestResolveLocation:

    @patch("core.location_resolver.OPENWEATHER_API_KEY", "test-key")
    def test_resolve_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"name": "Bologna", "lat": 44.49, "lon": 11.34, "country": "IT", "state": "Emilia-Romagna"}
        ]
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        loc = asyncio.run(resolve_location("meteo a Bologna", http_client=mock_client))
        assert loc["name"] == "Bologna"
        assert loc["lat"] == 44.49
        assert loc["country"] == "IT"

    @patch("core.location_resolver.OPENWEATHER_API_KEY", "test-key")
    def test_resolve_not_found(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)

        with pytest.raises(LocationNotFoundError):
            asyncio.run(resolve_location("meteo a Zzzzville", http_client=mock_client))

    def test_resolve_no_city_in_message(self):
        with pytest.raises(LocationNotFoundError):
            asyncio.run(resolve_location("che tempo fa?"))

    @patch("core.location_resolver.OPENWEATHER_API_KEY", "")
    def test_resolve_no_api_key(self):
        with pytest.raises(LocationNotFoundError, match="non configurato"):
            asyncio.run(resolve_location("meteo a Roma"))


# ═══════════════════════════════════════════════════════════════
# Test: Weather tool integration
# ═══════════════════════════════════════════════════════════════

from core.tool_services import ToolService


class TestWeatherTool:

    @patch("core.tool_services.OPENWEATHER_API_KEY", "test-key")
    @patch("core.tool_services.resolve_location")
    def test_weather_uses_resolve_location(self, mock_resolve):
        mock_resolve.return_value = {
            "name": "Imola", "lat": 44.35, "lon": 11.71, "country": "IT", "state": "Emilia-Romagna"
        }
        ts = ToolService()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "weather": [{"description": "cielo sereno"}],
            "main": {"temp": 22, "feels_like": 21, "humidity": 55},
            "wind": {"speed": 3.5},
            "name": "Imola",
        }
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.is_closed = False
        ts._http_client = mock_client

        result = asyncio.run(ts.get_weather("che tempo fa a Imola?"))
        assert "Imola" in result
        assert "22°C" in result
        mock_resolve.assert_called_once()

    @patch("core.tool_services.OPENWEATHER_API_KEY", "test-key")
    @patch("core.tool_services.resolve_location")
    def test_weather_ambiguous_returns_message(self, mock_resolve):
        mock_resolve.side_effect = AmbiguousLocationError(
            "Ci sono più località chiamate 'Springfield'.",
            candidates=[{"label": "Springfield, Illinois, US"}]
        )
        ts = ToolService()
        result = asyncio.run(ts.get_weather("meteo a Springfield"))
        assert "Springfield" in result

    @patch("core.tool_services.OPENWEATHER_API_KEY", "test-key")
    @patch("core.tool_services.resolve_location")
    def test_weather_not_found_returns_message(self, mock_resolve):
        mock_resolve.side_effect = LocationNotFoundError("Non trovo la località 'Zzzzville'.")
        ts = ToolService()
        result = asyncio.run(ts.get_weather("meteo a Zzzzville"))
        assert "Zzzzville" in result

    @patch("core.tool_services.OPENWEATHER_API_KEY", "")
    def test_weather_no_api_key(self):
        ts = ToolService()
        result = asyncio.run(ts.get_weather("meteo a Roma"))
        assert "non riesco a recuperare i dati meteo" in result.lower() or "non ho accesso" in result.lower()


# ═══════════════════════════════════════════════════════════════
# Test: News tool — RSS parsing
# ═══════════════════════════════════════════════════════════════

class TestNewsRSSParsing:

    def test_parse_rss_titles(self):
        xml = """<?xml version="1.0" encoding="UTF-8"?>
        <rss><channel>
            <item><title>Notizia uno - Fonte A</title></item>
            <item><title>Notizia due - Fonte B</title></item>
            <item><title>Notizia tre</title></item>
        </channel></rss>"""
        ts = ToolService()
        titles = ts._parse_rss_titles(xml)
        assert len(titles) == 3
        assert titles[0] == "Notizia uno"
        assert titles[2] == "Notizia tre"

    def test_parse_rss_empty(self):
        xml = """<?xml version="1.0"?><rss><channel></channel></rss>"""
        ts = ToolService()
        titles = ts._parse_rss_titles(xml)
        assert titles == []

    def test_parse_rss_invalid_xml(self):
        ts = ToolService()
        titles = ts._parse_rss_titles("not xml at all")
        assert titles == []

    def test_parse_rss_max_items(self):
        items = "".join(f"<item><title>News {i}</title></item>" for i in range(20))
        xml = f"<rss><channel>{items}</channel></rss>"
        ts = ToolService()
        titles = ts._parse_rss_titles(xml, max_items=3)
        assert len(titles) == 3


# ═══════════════════════════════════════════════════════════════
# Test: News fallback chain
# ═══════════════════════════════════════════════════════════════

class TestNewsFallbackChain:

    def test_city_found_no_fallback(self):
        ts = ToolService()
        mock_client = AsyncMock()
        rss_resp = MagicMock()
        rss_resp.status_code = 200
        rss_resp.text = """<rss><channel>
            <item><title>Imola news 1 - Fonte</title></item>
            <item><title>Imola news 2 - Fonte</title></item>
        </channel></rss>"""
        mock_client.get = AsyncMock(return_value=rss_resp)

        result = asyncio.run(ts._news_with_fallback_chain(mock_client, "Imola", "Emilia-Romagna", "IT"))
        assert "Imola" in result
        assert "news 1" in result

    def test_city_empty_falls_to_region(self):
        ts = ToolService()
        mock_client = AsyncMock()

        call_count = 0
        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.status_code = 200
            if call_count == 1:
                resp.text = "<rss><channel></channel></rss>"
            else:
                resp.text = """<rss><channel>
                    <item><title>Regional news - Fonte</title></item>
                </channel></rss>"""
            return resp

        mock_client.get = AsyncMock(side_effect=mock_get)

        result = asyncio.run(ts._news_with_fallback_chain(
            mock_client, "Castel del Rio", "Emilia-Romagna", "IT"))
        assert "Emilia-Romagna" in result or "Regional" in result

    def test_all_empty_returns_explicit_message(self):
        ts = ToolService()
        mock_client = AsyncMock()
        empty_resp = MagicMock()
        empty_resp.status_code = 200
        empty_resp.text = "<rss><channel></channel></rss>"
        mock_client.get = AsyncMock(return_value=empty_resp)

        with patch("core.tool_services.GNEWS_API_KEY", ""):
            result = asyncio.run(ts._news_with_fallback_chain(
                mock_client, "Castel del Rio", "Emilia-Romagna", "IT"))
        assert "Non trovo notizie" in result
        assert "Castel del Rio" in result


# ═══════════════════════════════════════════════════════════════
# Test: _extract_city via ToolService (backward compat)
# ═══════════════════════════════════════════════════════════════

class TestToolServiceExtractCity:

    def test_delegates_to_location_resolver(self):
        ts = ToolService()
        assert ts._extract_city("meteo a Roma") == "Roma"
        assert ts._extract_city("che tempo fa?") is None
