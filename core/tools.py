# core/tools.py
# Livello TOOL/API per Genesi-Fatti.
# Ogni funzione chiama un'API esterna e restituisce dati grezzi
# che verranno sintetizzati da GPT-4o-mini.

import os
import re
import json
import asyncio
from datetime import datetime
from typing import Optional, Dict, List

import httpx


# ===============================
# CONFIGURAZIONE API KEYS
# ===============================

def _get_openweather_key() -> Optional[str]:
    key = os.getenv("OPENWEATHER_API_KEY")
    print(f"[ENV_CHECK] OPENWEATHER_API_KEY={'OK' if key else 'KO'}", flush=True)
    return key

def _get_newsapi_key() -> Optional[str]:
    key = os.getenv("NEWSAPI_KEY")
    print(f"[ENV_CHECK] NEWSAPI_KEY={'OK' if key else 'KO'}", flush=True)
    return key

def check_api_keys() -> Dict[str, bool]:
    """
    Verifica tutte le API keys disponibili
    """
    return {
        "openweather": bool(_get_openweather_key()),
        "newsapi": bool(_get_newsapi_key()),
        "openai": bool(os.getenv("OPENAI_API_KEY"))
    }


# ===============================
# HELPERS
# ===============================

def _r1(val) -> str:
    """Arrotonda un numero a 1 decimale. Restituisce stringa."""
    try:
        return f"{float(val):.1f}"
    except (TypeError, ValueError):
        return str(val)


# ===============================
# CITY / LOCATION EXTRACTION
# ===============================

_PREP_PATTERN = re.compile(
    r"\b(?:a|ad|di|su|per|in|da|nel|nella|nello|nell|dello|della|del)\s+"
    r"([A-ZÀ-Úa-zà-ú][a-zà-ú']+(?:\s+(?:di|del|della|dell|dei|delle|d'|in|al|alla|sul|sulla)?\s*[A-ZÀ-Úa-zà-ú][a-zà-ú']+)*)",
    re.UNICODE
)

_STOP_WORDS = {
    "meteo", "tempo", "temperatura", "previsioni", "notizie", "notizia", "news",
    "cronaca", "attualità", "oggi", "domani", "ieri", "adesso", "ora", "che",
    "come", "quanto", "quanti", "quale", "quali", "cosa", "dove", "quando",
    "piove", "pioverà", "neve", "vento", "sole", "gradi", "caldo", "freddo",
    "successo", "succede", "succedendo", "ultime", "ultima", "degno", "nota",
    "per", "a", "ad", "fa", "il", "lo", "la", "le", "gli", "un", "una",
}

_LINK_WORDS = {"di", "del", "della", "dell", "dei", "delle", "d'", "in", "al", "alla", "sul", "sulla", "sant", "san"}

def extract_city(text: str) -> str:
    """Estrae la località dal messaggio. Supporta qualsiasi luogo. Default: Roma."""

    # 1. PRIORITÀ: cattura tutto dopo keyword meteo/notizie (nomi multi-parola)
    text_lower = text.lower()
    for kw in ["meteo ", "tempo a ", "previsioni ", "notizie di ", "notizie da ",
               "notizie a ", "notizie su ", "notizie "]:
        idx = text_lower.find(kw)
        if idx >= 0:
            rest = text[idx + len(kw):].strip()
            rest_words = rest.split()
            location_parts = []
            for rw in rest_words:
                clean = rw.strip(".,!?;:'\"")
                if not clean:
                    break
                if clean.lower() in _STOP_WORDS and len(clean) <= 1:
                    break
                if clean.lower() in _STOP_WORDS and not location_parts:
                    continue  # skip leading stop words
                # Articoli interni (di, del, sant, san, etc.) sono OK dentro un nome
                if clean.lower() in _LINK_WORDS or clean.lower() in _STOP_WORDS:
                    if location_parts and clean.lower() in _LINK_WORDS:
                        location_parts.append(clean)
                        continue
                    if not location_parts:
                        continue
                    break
                location_parts.append(clean)
            if location_parts:
                loc = " ".join(location_parts)
                print(f"[CITY_EXTRACT] found via keyword: '{loc}'", flush=True)
                return loc.title()

    # 2. Cerca dopo preposizione (a, di, in, etc.)
    for match in _PREP_PATTERN.finditer(text):
        candidate = match.group(1).strip()
        if candidate.lower() not in _STOP_WORDS and len(candidate) > 1:
            print(f"[CITY_EXTRACT] found via prep: '{candidate}'", flush=True)
            return candidate.title()

    # 3. Cerca parole capitalizzate e costruisci nome multi-parola
    words = text.split()
    for i, w in enumerate(words):
        clean = w.strip(".,!?;:'\"")
        if clean and clean[0].isupper() and clean.lower() not in _STOP_WORDS and len(clean) > 1:
            parts = [clean]
            j = i + 1
            while j < len(words):
                nw = words[j].strip(".,!?;:'\"")
                if not nw:
                    break
                if nw.lower() in _LINK_WORDS:
                    parts.append(nw)
                    j += 1
                    continue
                if nw[0].isupper() and nw.lower() not in _STOP_WORDS:
                    parts.append(nw)
                    j += 1
                    continue
                break
            result = " ".join(parts)
            print(f"[CITY_EXTRACT] found via caps: '{result}'", flush=True)
            return result.title()

    print(f"[CITY_EXTRACT] default: Roma", flush=True)
    return "Roma"


