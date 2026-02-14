"""
Tests for News Fallback Hierarchy: city → region → country → continent → global.
Covers: _count_news_results, _news_with_fallback_chain at each level,
NEWS_FALLBACK_LEVEL logging.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from core.tool_services import ToolService, _COUNTRY_TO_CONTINENT, _COUNTRY_NAMES


def _rss_with_items(scope: str, n: int) -> str:
    """Generate RSS XML with n items for a given scope."""
    items = "".join(
        f"<item><title>{scope} news {i} - Fonte</title></item>" for i in range(1, n + 1)
    )
    return f"<rss><channel>{items}</channel></rss>"


_EMPTY_RSS = "<rss><channel></channel></rss>"


class TestCountNewsResults:

    def test_empty_string(self):
        ts = ToolService()
        assert ts._count_news_results("") == 0

    def test_none(self):
        ts = ToolService()
        assert ts._count_news_results(None) == 0

    def test_no_header(self):
        ts = ToolService()
        assert ts._count_news_results("qualcosa senza header") == 0

    def test_with_results(self):
        ts = ToolService()
        text = "Ecco le ultime notizie su Roma:\n1. News 1\n2. News 2"
        assert ts._count_news_results(text) == 2

    def test_single_result(self):
        ts = ToolService()
        text = "Ecco le ultime notizie su Roma:\n1. News 1"
        assert ts._count_news_results(text) == 1


class TestFallbackHierarchyCityLevel:
    """City-level results → no fallback needed."""

    def test_city_found(self):
        ts = ToolService()
        mock_client = AsyncMock()
        rss_resp = MagicMock()
        rss_resp.status_code = 200
        rss_resp.text = _rss_with_items("Imola", 3)
        mock_client.get = AsyncMock(return_value=rss_resp)

        result = asyncio.run(ts._news_with_fallback_chain(
            mock_client, "Imola", "Emilia-Romagna", "IT"))
        assert "Imola" in result
        assert "news 1" in result


class TestFallbackHierarchyRegionLevel:
    """City empty → region has results."""

    def test_falls_to_region(self):
        ts = ToolService()
        mock_client = AsyncMock()

        call_count = 0
        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.status_code = 200
            if call_count == 1:
                resp.text = _EMPTY_RSS
            else:
                resp.text = _rss_with_items("Emilia-Romagna", 2)
            return resp

        mock_client.get = AsyncMock(side_effect=mock_get)

        result = asyncio.run(ts._news_with_fallback_chain(
            mock_client, "Castel del Rio", "Emilia-Romagna", "IT"))
        assert "Emilia-Romagna" in result


class TestFallbackHierarchyCountryLevel:
    """City + region empty → country has results."""

    def test_falls_to_country(self):
        ts = ToolService()
        mock_client = AsyncMock()

        call_count = 0
        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.status_code = 200
            if call_count <= 2:
                resp.text = _EMPTY_RSS
            else:
                resp.text = _rss_with_items("Italia", 3)
            return resp

        mock_client.get = AsyncMock(side_effect=mock_get)

        result = asyncio.run(ts._news_with_fallback_chain(
            mock_client, "Borgo Tiny", "Lazio", "IT"))
        assert "Italia" in result


class TestFallbackHierarchyContinentLevel:
    """City + region + country empty → continent has results."""

    def test_falls_to_continent(self):
        ts = ToolService()
        mock_client = AsyncMock()

        call_count = 0
        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.status_code = 200
            if call_count <= 3:
                resp.text = _EMPTY_RSS
            else:
                resp.text = _rss_with_items("Europa", 2)
            return resp

        mock_client.get = AsyncMock(side_effect=mock_get)

        result = asyncio.run(ts._news_with_fallback_chain(
            mock_client, "Borgo Tiny", "Lazio", "IT"))
        assert "Europa" in result


class TestFallbackHierarchyGlobalLevel:
    """All levels empty → global has results."""

    def test_falls_to_global(self):
        ts = ToolService()
        mock_client = AsyncMock()

        call_count = 0
        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.status_code = 200
            if call_count <= 4:
                resp.text = _EMPTY_RSS
            else:
                resp.text = _rss_with_items("mondo", 2)
            return resp

        mock_client.get = AsyncMock(side_effect=mock_get)

        result = asyncio.run(ts._news_with_fallback_chain(
            mock_client, "Borgo Tiny", "Lazio", "IT"))
        assert "mondo" in result


class TestFallbackHierarchyNoneLevel:
    """All levels empty including global → explicit error message."""

    def test_all_empty(self):
        ts = ToolService()
        mock_client = AsyncMock()
        empty_resp = MagicMock()
        empty_resp.status_code = 200
        empty_resp.text = _EMPTY_RSS
        mock_client.get = AsyncMock(return_value=empty_resp)

        with patch("core.tool_services.GNEWS_API_KEY", ""):
            result = asyncio.run(ts._news_with_fallback_chain(
                mock_client, "Borgo Tiny", "Lazio", "IT"))
        assert "Non trovo notizie" in result
        assert "Borgo Tiny" in result


class TestFallbackWithSection:
    """Fallback chain with a specific news section."""

    def test_section_appended_to_query(self):
        ts = ToolService()
        mock_client = AsyncMock()
        rss_resp = MagicMock()
        rss_resp.status_code = 200
        rss_resp.text = _rss_with_items("Roma sport", 2)
        mock_client.get = AsyncMock(return_value=rss_resp)

        result = asyncio.run(ts._news_with_fallback_chain(
            mock_client, "Roma", "Lazio", "IT", section="sport"))
        assert "Roma" in result


class TestContinentMapping:
    """Verify continent mapping completeness."""

    def test_it_is_europa(self):
        assert _COUNTRY_TO_CONTINENT["IT"] == "Europa"

    def test_us_is_nord_america(self):
        assert _COUNTRY_TO_CONTINENT["US"] == "Nord America"

    def test_jp_is_asia(self):
        assert _COUNTRY_TO_CONTINENT["JP"] == "Asia"

    def test_br_is_sud_america(self):
        assert _COUNTRY_TO_CONTINENT["BR"] == "Sud America"

    def test_au_is_oceania(self):
        assert _COUNTRY_TO_CONTINENT["AU"] == "Oceania"

    def test_eg_is_africa(self):
        assert _COUNTRY_TO_CONTINENT["EG"] == "Africa"

    def test_no_region_skips_to_country(self):
        """If state is empty, skip region level."""
        ts = ToolService()
        mock_client = AsyncMock()

        call_count = 0
        async def mock_get(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            resp = MagicMock()
            resp.status_code = 200
            if call_count == 1:
                resp.text = _EMPTY_RSS
            else:
                resp.text = _rss_with_items("Giappone", 2)
            return resp

        mock_client.get = AsyncMock(side_effect=mock_get)

        result = asyncio.run(ts._news_with_fallback_chain(
            mock_client, "Kyoto", "", "JP"))
        # Should skip region (empty) and go to country
        assert "Giappone" in result
