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

# Città italiane per estrazione
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

# Categorie notizie per NewsAPI
NEWS_CATEGORIES = {
    "tecnologia": "technology",
    "sport": "sports",
    "politica": "general",
    "economia": "business",
    "scienza": "science",
    "salute": "health",
    "intrattenimento": "entertainment",
}

# API Keys
OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
NEWSAPI_KEY = os.environ.get("NEWSAPI_KEY", "")

if not OPENWEATHER_API_KEY:
    logger.warning("OPENWEATHER_API_KEY non configurata — il servizio meteo non funzionerà")
if not NEWSAPI_KEY:
    logger.warning("NEWSAPI_KEY non configurata — il servizio notizie non funzionerà")


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

    async def get_weather(self, message: str) -> str:
        """
        Meteo reale via OpenWeather API.
        Formato: "A Roma: cielo sereno, 18°C, umidità 55%, vento 12 km/h."
        Se API fallisce → messaggio di errore, zero dati inventati.
        """
        try:
            log("TOOL_WEATHER_REQUEST", message=message[:50])
            city = self._extract_city(message) or "Roma"

            if not OPENWEATHER_API_KEY:
                logger.error("TOOL_WEATHER_MISSING_KEY error=OPENWEATHER_API_KEY non configurata")
                return "Servizio meteo non configurato."

            url = "https://api.openweathermap.org/data/2.5/weather"
            params = {
                "q": f"{city},IT",
                "appid": OPENWEATHER_API_KEY,
                "units": "metric",
                "lang": "it",
            }

            logger.info("TOOL_WEATHER_HTTP_CALL url=%s city=%s", url, city)
            log("TOOL_WEATHER_HTTP_CALL", url=url, city=city)

            client = await self._get_client()
            resp = await client.get(url, params=params)

            logger.info("TOOL_WEATHER_HTTP_STATUS status=%d city=%s", resp.status_code, city)
            log("TOOL_WEATHER_HTTP_STATUS", status=resp.status_code, city=city)

            if resp.status_code != 200:
                logger.error("TOOL_WEATHER_HTTP_ERROR status=%d body=%s", resp.status_code, resp.text[:200])
                log("TOOL_WEATHER_HTTP_ERROR", status=resp.status_code, error=resp.text[:200])
                return "Servizio meteo temporaneamente non disponibile."

            data = resp.json()
            return self._format_weather_it(data, city)

        except httpx.TimeoutException:
            logger.error("TOOL_WEATHER_HTTP_ERROR error=timeout city=%s", city)
            log("TOOL_WEATHER_HTTP_ERROR", error="timeout")
            return "Servizio meteo temporaneamente non disponibile."
        except Exception as e:
            logger.error("TOOL_WEATHER_HTTP_ERROR error=%s", str(e))
            log("TOOL_WEATHER_HTTP_ERROR", error=str(e))
            return "Servizio meteo temporaneamente non disponibile."

    def _format_weather_it(self, data: dict, city: str) -> str:
        """Formatta risposta OpenWeather in italiano naturale."""
        try:
            desc_en = data.get("weather", [{}])[0].get("description", "")
            # OpenWeather con lang=it già ritorna italiano, ma facciamo fallback
            desc_it = data.get("weather", [{}])[0].get("description", "")
            if not desc_it:
                desc_it = WEATHER_DESC_IT.get(desc_en, desc_en)

            temp = round(data.get("main", {}).get("temp", 0))
            feels_like = round(data.get("main", {}).get("feels_like", 0))
            humidity = data.get("main", {}).get("humidity", 0)
            wind_ms = data.get("wind", {}).get("speed", 0)
            wind_kmh = round(wind_ms * 3.6)

            parts = [f"A {city}: {desc_it}, {temp}°C"]
            if abs(feels_like - temp) >= 2:
                parts.append(f"percepiti {feels_like}°C")
            parts.append(f"umidità {humidity}%")
            parts.append(f"vento {wind_kmh} km/h")

            weather_info = ", ".join(parts) + "."

            log("TOOL_WEATHER_RESPONSE", city=city, temp=temp, desc=desc_it)
            return weather_info

        except Exception as e:
            logger.error("TOOL_WEATHER_FORMAT_ERROR error=%s", str(e))
            return "Servizio meteo temporaneamente non disponibile."

    # ───────────────────────────────────────────────────────────
    # NEWS — NewsAPI reale
    # ───────────────────────────────────────────────────────────

    async def get_news(self, message: str) -> str:
        """
        Notizie reali via NewsAPI.
        Se API fallisce → messaggio di errore, zero dati inventati.
        """
        try:
            log("TOOL_NEWS_REQUEST", message=message[:50])

            if not NEWSAPI_KEY:
                logger.error("TOOL_NEWS_MISSING_KEY error=NEWSAPI_KEY non configurata")
                return "Servizio notizie non configurato."

            topic = self._extract_topic(message)
            city = self._extract_city(message)

            # Se c'è una città, cerca notizie specifiche per quella città
            if city:
                return await self._news_by_query(city, topic)
            elif topic:
                return await self._news_by_category(topic)
            else:
                return await self._news_top_headlines()

        except httpx.TimeoutException:
            logger.error("TOOL_NEWS_HTTP_ERROR error=timeout")
            log("TOOL_NEWS_HTTP_ERROR", error="timeout")
            return "Servizio notizie temporaneamente non disponibile."
        except Exception as e:
            logger.error("TOOL_NEWS_HTTP_ERROR error=%s", str(e))
            log("TOOL_NEWS_HTTP_ERROR", error=str(e))
            return "Servizio notizie temporaneamente non disponibile."

    async def _news_by_query(self, city: str, topic: Optional[str] = None) -> str:
        """Cerca notizie per città (e opzionalmente topic)."""
        q = city
        if topic:
            q = f"{city} {topic}"

        url = "https://newsapi.org/v2/everything"
        params = {
            "q": q,
            "language": "it",
            "sortBy": "publishedAt",
            "pageSize": 5,
            "apiKey": NEWSAPI_KEY,
        }

        logger.info("TOOL_NEWS_HTTP_CALL url=%s query=%s", url, q)
        log("TOOL_NEWS_HTTP_CALL", url=url, query=q)

        client = await self._get_client()
        resp = await client.get(url, params=params)

        logger.info("TOOL_NEWS_HTTP_STATUS status=%d query=%s", resp.status_code, q)
        log("TOOL_NEWS_HTTP_STATUS", status=resp.status_code, query=q)

        if resp.status_code == 401:
            logger.error("TOOL_NEWS_API_KEY_INVALID status=401 body=%s", resp.text[:200])
            log("TOOL_NEWS_API_KEY_INVALID", status=401, error=resp.text[:200])
            return "Chiave News API non valida."
        if resp.status_code != 200:
            logger.error("TOOL_NEWS_HTTP_ERROR status=%d body=%s", resp.status_code, resp.text[:200])
            log("TOOL_NEWS_HTTP_ERROR", status=resp.status_code, error=resp.text[:200])
            return "Servizio notizie temporaneamente non disponibile."

        data = resp.json()
        return self._format_news_it(data, q)

    async def _news_by_category(self, topic: str) -> str:
        """Cerca notizie per categoria."""
        category = NEWS_CATEGORIES.get(topic, "general")

        url = "https://newsapi.org/v2/top-headlines"
        params = {
            "country": "it",
            "category": category,
            "pageSize": 5,
            "apiKey": NEWSAPI_KEY,
        }

        logger.info("TOOL_NEWS_HTTP_CALL url=%s category=%s topic=%s", url, category, topic)
        log("TOOL_NEWS_HTTP_CALL", url=url, category=category, topic=topic)

        client = await self._get_client()
        resp = await client.get(url, params=params)

        logger.info("TOOL_NEWS_HTTP_STATUS status=%d category=%s", resp.status_code, category)
        log("TOOL_NEWS_HTTP_STATUS", status=resp.status_code, category=category)

        if resp.status_code == 401:
            logger.error("TOOL_NEWS_API_KEY_INVALID status=401 body=%s", resp.text[:200])
            log("TOOL_NEWS_API_KEY_INVALID", status=401, error=resp.text[:200])
            return "Chiave News API non valida."
        if resp.status_code != 200:
            logger.error("TOOL_NEWS_HTTP_ERROR status=%d body=%s", resp.status_code, resp.text[:200])
            log("TOOL_NEWS_HTTP_ERROR", status=resp.status_code, error=resp.text[:200])
            return "Servizio notizie temporaneamente non disponibile."

        data = resp.json()
        return self._format_news_it(data, topic)

    async def _news_top_headlines(self) -> str:
        """Top headlines Italia."""
        url = "https://newsapi.org/v2/top-headlines"
        params = {
            "country": "it",
            "pageSize": 5,
            "apiKey": NEWSAPI_KEY,
        }

        logger.info("TOOL_NEWS_HTTP_CALL url=%s country=it", url)
        log("TOOL_NEWS_HTTP_CALL", url=url, country="it")

        client = await self._get_client()
        resp = await client.get(url, params=params)

        logger.info("TOOL_NEWS_HTTP_STATUS status=%d", resp.status_code)
        log("TOOL_NEWS_HTTP_STATUS", status=resp.status_code)

        if resp.status_code == 401:
            logger.error("TOOL_NEWS_API_KEY_INVALID status=401 body=%s", resp.text[:200])
            log("TOOL_NEWS_API_KEY_INVALID", status=401, error=resp.text[:200])
            return "Chiave News API non valida."
        if resp.status_code != 200:
            logger.error("TOOL_NEWS_HTTP_ERROR status=%d body=%s", resp.status_code, resp.text[:200])
            log("TOOL_NEWS_HTTP_ERROR", status=resp.status_code, error=resp.text[:200])
            return "Servizio notizie temporaneamente non disponibile."

        data = resp.json()
        return self._format_news_it(data, "Italia")

    def _format_news_it(self, data: dict, context: str) -> str:
        """Formatta risposta NewsAPI in italiano naturale."""
        try:
            articles = data.get("articles", [])
            if not articles:
                return f"Non ho trovato notizie recenti su {context}."

            lines = [f"Ecco le ultime notizie su {context}:"]
            for i, art in enumerate(articles[:5], 1):
                title = art.get("title", "").strip()
                # NewsAPI a volte mette " - Source" alla fine del titolo
                if " - " in title:
                    title = title.rsplit(" - ", 1)[0].strip()
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
        """Estrai nome città dal messaggio. Supporta 60+ città italiane."""
        message_lower = message.lower()
        # Controlla prima le città composte (es: "reggio calabria")
        for city in sorted(CITIES_IT, key=len, reverse=True):
            if city in message_lower:
                return city.title()
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
