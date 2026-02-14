"""
LOCATION RESOLVER - Genesi Core v2
Risoluzione intelligente di località da messaggi utente.
Supporto mondiale. Italia ultra-dettagliata.
Nessuna città hardcoded. Zero fallback silenzioso.
"""

import os
import re
import logging
from typing import Optional

import httpx

from core.log import log

logger = logging.getLogger(__name__)

OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")

# ═══════════════════════════════════════════════════════════════
# EXCEPTIONS
# ═══════════════════════════════════════════════════════════════

class LocationNotFoundError(Exception):
    """Raised when no geocoding result is found."""
    pass


class AmbiguousLocationError(Exception):
    """Raised when multiple locations match and disambiguation is needed."""
    def __init__(self, message: str, candidates: list):
        super().__init__(message)
        self.candidates = candidates


# ═══════════════════════════════════════════════════════════════
# CITY EXTRACTION FROM MESSAGE
# ═══════════════════════════════════════════════════════════════

# Connectors that can appear inside multi-word city names
_CITY_CONNECTORS = r"(?:del|di|dei|delle|della|dello|d'|l'|sul|sulla|in|al|alla|san|santo|santa|saint|los|las|el|le|la|new|old|fort|mount|port|east|west|north|south)"

# Capitalized word pattern for city names
_CAP_WORD = r"[A-ZÀ-Ú][a-zà-ú']+"

# ── Case-sensitive patterns (preferred — match proper nouns) ──

# Prepositions that precede city names in Italian
_PREP_PATTERN = re.compile(
    r"(?:^|[\s,])(?:a|ad|di|da|in|su|per|nel|nella|nello|nell'|dello|della|del)"
    rf"\s+({_CAP_WORD}(?:\s+{_CITY_CONNECTORS}\s+)?(?:{_CAP_WORD}(?:\s+{_CAP_WORD})*)?)",
    re.UNICODE
)

# Direct patterns: "meteo Tokyo", "notizie Bangkok", "tempo a Milano"
_DIRECT_PATTERN = re.compile(
    r"(?:meteo|tempo|previsioni|notizie|news|clima)\s+(?:a|di|per|in|da|su)?\s*"
    rf"({_CAP_WORD}(?:\s+{_CITY_CONNECTORS}\s+)?(?:{_CAP_WORD}(?:\s+{_CAP_WORD})*)?)",
    re.UNICODE
)

# Trailing city: "che tempo fa a Kyoto?"
_TRAILING_PATTERN = re.compile(
    r"(?:che\s+(?:tempo|meteo)\s+fa|com'è\s+il\s+(?:tempo|meteo)|piove|nevica|fa\s+(?:caldo|freddo))"
    rf"\s+(?:a|ad|in|di|da|su|per)\s+"
    rf"({_CAP_WORD}(?:\s+{_CITY_CONNECTORS}\s+)?(?:{_CAP_WORD}(?:\s+{_CAP_WORD})*)?)",
    re.UNICODE
)

# ── Case-insensitive fallback patterns (for all-lowercase input) ──

_CI_WORD = r"[a-zà-ú']+"

# Case-insensitive: capture everything after the preposition until end/punctuation
_PREP_PATTERN_CI = re.compile(
    r"(?:^|[\s,])(?:a|ad|di|da|in|su|per|nel|nella|nello|nell'|dello|della|del)"
    rf"\s+({_CI_WORD}(?:\s+{_CI_WORD})*)",
    re.UNICODE
)

_DIRECT_PATTERN_CI = re.compile(
    r"(?:meteo|tempo|previsioni|notizie|news|clima)\s+(?:a|di|per|in|da|su)?\s*"
    rf"({_CI_WORD}(?:\s+{_CI_WORD})*)",
    re.UNICODE
)

_TRAILING_PATTERN_CI = re.compile(
    r"(?:che\s+(?:tempo|meteo)\s+fa|com'è\s+il\s+(?:tempo|meteo)|piove|nevica|fa\s+(?:caldo|freddo))"
    rf"\s+(?:a|ad|in|di|da|su|per)\s+"
    rf"({_CI_WORD}(?:\s+{_CI_WORD})*)",
    re.UNICODE
)

# Words to skip — common Italian words that aren't cities
_SKIP_WORDS = {
    "come", "che", "non", "per", "con", "cosa", "chi", "dove", "quando",
    "quanto", "quale", "perché", "oggi", "domani", "ieri", "italia",
    "europa", "mondo", "sera", "mattina", "pomeriggio", "notte",
    "tempo", "meteo", "previsioni", "notizie", "news", "ultime",
    "momento", "adesso", "ora", "sempre", "mai", "ancora", "anche",
    "molto", "poco", "tutto", "niente", "qualcosa", "qualcuno",
    "fa", "fatto", "fare", "bene", "male", "così", "cosi", "tanto",
    "questo", "quello", "qui", "qua", "là", "la", "li", "lo",
}


def _title_case_city(name: str) -> str:
    """Title-case a city name, preserving connectors lowercase."""
    connectors = {"del", "di", "dei", "delle", "della", "dello", "d'", "l'",
                  "sul", "sulla", "in", "al", "alla"}
    words = name.split()
    result = []
    for i, w in enumerate(words):
        if i > 0 and w.lower() in connectors:
            result.append(w.lower())
        else:
            result.append(w.capitalize())
    return " ".join(result)


