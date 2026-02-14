"""TOOL SERVICES - Genesi Core v2
Servizi tool per weather, news, time, date.
100% API-driven. Zero mock. Zero dati inventati.
"""

import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from typing import Optional

import httpx

from core.log import log

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

# Città note per estrazione rapida (fallback se geocoding non serve)
CITIES_IT = [
    "roma", "milano", "napoli", "torino", "firenze", "bologna",
    "genova", "palermo", "catania", "bari", "venezia", "verona",
    "messina", "padova", "trieste", "brescia", "parma", "modena",
    "reggio calabria", "reggio emilia", "perugia", "cagliari",
    "livorno", "ravenna", "ferrara", "rimini", "salerno",
    "sassari", "latina", "bergamo", "siracusa", "monza",
    "pescara", "trento", "bolzano", "ancona", "lecce", "udine",
    "taranto", "pisa", "como", "arezzo", "prato", "la spezia",
    "vicenza", "terni", "novara", "aosta", "potenza", "campobasso",
    "l'aquila", "catanzaro", "crotone", "cosenza", "trapani",
    "agrigento", "ragusa", "enna", "caltanissetta", "matera",
    "avellino", "benevento", "caserta", "frosinone", "rieti",
    "viterbo", "asti", "alessandria", "cuneo", "biella",
]

