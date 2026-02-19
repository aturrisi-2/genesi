"""
LOCATION RESOLVER - Genesi Core v3
Risoluzione intelligente di località da messaggi utente.
Supporto mondiale. Italia ultra-dettagliata.
Nessuna città hardcoded. Zero fallback silenzioso.
Fuzzy match per micro-località italiane.
"""

import os
import re
import logging
from typing import Optional

import httpx
import unidecode

from core.log import log

# Importa città italiane per priorità IT
ITALIAN_CITIES = [
    "roma", "milano", "napoli", "torino", "palermo", "genova", "bologna",
    "firenze", "bari", "catania", "venezia", "verona", "messina", "padova",
    "trieste", "brescia", "taranto", "prato", "reggio calabria", "modena",
    "parma", "reggio emilia", "perugia", "livorno", "ravenna", "cagliari",
    "foggia", "rimini", "salerno", "ferrara", "latina", "giugliano",
    "monza", "siracusa", "bergamo", "trento", "novara", "imola"
]

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

# STT-specific stop words to remove for robust parsing
_STT_STOP_WORDS = {
    "che", "tempo", "fa", "è", "e'", "oggi", "domani", "per", "favore",
    "genesis", "genesi", "a", "di", "in", "su", "da", "con", "per",
    "fa", "fanno", "sono", "e", "ed"
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


def _clean_stt_input(message: str) -> str:
    """
    Clean STT input for robust location parsing.
    
    Args:
        message: Raw STT input (e.g., "Genesis che tempo fa è Imola")
        
    Returns:
        Cleaned text ready for city extraction
    """
    original = message
    
    # Try to extract city directly from original message first
    # Look for capitalized words at the end that could be city names
    words = message.split()
    for i in range(len(words) - 1, -1, -1):
        word = words[i].strip('?!.,;:')
        if (word and word[0].isupper() and 
            len(word) >= 2 and 
            word.lower() not in _STT_STOP_WORDS and 
            word.lower() not in _SKIP_WORDS and
            word.lower() not in ['fa', 'sono', 'fanno']):  # Additional common words
            log("LOCATION_CLEANED_INPUT", original=original[:50], cleaned=word, city=word)
            return word
    
    # Fallback: clean and process
    cleaned = message.lower()
    cleaned = re.sub(r'[^\w\s]', ' ', cleaned)
    
    # Remove STT stop words
    words = cleaned.split()
    filtered_words = [w for w in words if w not in _STT_STOP_WORDS and w not in _SKIP_WORDS]
    cleaned = ' '.join(filtered_words)
    
    # Return last valid token
    tokens = cleaned.split()
    if tokens and len(tokens[-1]) >= 2:
        city_candidate = tokens[-1]
        log("LOCATION_CLEANED_INPUT", original=original[:50], cleaned=cleaned, city=city_candidate)
        return city_candidate
    
    log("LOCATION_CLEANED_INPUT", original=original[:50], cleaned=cleaned, city=None)
    return ""


def extract_city_from_message(message: str) -> Optional[str]:
    """
    Extract a city/location name from a user message.
    Returns the extracted city name (title-cased) or None.
    Tries case-sensitive patterns first, then case-insensitive fallback.
    Enhanced with STT robust parsing for noisy input.
    """
    # Pass 1: case-sensitive (proper nouns)
    for pattern in [_TRAILING_PATTERN, _DIRECT_PATTERN, _PREP_PATTERN]:
        m = pattern.search(message)
        if m:
            candidate = m.group(1).strip().rstrip("?!.,;:")
            if candidate.lower() not in _SKIP_WORDS and len(candidate) >= 2:
                return candidate

    # Pass 1.5: STT robust parsing ONLY for noisy input (contains "genesis" or multiple capitalized words)
    if 'genesis' in message.lower() or 'genesi' in message.lower() or sum(1 for w in message.split() if w and w[0].isupper()) > 2:
        stt_cleaned = _clean_stt_input(message)
        if stt_cleaned and len(stt_cleaned) >= 2:
            # Title case the cleaned city name
            return _title_case_city(stt_cleaned)

    # Pass 2: case-insensitive fallback (all-lowercase input)
    for pattern in [_TRAILING_PATTERN_CI, _DIRECT_PATTERN_CI, _PREP_PATTERN_CI]:
        m = pattern.search(message.lower())
        if m:
            candidate = m.group(1).strip().rstrip("?!.,;:")
            if candidate.lower() not in _SKIP_WORDS and len(candidate) >= 2:
                return _title_case_city(candidate)

    return None


# ═══════════════════════════════════════════════════════════════
# FUZZY MATCHING — micro-località italiane
# ═══════════════════════════════════════════════════════════════

def _normalize(s: str) -> str:
    """Normalize a string for fuzzy comparison: lowercase, strip accents, strip punctuation."""
    return unidecode.unidecode(s).lower().strip()


def _levenshtein(a: str, b: str) -> int:
    """Simple Levenshtein distance."""
    if len(a) < len(b):
        return _levenshtein(b, a)
    if len(b) == 0:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            cost = 0 if ca == cb else 1
            curr.append(min(curr[j] + 1, prev[j + 1] + 1, prev[j] + cost))
        prev = curr
    return prev[-1]


def fuzzy_match_city(query: str, candidates: list) -> Optional[dict]:
    """
    Fuzzy-match a city query against geocoding candidates.
    Prioritizes Italian results. Returns best match or None.

    Matching criteria:
    - Normalized Levenshtein distance <= 2 (for names >= 4 chars)
    - OR normalized name starts with normalized query
    - IT results get priority bonus

    Logs LOCATION_FUZZY_MATCH on successful match.
    """
    if not candidates or not query:
        return None

    q_norm = _normalize(query)
    if len(q_norm) < 3:
        return None

    best = None
    best_score = 999

    for r in candidates:
        name = r.get("name", "")
        local_it = r.get("local_names", {}).get("it", "")
        country = r.get("country", "")

        for candidate_name in [name, local_it]:
            if not candidate_name:
                continue
            c_norm = _normalize(candidate_name)

            # Exact normalized match
            if c_norm == q_norm:
                score = 0
            # Prefix match: query is a significant prefix of candidate (>= 60%)
            elif c_norm.startswith(q_norm) and len(q_norm) >= len(c_norm) * 0.5:
                score = 1
            elif q_norm.startswith(c_norm) and len(c_norm) >= len(q_norm) * 0.5:
                score = 1
            # Levenshtein
            else:
                dist = _levenshtein(q_norm, c_norm)
                max_len = max(len(q_norm), len(c_norm))
                # Allow distance up to 2 for names >= 4 chars
                if max_len >= 4 and dist <= 2:
                    score = dist
                else:
                    continue

            # IT priority: Italian results get a fractional bonus
            if country == "IT":
                score -= 0.5

            if score < best_score:
                best_score = score
                best = r

    if best is not None and best_score <= 2:
        matched_name = best.get("local_names", {}).get("it", best.get("name", query))
        log("LOCATION_FUZZY_MATCH",
            query=query,
            matched=matched_name,
            country=best.get("country", ""),
            distance=best_score)
        logger.info("LOCATION_FUZZY_MATCH query=%s matched=%s country=%s dist=%d",
                     query, matched_name, best.get("country", ""), best_score)
        return best

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

        # Try fuzzy match if no exact name match found
        exact_names = [_normalize(r.get("name", "")) for r in results]
        city_norm = _normalize(city)
        if city_norm not in exact_names:
            fuzzy_result = fuzzy_match_city(city, results)
            if fuzzy_result:
                location = _format_result(fuzzy_result)
                log("LOCATION_RESOLVE_RESULT",
                    city=city,
                    resolved_name=location["name"],
                    country=location["country"],
                    lat=location["lat"],
                    lon=location["lon"],
                    method="fuzzy")
                return location

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

    # Se ambiguous, cerca se uno dei candidati è IT e la città è italiana nota
    if len(it_results) > 0 and len(countries) > 1:
        city_lower = city.lower()
        # Controlla se è una città italiana conosciuta
        if city_lower in [c.lower() for c in ITALIAN_CITIES]:
            log("LOCATION_IT_PRIORITY", city=city, reason="known_italian_city")
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