# ===============================
# 1. METEO — OpenWeatherMap (GLOBALE)
# ===============================

async def _geocode_city(client, city: str, api_key: str) -> Optional[Dict]:
    """Usa OpenWeather Geocoding API per risolvere qualsiasi località in coordinate.
    Supporta villaggi, frazioni, comuni minuscoli — qualsiasi luogo nel mondo."""
    geo_url = "https://api.openweathermap.org/geo/1.0/direct"
    # Prova prima con ,IT per località italiane
    for query in [f"{city},IT", city]:
        resp = await client.get(geo_url, params={
            "q": query,
            "limit": 1,
            "appid": api_key
        })
        if resp.status_code == 200:
            data = resp.json()
            if data:
                loc = data[0]
                resolved = loc.get("local_names", {}).get("it", loc.get("name", city))
                print(f"[GEOCODE] ✓ '{city}' → {resolved} ({loc['lat']}, {loc['lon']}) country={loc.get('country','?')}", flush=True)
                return {"lat": loc["lat"], "lon": loc["lon"], "name": resolved, "country": loc.get("country", "")}
    print(f"[GEOCODE] ✗ '{city}' non trovata", flush=True)
    return None


async def fetch_weather(user_message: str) -> Dict:
    """Chiama OpenWeatherMap e restituisce dati meteo reali per QUALSIASI località."""
    print(f"[DEBUG_WEATHER] weather handler ENTERED", flush=True)
    print(f"[DEBUG_WEATHER] raw_message={user_message}", flush=True)
    
    api_key = _get_openweather_key()
    print(f"[FATTI][API_CALL] OPENWEATHER_API_KEY present: {bool(api_key)}", flush=True)
    if not api_key:
        print("[FATTI][API_METEO] ❌ OPENWEATHER_API_KEY non configurata", flush=True)
        return {"error": "API meteo non configurata", "source": "openweathermap"}

    city = extract_city(user_message)
    print(f"[FATTI][API_METEO] città_estratta={city}", flush=True)
    print(f"[DEBUG_WEATHER] calling OpenWeather API", flush=True)

    async with httpx.AsyncClient(timeout=12.0) as client:
        try:
            # STEP 1: Geocoding — risolvi qualsiasi località in coordinate
            geo = await _geocode_city(client, city, api_key)
            if not geo:
                return {"error": f"Località '{city}' non trovata", "source": "openweathermap"}

            lat, lon = geo["lat"], geo["lon"]
            resolved_name = geo["name"]

            # STEP 2: Current weather via coordinate (funziona per qualsiasi punto)
            current_url = "https://api.openweathermap.org/data/2.5/weather"
            current_resp = await client.get(current_url, params={
                "lat": lat, "lon": lon,
                "appid": api_key,
                "units": "metric",
                "lang": "it"
            })
            current_data = current_resp.json()
            print(f"[DEBUG_WEATHER] api_response_received status={current_resp.status_code}", flush=True)

            # STEP 3: Forecast via coordinate
            forecast_url = "https://api.openweathermap.org/data/2.5/forecast"
            forecast_resp = await client.get(forecast_url, params={
                "lat": lat, "lon": lon,
                "appid": api_key,
                "units": "metric",
                "lang": "it",
                "cnt": 16
            })
            forecast_data = forecast_resp.json()

            result = {
                "source": "openweathermap",
                "city": resolved_name,
                "timestamp": datetime.now().isoformat(),
                "current": {},
                "forecast": []
            }

            print(f"[FATTI][API_DATA_SAMPLE] weather_status={current_resp.status_code} forecast_status={forecast_resp.status_code}", flush=True)

            # Parse current — TUTTI I NUMERI ARROTONDATI A 1 DECIMALE
            if "main" in current_data:
                result["current"] = {
                    "temp": _r1(current_data["main"]["temp"]),
                    "feels_like": _r1(current_data["main"]["feels_like"]),
                    "temp_min": _r1(current_data["main"]["temp_min"]),
                    "temp_max": _r1(current_data["main"]["temp_max"]),
                    "humidity": round(current_data["main"]["humidity"]),
                    "description": current_data.get("weather", [{}])[0].get("description", ""),
                    "wind_speed": _r1(current_data.get("wind", {}).get("speed", 0)),
                }
                print(f"[FATTI][API_METEO] ✓ current: {result['current']['temp']}°C, {result['current']['description']}", flush=True)

            # Parse forecast — ARROTONDATO
            if "list" in forecast_data:
                for item in forecast_data["list"]:
                    result["forecast"].append({
                        "datetime": item.get("dt_txt", ""),
                        "temp": _r1(item["main"]["temp"]),
                        "temp_min": _r1(item["main"]["temp_min"]),
                        "temp_max": _r1(item["main"]["temp_max"]),
                        "description": item.get("weather", [{}])[0].get("description", ""),
                        "humidity": round(item["main"]["humidity"]),
                        "wind_speed": _r1(item.get("wind", {}).get("speed", 0)),
                    })
                print(f"[FATTI][API_METEO] ✓ forecast: {len(result['forecast'])} entries", flush=True)

            return result

        except Exception as e:
            print(f"[FATTI][API_METEO] ❌ errore: {e}", flush=True)
            return {"error": str(e), "source": "openweathermap"}