# Pattern per estrarre città dal messaggio (qualsiasi città del mondo)
CITY_EXTRACT_PATTERNS = [
    r"(?:a|di|da|in|su|per|ad)\s+([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)*)",
    r"(?:meteo|tempo|previsioni)\s+(?:a|di|per|in)?\s*([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)*)",
]

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

    async def _geocode_city(self, city: str) -> Optional[dict]:
        """Geocode any city worldwide via OpenWeather Geocoding API. Returns {lat, lon, name, country}."""
        try:
            client = await self._get_client()
            url = "https://api.openweathermap.org/geo/1.0/direct"
            params = {"q": city, "limit": 1, "appid": OPENWEATHER_API_KEY}
            resp = await client.get(url, params=params)
            if resp.status_code == 200:
                results = resp.json()
                if results:
                    r = results[0]
                    return {"lat": r["lat"], "lon": r["lon"],
                            "name": r.get("local_names", {}).get("it", r.get("name", city)),
                            "country": r.get("country", "")}
            logger.warning("TOOL_GEOCODE_NO_RESULT city=%s status=%d", city, resp.status_code)
        except Exception as e:
            logger.error("TOOL_GEOCODE_ERROR city=%s error=%s", city, str(e))
        return None

    async def get_weather(self, message: str) -> str:
        """
        Meteo reale via OpenWeather API — supporta qualsiasi citta' del mondo.
        Se l'utente chiede previsioni future, usa endpoint forecast.
        Se API fallisce -> messaggio di errore, zero dati inventati.
        """
        try:
            log("TOOL_WEATHER_REQUEST", message=message[:50])
            city = self._extract_city(message) or "Roma"

            if not OPENWEATHER_API_KEY:
                logger.error("TOOL_WEATHER_MISSING_KEY error=OPENWEATHER_API_KEY non configurata")
                return "Servizio meteo non configurato."

            # Geocode city for worldwide support
            geo = await self._geocode_city(city)
            if not geo:
                # Fallback: try direct query without country restriction
                geo = {"lat": None, "lon": None, "name": city, "country": ""}

            display_name = geo["name"]
            is_forecast = self._is_forecast_request(message)

            if is_forecast and geo["lat"] is not None:
                return await self._get_forecast(geo, message, display_name)
            else:
                return await self._get_current_weather(city, geo, display_name)

        except httpx.TimeoutException:
            logger.error("TOOL_WEATHER_HTTP_ERROR error=timeout")
            log("TOOL_WEATHER_HTTP_ERROR", error="timeout")
            return "Servizio meteo temporaneamente non disponibile."
        except Exception as e:
            logger.error("TOOL_WEATHER_HTTP_ERROR error=%s", str(e))
            log("TOOL_WEATHER_HTTP_ERROR", error=str(e))
            return "Servizio meteo temporaneamente non disponibile."

    async def _get_current_weather(self, city: str, geo: dict, display_name: str) -> str:
        """Current weather via /data/2.5/weather. Worldwide support."""
        client = await self._get_client()

        if geo.get("lat") is not None:
            url = "https://api.openweathermap.org/data/2.5/weather"
            params = {"lat": geo["lat"], "lon": geo["lon"],
                      "appid": OPENWEATHER_API_KEY, "units": "metric", "lang": "it"}
        else:
            url = "https://api.openweathermap.org/data/2.5/weather"
            params = {"q": city, "appid": OPENWEATHER_API_KEY,
                      "units": "metric", "lang": "it"}

        logger.info("TOOL_WEATHER_HTTP_CALL url=%s city=%s", url, display_name)
        log("TOOL_WEATHER_HTTP_CALL", url=url, city=display_name)

        resp = await client.get(url, params=params)

        logger.info("TOOL_WEATHER_HTTP_STATUS status=%d city=%s", resp.status_code, display_name)
        log("TOOL_WEATHER_HTTP_STATUS", status=resp.status_code, city=display_name)

        if resp.status_code != 200:
            logger.error("TOOL_WEATHER_HTTP_ERROR status=%d body=%s", resp.status_code, resp.text[:200])
            log("TOOL_WEATHER_HTTP_ERROR", status=resp.status_code, error=resp.text[:200])
            return "Servizio meteo temporaneamente non disponibile."

        data = resp.json()
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
    # NEWS — NewsAPI reale
    # ───────────────────────────────────────────────────────────

    async def get_news(self, message: str) -> str:
        """
        Notizie reali via GNews API (gnews.io).
        Supporta notizie locali per qualsiasi citta'/paese.
        Organizza per categoria: cronaca, politica, sport, finanza.
        Se API fallisce -> messaggio di errore, zero dati inventati.
        """
        try:
            log("TOOL_NEWS_REQUEST", message=message[:50])

            if not GNEWS_API_KEY:
                logger.error("TOOL_NEWS_MISSING_KEY error=GNEWS_API_KEY non configurata")
                return "Servizio notizie non configurato."

            topic = self._extract_topic(message)
            city = self._extract_city(message)
            msg_lower = message.lower()

            # Check if user asks for a specific category
            requested_section = None
            for section, keywords in NEWS_SECTIONS.items():
                if any(kw in msg_lower for kw in keywords):
                    requested_section = section
                    break

            if requested_section:
                # Single category search
                query = f"{city} {requested_section}" if city else requested_section
                result = await self._gnews_search(query)
                return result
            elif city:
                # Local news for specific city/town — multi-category
                return await self._get_categorized_news(city)
            elif topic:
                return await self._gnews_search(topic)
            else:
                # General Italian news — multi-category
                return await self._get_categorized_news("Italia")

        except httpx.TimeoutException:
            logger.error("TOOL_GNEWS_HTTP_ERROR error=timeout")
            log("TOOL_GNEWS_HTTP_ERROR", error="timeout")
            return "Servizio notizie temporaneamente non disponibile."
        except Exception as e:
            logger.error("TOOL_GNEWS_HTTP_ERROR error=%s", str(e))
            log("TOOL_GNEWS_HTTP_ERROR", error=str(e))
            return "Servizio notizie temporaneamente non disponibile."

    async def _get_categorized_news(self, context: str) -> str:
        """Fetch news organized by category (cronaca, politica, sport, finanza)."""
        sections_output = []
        categories_to_fetch = ["cronaca", "politica", "sport", "finanza"]

        for category in categories_to_fetch:
            query = f"{context} {category}"
            try:
                raw = await self._gnews_search_raw(query, max_results=3)
                if raw:
                    section_title = category.upper()
                    lines = [f"\n{section_title}:"]
                    for i, art in enumerate(raw[:3], 1):
                        title = art.get("title", "").strip()
                        if title:
                            lines.append(f"  {i}. {title}")
                    if len(lines) > 1:
                        sections_output.append("\n".join(lines))
            except Exception as e:
                logger.warning("TOOL_NEWS_CATEGORY_ERROR category=%s error=%s", category, str(e))
                continue

        if sections_output:
            header = f"Notizie per {context}:"
            return header + "\n".join(sections_output)
        else:
            # Fallback to simple search
            return await self._gnews_search(context)

    async def _gnews_search_raw(self, query: str, max_results: int = 5) -> list:
        """Raw GNews search — returns list of article dicts."""
        url = "https://gnews.io/api/v4/search"
        params = {
            "apikey": GNEWS_API_KEY,
            "q": query,
            "lang": "it",
            "max": max_results,
        }

        client = await self._get_client()
        resp = await client.get(url, params=params)

        logger.info("TOOL_GNEWS_HTTP_STATUS status=%d query=%s", resp.status_code, query)

        if resp.status_code != 200:
            return []

        data = resp.json()
        return data.get("articles", [])

    async def _gnews_search(self, query: str) -> str:
        """Cerca notizie via GNews API (gnews.io/api/v4/search)."""
        url = "https://gnews.io/api/v4/search"
        params = {
            "apikey": GNEWS_API_KEY,
            "q": query,
            "lang": "it",
            "max": 5,
        }

        logger.info("TOOL_GNEWS_HTTP_CALL url=%s query=%s", url, query)
        log("TOOL_GNEWS_HTTP_CALL", url=url, query=query)

        client = await self._get_client()
        resp = await client.get(url, params=params)

        logger.info("TOOL_GNEWS_HTTP_STATUS status=%d query=%s", resp.status_code, query)
        log("TOOL_GNEWS_HTTP_STATUS", status=resp.status_code, query=query)

        if resp.status_code == 401 or resp.status_code == 403:
            logger.error("TOOL_NEWS_API_KEY_INVALID status=%d body=%s", resp.status_code, resp.text[:200])
            log("TOOL_NEWS_API_KEY_INVALID", status=resp.status_code, error=resp.text[:200])
            return "Chiave News API non valida."
        if resp.status_code != 200:
            logger.error("TOOL_GNEWS_HTTP_ERROR status=%d body=%s", resp.status_code, resp.text[:200])
            log("TOOL_GNEWS_HTTP_ERROR", status=resp.status_code, error=resp.text[:200])
            return "Servizio notizie temporaneamente non disponibile."

        data = resp.json()
        return self._format_gnews_it(data, query)

    def _format_gnews_it(self, data: dict, context: str) -> str:
        """Formatta risposta GNews in italiano naturale."""
        try:
            articles = data.get("articles", [])
            if not articles:
                return f"Non ho trovato notizie recenti su {context}."

            lines = [f"Ecco le ultime notizie su {context}:"]
            for i, art in enumerate(articles[:5], 1):
                title = art.get("title", "").strip()
                if title:
                    lines.append(f"{i}. {title}")

            news_info = "\n".join(lines)
            log("TOOL_NEWS_RESPONSE", context=context, count=len(articles))
            return news_info

        except Exception as e:
            logger.error("TOOL_NEWS_FORMAT_ERROR error=%s", str(e))
            return "Servizio notizie temporaneamente non disponibile."

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
        """Estrai nome citta' dal messaggio. Supporta qualsiasi citta' del mondo."""
        message_lower = message.lower()
        # 1. Check known Italian cities first (fast path)
        for city in sorted(CITIES_IT, key=len, reverse=True):
            if city in message_lower:
                return city.title()
        # 2. Regex extraction for any capitalized city name
        import re as _re
        for pattern in CITY_EXTRACT_PATTERNS:
            m = _re.search(pattern, message)
            if m:
                candidate = m.group(1).strip()
                # Filter out common Italian words that aren't cities
                skip_words = {"Come", "Che", "Non", "Per", "Con", "Cosa", "Chi",
                              "Dove", "Quando", "Quanto", "Quale", "Perch\u00e9",
                              "Oggi", "Domani", "Ieri", "Italia", "Europa"}
                if candidate not in skip_words and len(candidate) >= 2:
                    return candidate
        return None

    def _extract_topic(self, message: str) -> Optional[str]:
        """Estrai argomento dal messaggio."""
        message_lower = message.lower()
        for topic in NEWS_CATEGORIES:
            if topic in message_lower:
                return topic
        return None


# Istanza globale
tool_service = ToolService()