def extract_city_from_message(message: str) -> Optional[str]:
    """
    Extract a city/location name from a user message.
    Returns the extracted city name (title-cased) or None.
    Tries case-sensitive patterns first, then case-insensitive fallback.
    """
    # Pass 1: case-sensitive (proper nouns)
    for pattern in [_TRAILING_PATTERN, _DIRECT_PATTERN, _PREP_PATTERN]:
        m = pattern.search(message)
        if m:
            candidate = m.group(1).strip().rstrip("?!.,;:")
            if candidate.lower() not in _SKIP_WORDS and len(candidate) >= 2:
                return candidate

    # Pass 2: case-insensitive fallback (all-lowercase input)
    for pattern in [_TRAILING_PATTERN_CI, _DIRECT_PATTERN_CI, _PREP_PATTERN_CI]:
        m = pattern.search(message.lower())
        if m:
            candidate = m.group(1).strip().rstrip("?!.,;:")
            if candidate.lower() not in _SKIP_WORDS and len(candidate) >= 2:
                return _title_case_city(candidate)

    return None


# ═══════════════════════════════════════════════════════════════
# GEOCODING — OpenWeather Geocoding API
# ═══════════════════════════════════════════════════════════════

async def resolve_location(message: str, http_client: Optional[httpx.AsyncClient] = None) -> dict:
    """
    Resolve a location from a user message.

    Steps:
    1. Extract city name from message
    2. Call OpenWeather Geocoding API (global)
    3. Disambiguate: prefer IT if Italian context, raise if ambiguous
    4. Return {name, lat, lon, country, state}

    Raises:
        LocationNotFoundError: if no city extracted or no geocoding result
        AmbiguousLocationError: if multiple ambiguous results
    """
    city = extract_city_from_message(message)
    if not city:
        log("LOCATION_NOT_FOUND", message=message[:60], reason="no_city_extracted")
        raise LocationNotFoundError(f"Non riesco a identificare una località nel messaggio.")

    log("LOCATION_RESOLVE_REQUEST", city=city, message=message[:60])

    if not OPENWEATHER_API_KEY:
        raise LocationNotFoundError("Servizio di geolocalizzazione non configurato.")

    # Call geocoding API
    client = http_client
    close_after = False
    if client is None:
        client = httpx.AsyncClient(timeout=10.0)
        close_after = True

    try:
        url = "https://api.openweathermap.org/geo/1.0/direct"
        params = {"q": city, "limit": 5, "appid": OPENWEATHER_API_KEY}
        resp = await client.get(url, params=params)

        if resp.status_code != 200:
            logger.error("LOCATION_GEOCODE_HTTP_ERROR status=%d city=%s", resp.status_code, city)
            raise LocationNotFoundError(f"Errore nel servizio di geolocalizzazione per '{city}'.")

        results = resp.json()

        if not results:
            log("LOCATION_NOT_FOUND", city=city, reason="no_geocoding_result")
            raise LocationNotFoundError(f"Non trovo la località '{city}'. Verifica il nome e riprova.")

        # Disambiguate
        location = _disambiguate(city, results, message)

        log("LOCATION_RESOLVE_RESULT",
            city=city,
            resolved_name=location["name"],
            country=location["country"],
            lat=location["lat"],
            lon=location["lon"])

        return location

    finally:
        if close_after:
            await client.aclose()


def _disambiguate(city: str, results: list, message: str) -> dict:
    """
    Disambiguate geocoding results.
    - If only 1 result → use it
    - If multiple results in different countries:
      - If message is Italian context → prefer IT result
      - If strong ambiguity (e.g. Springfield) → raise AmbiguousLocationError
    """
    if len(results) == 1:
        return _format_result(results[0])

    # Check if there's an IT result
    it_results = [r for r in results if r.get("country") == "IT"]
    non_it_results = [r for r in results if r.get("country") != "IT"]

    # If exactly one IT result and message looks Italian → prefer IT
    if len(it_results) == 1 and non_it_results:
        log("LOCATION_RESOLVE_RESULT",
            city=city,
            resolved_name=it_results[0].get("name", city),
            country="IT",
            reason="italian_priority")
        return _format_result(it_results[0])

    # Check if all results are in the same country → just pick first
    countries = set(r.get("country", "") for r in results)
    if len(countries) == 1:
        return _format_result(results[0])

    # Strong ambiguity: same city name in multiple countries, no clear IT preference
    # Check if the city name is identical across results (true ambiguity)
    names_lower = set(r.get("name", "").lower() for r in results)
    if len(names_lower) <= 2 and len(countries) >= 3:
        # e.g. Springfield exists in 5+ US states and other countries
        candidates = []
        for r in results[:5]:
            state = r.get("state", "")
            country = r.get("country", "")
            name = r.get("name", city)
            label = f"{name}, {state}, {country}" if state else f"{name}, {country}"
            candidates.append({
                "label": label,
                "name": name,
                "country": country,
                "state": state,
                "lat": r.get("lat"),
                "lon": r.get("lon"),
            })

        log("LOCATION_AMBIGUOUS", city=city, candidates_count=len(candidates))
        raise AmbiguousLocationError(
            f"Ci sono più località chiamate '{city}'. Quale intendi?\n" +
            "\n".join(f"  - {c['label']}" for c in candidates),
            candidates=candidates
        )

    # Default: pick the first result (most relevant by API ranking)
    return _format_result(results[0])


def _format_result(r: dict) -> dict:
    """Format a single geocoding result into our standard dict."""
    # Prefer Italian local name if available
    name = r.get("local_names", {}).get("it", r.get("name", ""))
    return {
        "name": name,
        "lat": r["lat"],
        "lon": r["lon"],
        "country": r.get("country", ""),
        "state": r.get("state", ""),
    }