# ===============================
# 2. NEWS — GNews API (GLOBALE)
# ===============================

def _extract_news_location(text: str) -> Optional[str]:
    """Estrae località specifica per ricerca notizie locali."""
    msg_lower = text.lower()
    # Se contiene keyword di località + preposizione → estrai
    for kw in ["notizie di", "notizie da", "notizie a", "notizie su",
               "news di", "news da", "cronaca di", "cronaca da",
               "succede a", "successo a", "successo a", "succedendo a"]:
        idx = msg_lower.find(kw)
        if idx >= 0:
            rest = text[idx + len(kw):].strip()
            rest_words = rest.split()
            location_parts = []
            for rw in rest_words:
                clean = rw.strip(".,!?;:'\"")
                if clean.lower() in _STOP_WORDS or len(clean) <= 1:
                    break
                location_parts.append(clean)
                if len(location_parts) >= 3:
                    break
            if location_parts:
                loc = " ".join(location_parts)
                print(f"[NEWS_LOCATION] found: '{loc}'", flush=True)
                return loc
    # Prova extract_city come fallback
    city = extract_city(text)
    if city != "Roma":
        return city
    return None


async def fetch_news(user_message: str) -> Dict:
    """Chiama GNews API per notizie aggiornate. Supporta ricerca per località."""
    api_key = _get_newsapi_key()
    print(f"[FATTI][API_CALL] NEWSAPI_KEY present: {bool(api_key)}", flush=True)
    if not api_key:
        print("[FATTI][API_NEWS] ❌ NEWSAPI_KEY non configurata", flush=True)
        return {"error": "API news non configurata", "source": "gnews"}

    msg_lower = user_message.lower()

    # Determina topic
    topic = "general"
    if any(w in msg_lower for w in ["economia", "economica", "economico", "borsa", "mercati", "pil"]):
        topic = "business"
    elif any(w in msg_lower for w in ["tecnologia", "tech", "digitale", "ai", "intelligenza artificiale"]):
        topic = "technology"
    elif any(w in msg_lower for w in ["scienza", "scientifico", "ricerca", "scoperta"]):
        topic = "science"
    elif any(w in msg_lower for w in ["sport", "calcio", "serie a", "champions"]):
        topic = "sports"
    elif any(w in msg_lower for w in ["salute", "sanità", "medico", "ospedale"]):
        topic = "health"

    # Determina lingua e paese
    lang = "it"
    country = "it"
    if any(w in msg_lower for w in ["europa", "europee", "europeo", "mondo", "mondiale", "internazional"]):
        country = ""

    # Estrai località per ricerca locale
    location = _extract_news_location(user_message)

    print(f"[FATTI][API_NEWS] topic={topic} country={country} location={location}", flush=True)

    async with httpx.AsyncClient(timeout=12.0) as client:
        try:
            articles = []

            # STRATEGIA 1: Se c'è una località specifica → usa search endpoint
            if location:
                search_params = {
                    "apikey": api_key,
                    "q": location,
                    "lang": lang,
                    "max": 5,
                    "sortby": "publishedAt",
                }
                resp = await client.get("https://gnews.io/api/v4/search", params=search_params)
                data = resp.json()
                print(f"[FATTI][API_NEWS] search '{location}': status={resp.status_code} count={len(data.get('articles', []))}", flush=True)

                for art in data.get("articles", [])[:5]:
                    articles.append({
                        "title": art.get("title", ""),
                        "description": art.get("description", ""),
                        "source": art.get("source", {}).get("name", ""),
                        "published": art.get("publishedAt", ""),
                    })

                # Se la ricerca locale non trova nulla → fallback a top-headlines
                if not articles:
                    print(f"[FATTI][API_NEWS] search vuota per '{location}', fallback a top-headlines", flush=True)

            # STRATEGIA 2: Top headlines (default o fallback)
            if not articles:
                params = {
                    "apikey": api_key,
                    "lang": lang,
                    "max": 5,
                    "topic": topic,
                }
                if country:
                    params["country"] = country

                resp = await client.get("https://gnews.io/api/v4/top-headlines", params=params)
                data = resp.json()
                print(f"[FATTI][API_NEWS] headlines: status={resp.status_code} count={len(data.get('articles', []))}", flush=True)

                for art in data.get("articles", [])[:5]:
                    articles.append({
                        "title": art.get("title", ""),
                        "description": art.get("description", ""),
                        "source": art.get("source", {}).get("name", ""),
                        "published": art.get("publishedAt", ""),
                    })

            print(f"[FATTI][API_NEWS] ✓ {len(articles)} articoli trovati", flush=True)
            return {
                "source": "gnews",
                "topic": topic,
                "location": location,
                "timestamp": datetime.now().isoformat(),
                "articles": articles
            }

        except Exception as e:
            print(f"[FATTI][API_NEWS] ❌ errore: {e}", flush=True)
            return {"error": str(e), "source": "gnews"}


