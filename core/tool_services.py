"""TOOL SERVICES - Genesi Core v3
Servizi tool per weather, news, time, date.
100% API-driven. Zero mock. Zero dati inventati.
Supporto mondiale. Italia ultra-dettagliata.
"""

import os
import re
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional
from xml.etree import ElementTree

import httpx

from core.log import log
from core.location_resolver import (
    resolve_location,
    extract_city_from_message,
    LocationNotFoundError,
    AmbiguousLocationError,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# CONFIGURAZIONE
# ═══════════════════════════════════════════════════════════════

TIMEZONE = ZoneInfo("Europe/Rome")

# Nomi italiani — nessuna dipendenza da locale OS
GIORNI_IT = ["lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica"]
MESI_IT = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
           "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]

# Descrizioni meteo OpenWeather → italiano
WEATHER_DESC_IT = {
    "clear sky": "cielo sereno",
    "few clouds": "poche nuvole",
    "scattered clouds": "nuvole sparse",
    "broken clouds": "nuvoloso",
    "overcast clouds": "coperto",
    "shower rain": "pioggia a tratti",
    "rain": "pioggia",
    "light rain": "pioggia leggera",
    "moderate rain": "pioggia moderata",
    "heavy intensity rain": "pioggia intensa",
    "thunderstorm": "temporale",
    "snow": "neve",
    "light snow": "neve leggera",
    "mist": "foschia",
    "fog": "nebbia",
    "haze": "foschia",
    "drizzle": "pioggerella",
}


# Parole chiave che indicano previsione futura
FORECAST_KEYWORDS = [
    "domani", "dopodomani", "prossimi giorni", "settimana",
    "weekend", "sabato", "domenica", "lunedì", "martedì",
    "mercoledì", "giovedì", "venerdì", "previsioni",
    "prossima settimana", "fra poco", "stasera", "stanotte",
    "tra qualche giorno",
]

# Categorie notizie per ricerca organizzata
NEWS_SECTIONS = {
    "cronaca": ["cronaca", "incidente", "emergenza", "arresto", "omicidio", "rapina"],
    "politica": ["politica", "governo", "parlamento", "elezioni", "ministro", "legge"],
    "sport": ["sport", "calcio", "serie a", "champions", "tennis", "formula 1", "basket", "pallavolo"],
    "finanza": ["finanza", "economia", "borsa", "mercati", "pil", "inflazione", "banca"],
}

# Categorie notizie per NewsAPI (legacy, kept for _extract_topic compat)
NEWS_CATEGORIES = {
    "tecnologia": "technology",
    "sport": "sports",
    "politica": "general",
    "economia": "business",
    "scienza": "science",
    "salute": "health",
    "intrattenimento": "entertainment",
    "cronaca": "general",
    "finanza": "business",
}

# API Keys
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
GNEWS_API_KEY = os.environ.get("GNEWS_API_KEY", os.environ.get("NEWSAPI_KEY", ""))

if not OPENWEATHER_API_KEY:
    logger.warning("OPENWEATHER_API_KEY non configurata — il servizio meteo non funzionerà")
if not GNEWS_API_KEY:
    logger.warning("GNEWS_API_KEY non configurata -- il servizio notizie non funzionera'")

# Country code → display name (for news fallback chain)
_COUNTRY_NAMES = {
    "IT": "Italia", "US": "Stati Uniti", "GB": "Regno Unito", "FR": "Francia",
    "DE": "Germania", "ES": "Spagna", "CH": "Svizzera", "AT": "Austria",
    "JP": "Giappone", "CN": "Cina", "BR": "Brasile", "TH": "Thailandia",
    "IN": "India", "AU": "Australia", "CA": "Canada", "MX": "Messico",
    "AR": "Argentina", "PT": "Portogallo", "NL": "Paesi Bassi", "BE": "Belgio",
    "GR": "Grecia", "TR": "Turchia", "RU": "Russia", "PL": "Polonia",
    "SE": "Svezia", "NO": "Norvegia", "DK": "Danimarca", "FI": "Finlandia",
    "KR": "Corea del Sud", "EG": "Egitto", "ZA": "Sudafrica",
}


# ═══════════════════════════════════════════════════════════════
# TOOL SERVICE
# ═══════════════════════════════════════════════════════════════

class ToolService:
    """
    Tool Service - Weather, News, Time, Date.
    100% API-driven. Zero mock. Zero dati inventati.
    """

    def __init__(self):
        self._http_client: Optional[httpx.AsyncClient] = None
        log("TOOL_SERVICE_ACTIVE")

    async def _get_client(self) -> httpx.AsyncClient:
        """Lazy-init httpx async client."""
        if self._http_client is None or self._http_client.is_closed:
            self._http_client = httpx.AsyncClient(timeout=10.0)
        return self._http_client

    # ───────────────────────────────────────────────────────────
    # WEATHER — OpenWeather API reale
    # ───────────────────────────────────────────────────────────

    def _is_forecast_request(self, message: str) -> bool:
        """Detect if user is asking for forecast (future weather)."""
        msg_lower = message.lower()
        return any(kw in msg_lower for kw in FORECAST_KEYWORDS)

    async def get_weather(self, message: str) -> str:
        """
        Meteo reale via OpenWeather API — supporto mondiale.
        Usa location_resolver per geocoding intelligente.
        Se API fallisce -> messaggio di errore, zero dati inventati.
        """
        try:
            log("TOOL_WEATHER_REQUEST", message=message[:50])

            if not OPENWEATHER_API_KEY:
                logger.error("TOOL_WEATHER_MISSING_KEY error=OPENWEATHER_API_KEY non configurata")
                return "Servizio meteo non configurato."

            client = await self._get_client()

            try:
                geo = await resolve_location(message, http_client=client)
            except AmbiguousLocationError as e:
                return str(e)
            except LocationNotFoundError as e:
                return str(e)

            display_name = geo["name"]
            log("WEATHER_COORD_CALL", city=display_name, lat=geo["lat"], lon=geo["lon"], country=geo["country"])

            is_forecast = self._is_forecast_request(message)

            if is_forecast:
                return await self._get_forecast(geo, message, display_name)
            else:
                return await self._get_current_weather_coords(geo, display_name)

        except httpx.TimeoutException:
            logger.error("TOOL_WEATHER_HTTP_ERROR error=timeout")
            log("TOOL_WEATHER_HTTP_ERROR", error="timeout")
            return "Servizio meteo temporaneamente non disponibile."
        except Exception as e:
            logger.error("TOOL_WEATHER_HTTP_ERROR error=%s", str(e))
            log("TOOL_WEATHER_HTTP_ERROR", error=str(e))
            return "Servizio meteo temporaneamente non disponibile."

    async def _get_current_weather_coords(self, geo: dict, display_name: str) -> str:
        """Current weather via /data/2.5/weather using lat/lon coordinates."""
        client = await self._get_client()
        url = "https://api.openweathermap.org/data/2.5/weather"
        params = {"lat": geo["lat"], "lon": geo["lon"],
                  "appid": OPENWEATHER_API_KEY, "units": "metric", "lang": "it"}

        logger.info("TOOL_WEATHER_HTTP_CALL url=%s city=%s lat=%s lon=%s", url, display_name, geo["lat"], geo["lon"])
        log("TOOL_WEATHER_HTTP_CALL", url=url, city=display_name)

        resp = await client.get(url, params=params)

        logger.info("TOOL_WEATHER_HTTP_STATUS status=%d city=%s", resp.status_code, display_name)
        log("TOOL_WEATHER_HTTP_STATUS", status=resp.status_code, city=display_name)

        if resp.status_code != 200:
            logger.error("TOOL_WEATHER_HTTP_ERROR status=%d body=%s", resp.status_code, resp.text[:200])
            log("TOOL_WEATHER_HTTP_ERROR", status=resp.status_code, error=resp.text[:200])
            return f"Non riesco a ottenere il meteo per {display_name}."

        data = resp.json()
        city_used = data.get("name", display_name)
        log("WEATHER_RESPONSE_CITY_USED", requested=display_name, api_city=city_used)
        return self._format_weather_it(data, display_name)

    async def _get_forecast(self, geo: dict, message: str, display_name: str) -> str:
        """5-day forecast via /data/2.5/forecast. Returns organized daily summary."""
        client = await self._get_client()
        url = "https://api.openweathermap.org/data/2.5/forecast"
        params = {"lat": geo["lat"], "lon": geo["lon"],
                  "appid": OPENWEATHER_API_KEY, "units": "metric", "lang": "it"}

        logger.info("TOOL_FORECAST_HTTP_CALL city=%s", display_name)
        log("TOOL_FORECAST_HTTP_CALL", city=display_name)

        resp = await client.get(url, params=params)

        if resp.status_code != 200:
            logger.error("TOOL_FORECAST_HTTP_ERROR status=%d", resp.status_code)
            return "Servizio previsioni temporaneamente non disponibile."

        data = resp.json()
        return self._format_forecast_it(data, display_name, message)

    def _format_weather_it(self, data: dict, city: str) -> str:
        """Formatta risposta OpenWeather in italiano naturale."""
        try:
            desc_it = data.get("weather", [{}])[0].get("description", "")
            if not desc_it:
                desc_en = data.get("weather", [{}])[0].get("description", "")
                desc_it = WEATHER_DESC_IT.get(desc_en, desc_en)

            temp = round(data.get("main", {}).get("temp", 0))
            feels_like = round(data.get("main", {}).get("feels_like", 0))
            humidity = data.get("main", {}).get("humidity", 0)
            wind_ms = data.get("wind", {}).get("speed", 0)
            wind_kmh = round(wind_ms * 3.6)

            parts = [f"A {city}: {desc_it}, {temp}°C"]
            if abs(feels_like - temp) >= 2:
                parts.append(f"percepiti {feels_like}°C")
            parts.append(f"umidit\u00e0 {humidity}%")
            parts.append(f"vento {wind_kmh} km/h")

            weather_info = ", ".join(parts) + "."

            log("TOOL_WEATHER_RESPONSE", city=city, temp=temp, desc=desc_it)
            return weather_info

        except Exception as e:
            logger.error("TOOL_WEATHER_FORMAT_ERROR error=%s", str(e))
            return "Servizio meteo temporaneamente non disponibile."

    def _format_forecast_it(self, data: dict, city: str, message: str) -> str:
        """Format 5-day forecast into organized daily summaries."""
        try:
            forecasts = data.get("list", [])
            if not forecasts:
                return f"Nessuna previsione disponibile per {city}."

            # Group by day
            days = {}
            for entry in forecasts:
                dt_txt = entry.get("dt_txt", "")
                day = dt_txt.split(" ")[0] if dt_txt else ""
                if day not in days:
                    days[day] = []
                days[day].append(entry)

            msg_lower = message.lower()
            # Determine how many days to show
            if "domani" in msg_lower:
                day_keys = list(days.keys())[:2]  # today + tomorrow
            elif "dopodomani" in msg_lower:
                day_keys = list(days.keys())[:3]
            else:
                day_keys = list(days.keys())[:5]  # max 5 days

            lines = [f"Previsioni per {city}:"]
            for day_key in day_keys:
                entries = days.get(day_key, [])
                if not entries:
                    continue

                # Parse date
                try:
                    dt = datetime.strptime(day_key, "%Y-%m-%d")
                    weekday = GIORNI_IT[dt.weekday()]
                    day_label = f"{weekday} {dt.day} {MESI_IT[dt.month]}"
                except (ValueError, IndexError):
                    day_label = day_key

                # Aggregate: min/max temp, most common description
                temps = [e.get("main", {}).get("temp", 0) for e in entries]
                descs = [e.get("weather", [{}])[0].get("description", "") for e in entries]
                # Pick midday description if available, else most common
                midday_desc = ""
                for e in entries:
                    hour = e.get("dt_txt", "").split(" ")[1][:2] if e.get("dt_txt") else ""
                    if hour in ("12", "15"):
                        midday_desc = e.get("weather", [{}])[0].get("description", "")
                        break
                if not midday_desc and descs:
                    midday_desc = max(set(descs), key=descs.count)

                t_min = round(min(temps))
                t_max = round(max(temps))
                lines.append(f"  {day_label}: {midday_desc}, {t_min}°C / {t_max}°C")

            result = "\n".join(lines)
            log("TOOL_FORECAST_RESPONSE", city=city, days=len(day_keys))
            return result

        except Exception as e:
            logger.error("TOOL_FORECAST_FORMAT_ERROR error=%s", str(e))
            return "Servizio previsioni temporaneamente non disponibile."

    # ───────────────────────────────────────────────────────────
    # NEWS — Google News RSS + GNews fallback
    # ───────────────────────────────────────────────────────────

    async def get_news(self, message: str) -> str:
        """
        Notizie reali — supporto mondiale.
        Pipeline: location_resolver → Google News RSS (city → region → country).
        Fallback su GNews API se RSS vuoto.
        Se nessun risultato → messaggio esplicito, zero dati inventati.
        """
        try:
            log("TOOL_NEWS_REQUEST", message=message[:50])

            client = await self._get_client()
            msg_lower = message.lower()

            # Detect specific category
            requested_section = None
            for section, keywords in NEWS_SECTIONS.items():
                if any(kw in msg_lower for kw in keywords):
                    requested_section = section
                    break

            # Try to resolve location
            city_name = None
            country = "IT"
            state = ""
            try:
                geo = await resolve_location(message, http_client=client)
                city_name = geo["name"]
                country = geo.get("country", "IT")
                state = geo.get("state", "")
            except (LocationNotFoundError, AmbiguousLocationError):
                # No location in message — use general topic search
                pass

            # Determine search query
            if city_name:
                log("NEWS_QUERY_CITY", city=city_name, country=country, state=state)
                return await self._news_with_fallback_chain(
                    client, city_name, state, country, requested_section)
            elif requested_section:
                return await self._news_rss_search(client, requested_section, "IT", "Italia")
            else:
                # General news
                topic = self._extract_topic(message)
                query = topic if topic else "Italia"
                return await self._news_rss_search(client, query, "IT", "Italia")

        except httpx.TimeoutException:
            logger.error("TOOL_NEWS_HTTP_ERROR error=timeout")
            log("TOOL_NEWS_HTTP_ERROR", error="timeout")
            return "Servizio notizie temporaneamente non disponibile."
        except Exception as e:
            logger.error("TOOL_NEWS_HTTP_ERROR error=%s", str(e))
            log("TOOL_NEWS_HTTP_ERROR", error=str(e))
            return "Servizio notizie temporaneamente non disponibile."

    async def _news_with_fallback_chain(self, client: httpx.AsyncClient,
                                         city: str, state: str, country: str,
                                         section: Optional[str] = None) -> str:
        """
        News fallback chain: city → state/region → country.
        Logs every fallback step.
        """
        query = f"{city} {section}" if section else city
        scope = city

        # 1. Try city-level
        result = await self._news_rss_search(client, query, country, scope)
        count = result.count("\n") if result and "ultime notizie" in result.lower() else 0
        log("NEWS_RESULTS_COUNT", scope=scope, count=count)

        if count > 0:
            log("NEWS_FINAL_SCOPE", scope=scope, level="city")
            return result

        # 2. Fallback to state/region (if available)
        if state:
            log("NEWS_FALLBACK_TRIGGERED", from_scope=scope, to_scope=state, level="region")
            scope = state
            query = f"{state} {section}" if section else state
            result = await self._news_rss_search(client, query, country, scope)
            count = result.count("\n") if result and "ultime notizie" in result.lower() else 0
            log("NEWS_RESULTS_COUNT", scope=scope, count=count)

            if count > 0:
                log("NEWS_FINAL_SCOPE", scope=scope, level="region")
                return result

        # 3. Fallback to country
        country_name = _COUNTRY_NAMES.get(country, country)
        if country_name != city:
            log("NEWS_FALLBACK_TRIGGERED", from_scope=scope, to_scope=country_name, level="country")
            scope = country_name
            query = f"{country_name} {section}" if section else country_name
            result = await self._news_rss_search(client, query, country, scope)
            count = result.count("\n") if result and "ultime notizie" in result.lower() else 0
            log("NEWS_RESULTS_COUNT", scope=scope, count=count)

            if count > 0:
                log("NEWS_FINAL_SCOPE", scope=scope, level="country")
                return result

        # 4. Nothing found at any level
        log("NEWS_FINAL_SCOPE", scope=city, level="none")
        return f"Non trovo notizie locali recenti per {city}."

    async def _news_rss_search(self, client: httpx.AsyncClient,
                                query: str, country: str, display_scope: str) -> str:
        """
        Search Google News RSS for a query.
        URL: https://news.google.com/rss/search?q={query}&hl=it&gl={country}&ceid={country}:it
        Falls back to GNews API if RSS fails.
        """
        try:
            gl = country if country else "IT"
            rss_url = "https://news.google.com/rss/search"
            params = {"q": query, "hl": "it", "gl": gl, "ceid": f"{gl}:it"}

            logger.info("TOOL_NEWS_RSS_CALL query=%s gl=%s", query, gl)

            resp = await client.get(rss_url, params=params, follow_redirects=True)

            if resp.status_code == 200:
                titles = self._parse_rss_titles(resp.text, max_items=5)
                if titles:
                    lines = [f"Ecco le ultime notizie su {display_scope}:"]
                    for i, title in enumerate(titles, 1):
                        lines.append(f"{i}. {title}")
                    log("TOOL_NEWS_RESPONSE", context=display_scope, count=len(titles), source="google_rss")
                    return "\n".join(lines)

            # RSS empty or failed — try GNews as backup
            logger.info("TOOL_NEWS_RSS_EMPTY query=%s, trying GNews", query)

        except Exception as e:
            logger.warning("TOOL_NEWS_RSS_ERROR query=%s error=%s", query, str(e))

        # GNews fallback
        if GNEWS_API_KEY:
            return await self._gnews_search(client, query, display_scope)

        return ""

    def _parse_rss_titles(self, xml_text: str, max_items: int = 5) -> list:
        """Parse Google News RSS XML and extract article titles."""
        try:
            root = ElementTree.fromstring(xml_text)
            items = root.findall(".//item")
            titles = []
            for item in items[:max_items]:
                title_el = item.find("title")
                if title_el is not None and title_el.text:
                    # Google News titles often end with " - Source Name"
                    title = title_el.text.strip()
                    # Remove source suffix for cleaner output
                    if " - " in title:
                        title = title.rsplit(" - ", 1)[0].strip()
                    if title:
                        titles.append(title)
            return titles
        except Exception as e:
            logger.warning("TOOL_NEWS_RSS_PARSE_ERROR error=%s", str(e))
            return []

    async def _gnews_search(self, client: httpx.AsyncClient,
                             query: str, display_scope: str) -> str:
        """GNews API search as fallback for RSS."""
        url = "https://gnews.io/api/v4/search"
        params = {
            "apikey": GNEWS_API_KEY,
            "q": query,
            "lang": "it",
            "max": 5,
        }

        logger.info("TOOL_GNEWS_HTTP_CALL query=%s", query)
        log("TOOL_GNEWS_HTTP_CALL", query=query)

        resp = await client.get(url, params=params)

        logger.info("TOOL_GNEWS_HTTP_STATUS status=%d query=%s", resp.status_code, query)

        if resp.status_code != 200:
            return ""

        data = resp.json()
        articles = data.get("articles", [])
        if not articles:
            return ""

        lines = [f"Ecco le ultime notizie su {display_scope}:"]
        for i, art in enumerate(articles[:5], 1):
            title = art.get("title", "").strip()
            if title:
                lines.append(f"{i}. {title}")

        log("TOOL_NEWS_RESPONSE", context=display_scope, count=len(articles), source="gnews")
        return "\n".join(lines)

    # ───────────────────────────────────────────────────────────
    # TIME — Europe/Rome timezone
    # ───────────────────────────────────────────────────────────

    async def get_time(self) -> str:
        """
        Ora corrente in italiano, timezone Europe/Rome.
        Formato: "Sono le 20:15."
        """
        try:
            log("TOOL_TIME_REQUEST")

            now = datetime.now(tz=TIMEZONE)
            ora = now.strftime("%H:%M")
            time_info = f"Sono le {ora}."

            log("TOOL_TIME_RESPONSE", time=ora, timezone="Europe/Rome")
            logger.info("TOOL_TIME_RESPONSE time=%s timezone=Europe/Rome", ora)
            return time_info

        except Exception as e:
            log("TOOL_TIME_ERROR", error=str(e))
            return "Mi dispiace, non riesco a ottenere l'ora."

    # ───────────────────────────────────────────────────────────
    # DATE — Europe/Rome timezone, italiano
    # ───────────────────────────────────────────────────────────

    async def get_date(self) -> str:
        """
        Data corrente in italiano, timezone Europe/Rome.
        Formato: "Oggi è giovedì 12 febbraio 2026."
        """
        try:
            log("TOOL_DATE_REQUEST")

            now = datetime.now(tz=TIMEZONE)
            weekday = GIORNI_IT[now.weekday()]
            giorno = now.day
            mese = MESI_IT[now.month]
            anno = now.year

            date_info = f"Oggi è {weekday} {giorno} {mese} {anno}."

            log("TOOL_DATE_RESPONSE", weekday_it=weekday, date=f"{giorno} {mese} {anno}", timezone="Europe/Rome")
            logger.info("TOOL_DATE_RESPONSE date=%d %s %d weekday_it=%s timezone=Europe/Rome",
                        giorno, mese, anno, weekday)
            return date_info

        except Exception as e:
            log("TOOL_DATE_ERROR", error=str(e))
            return "Mi dispiace, non riesco a ottenere la data."

    # ───────────────────────────────────────────────────────────
    # EXTRACTORS
    # ───────────────────────────────────────────────────────────

    def _extract_city(self, message: str) -> Optional[str]:
        """Estrai nome citta' dal messaggio. Delega a location_resolver."""
        return extract_city_from_message(message)

    def _extract_topic(self, message: str) -> Optional[str]:
        """Estrai argomento dal messaggio."""
        message_lower = message.lower()
        for topic in NEWS_CATEGORIES:
            if topic in message_lower:
                return topic
        return None


# Istanza globale
tool_service = ToolService()