# ===============================
# 3. ECONOMIA — dati pubblici
# ===============================

async def fetch_economy(user_message: str) -> Dict:
    """Recupera dati economici da fonti pubbliche."""
    print(f"[FATTI][API_ECONOMY] richiesta economia", flush=True)

    results = {}

    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            # ECB Exchange rates (EUR/USD, EUR/GBP)
            ecb_url = "https://data-api.ecb.europa.eu/service/data/EXR/D.USD+GBP.EUR.SP00.A?lastNObservations=1&format=jsondata"
            ecb_resp = await client.get(ecb_url, headers={"Accept": "application/json"})
            if ecb_resp.status_code == 200:
                ecb_data = ecb_resp.json()
                datasets = ecb_data.get("dataSets", [{}])
                if datasets:
                    series = datasets[0].get("series", {})
                    rates = {}
                    for key, val in series.items():
                        obs = val.get("observations", {})
                        if obs:
                            last_val = list(obs.values())[-1][0]
                            if "0" in key:
                                rates["EUR/USD"] = last_val
                            else:
                                rates["EUR/GBP"] = last_val
                    results["exchange_rates"] = rates
                    print(f"[FATTI][API_ECONOMY] ✓ ECB rates: {rates}", flush=True)
        except Exception as e:
            print(f"[FATTI][API_ECONOMY] ⚠ ECB error: {e}", flush=True)

        try:
            # World Bank — Italy GDP growth (most recent)
            wb_url = "https://api.worldbank.org/v2/country/IT/indicator/NY.GDP.MKTP.KD.ZG?format=json&per_page=3&mrv=3"
            wb_resp = await client.get(wb_url)
            if wb_resp.status_code == 200:
                wb_data = wb_resp.json()
                if len(wb_data) > 1 and wb_data[1]:
                    gdp_entries = []
                    for entry in wb_data[1]:
                        if entry.get("value") is not None:
                            gdp_entries.append({
                                "year": entry["date"],
                                "gdp_growth_pct": round(entry["value"], 2)
                            })
                    results["italy_gdp_growth"] = gdp_entries
                    print(f"[FATTI][API_ECONOMY] ✓ World Bank GDP: {gdp_entries}", flush=True)
        except Exception as e:
            print(f"[FATTI][API_ECONOMY] ⚠ World Bank error: {e}", flush=True)

        try:
            # Eurostat — Italy unemployment rate
            eurostat_url = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/une_rt_m?geo=IT&unit=PC_ACT&s_adj=SA&age=TOTAL&sex=T&lastTimePeriod=3&format=JSON"
            es_resp = await client.get(eurostat_url)
            if es_resp.status_code == 200:
                es_data = es_resp.json()
                values = es_data.get("value", {})
                dimensions = es_data.get("dimension", {}).get("time", {}).get("category", {}).get("index", {})
                unemployment = []
                for period, idx in sorted(dimensions.items(), key=lambda x: x[1]):
                    val = values.get(str(idx))
                    if val is not None:
                        unemployment.append({"period": period, "rate_pct": val})
                results["italy_unemployment"] = unemployment
                print(f"[FATTI][API_ECONOMY] ✓ Eurostat unemployment: {unemployment}", flush=True)
        except Exception as e:
            print(f"[FATTI][API_ECONOMY] ⚠ Eurostat error: {e}", flush=True)

    # Se anche le news economiche possono aiutare, aggiungiamo
    news_data = await fetch_news("economia italiana borsa mercati")
    if news_data.get("articles"):
        results["economic_news"] = news_data["articles"][:3]

    results["source"] = "ecb+worldbank+eurostat"
    results["timestamp"] = datetime.now().isoformat()
    print(f"[FATTI][API_ECONOMY] ✓ dati raccolti: {list(results.keys())}", flush=True)
    return results


# ===============================
# 4. MEDICO — fonti istituzionali
# ===============================

async def fetch_medical_info(user_message: str) -> Dict:
    """Cerca informazioni mediche da fonti istituzionali (WHO, NHS)."""
    print(f"[FATTI][API_MEDICAL] richiesta medica", flush=True)

    # Estrai sintomi/termini dal messaggio
    msg_lower = user_message.lower()

    results = {"source": "who+nhs", "timestamp": datetime.now().isoformat()}

    _WIKI_HEADERS = {
        "User-Agent": "Genesi/1.0 (https://github.com/aturrisi-2/genesi; genesi@info.it) httpx/0.27"
    }

    search_terms = _extract_medical_terms(msg_lower)

    async with httpx.AsyncClient(timeout=15.0, headers=_WIKI_HEADERS) as client:
        try:
            wiki_results = []

            for term in search_terms[:2]:
                wiki_url = "https://it.wikipedia.org/api/rest_v1/page/summary/" + term
                resp = await client.get(wiki_url)
                if resp.status_code == 200:
                    data = resp.json()
                    wiki_results.append({
                        "title": data.get("title", ""),
                        "extract": data.get("extract", "")[:500],
                        "source": "Wikipedia (fonti mediche verificate)"
                    })
                    print(f"[FATTI][API_MEDICAL] ✓ Wikipedia: {data.get('title', '')}", flush=True)
                else:
                    print(f"[FATTI][API_MEDICAL] ⚠ Wikipedia {term}: status {resp.status_code}", flush=True)

            if wiki_results:
                results["medical_info"] = wiki_results

        except Exception as e:
            print(f"[FATTI][API_MEDICAL] ⚠ errore Wikipedia: {e}", flush=True)

    results["disclaimer"] = "Queste informazioni sono a scopo informativo. Per una diagnosi accurata, consultare un medico."
    return results


def _extract_medical_terms(text: str) -> List[str]:
    """Estrae termini medici dal messaggio per la ricerca."""
    medical_map = {
        "dolore al petto": ["Dolore_toracico"],
        "dolore toracico": ["Dolore_toracico"],
        "mal di testa": ["Cefalea"],
        "cefalea": ["Cefalea"],
        "febbre": ["Febbre"],
        "tosse": ["Tosse"],
        "nausea": ["Nausea"],
        "vertigini": ["Vertigine"],
        "pressione alta": ["Ipertensione"],
        "ipertensione": ["Ipertensione"],
        "diabete": ["Diabete_mellito"],
        "ansia": ["Disturbo_d'ansia"],
        "depressione": ["Disturbo_depressivo"],
        "mal di stomaco": ["Dispepsia"],
        "diarrea": ["Diarrea"],
        "allergia": ["Allergia"],
        "asma": ["Asma"],
        "influenza": ["Influenza"],
        "raffreddore": ["Raffreddore"],
        "dolore alla schiena": ["Lombalgia"],
        "tachicardia": ["Tachicardia"],
        "respiro": ["Dispnea"],
        "difficoltà a respirare": ["Dispnea"],
    }

    terms = []
    for symptom, wiki_terms in medical_map.items():
        if symptom in text:
            terms.extend(wiki_terms)

    if not terms:
        # Fallback: usa le parole chiave più rilevanti
        words = text.split()
        medical_words = [w for w in words if len(w) > 4 and w not in ("quando", "come", "perché", "sempre", "molto")]
        if medical_words:
            terms = [medical_words[0].capitalize()]

    return terms


# ===============================
# DISPATCHER — sceglie quale tool usare
# ===============================

_WEATHER_SIGNALS = [
    "meteo", "tempo fa", "temperatura", "previsioni", "piove", "pioverà",
    "gradi", "caldo", "freddo", "neve", "vento", "umidità", "temporale",
    "sole", "nuvoloso", "pioggia",
]

_NEWS_SIGNALS = [
    "notizie", "notizia", "news", "cronaca", "attualità",
    "successo oggi", "successo ieri", "cosa è successo", "cos'è successo",
    "cosa sta succedendo", "cosa succede", "ultime ore", "ultima ora",
    "degno di nota",
]

_ECONOMY_SIGNALS = [
    "economia", "economica", "economico", "inflazione", "pil", "spread",
    "borsa", "azioni", "mercato", "mercati", "tasso", "tassi",
    "debito pubblico", "disoccupazione", "occupazione",
]

_MEDICAL_SIGNALS = [
    "dolore", "sintomo", "sintomi", "farmaco", "farmaci", "medicina",
    "febbre", "mal di testa", "mal di stomaco", "pressione",
    "tosse", "raffreddore", "influenza", "allergia", "nausea",
    "vertigini", "tachicardia", "respiro", "diagnosi",
    "antibiotico", "paracetamolo", "ibuprofene", "dose", "dosaggio",
]


async def resolve_tools(user_message: str) -> Optional[Dict]:
    """
    Analizza il messaggio e chiama le API appropriate.
    Restituisce i dati grezzi da passare a GPT-4o-mini per la sintesi.
    Restituisce None se nessun tool è necessario (domanda tecnica/generica).
    """
    msg_lower = user_message.lower()

    # Determina quale tool usare
    tool_type = None
    tool_data = None

    if any(s in msg_lower for s in _WEATHER_SIGNALS):
        tool_type = "meteo"
        tool_data = await fetch_weather(user_message)

    elif any(s in msg_lower for s in _MEDICAL_SIGNALS):
        tool_type = "medical"
        tool_data = await fetch_medical_info(user_message)

    elif any(s in msg_lower for s in _ECONOMY_SIGNALS):
        tool_type = "economy"
        tool_data = await fetch_economy(user_message)

    elif any(s in msg_lower for s in _NEWS_SIGNALS):
        tool_type = "news"
        tool_data = await fetch_news(user_message)

    if tool_type and tool_data:
        print(f"[FATTI][TOOL_RESOLVED] type={tool_type}", flush=True)
        return {
            "tool_type": tool_type,
            "data": tool_data
        }

    # Nessun tool necessario — domanda tecnica/generica → solo LLM
    print(f"[FATTI][TOOL_RESOLVED] type=none (solo LLM)", flush=True)
    return None
