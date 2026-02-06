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
    return os.getenv("OPENWEATHER_API_KEY")

def _get_newsapi_key() -> Optional[str]:
    return os.getenv("NEWSAPI_KEY")


# ===============================
# CITY EXTRACTION
# ===============================

_CITY_PATTERN = re.compile(
    r"\b(?:a|di|su|per|in)\s+([A-ZÀ-Ú][a-zà-ú]+(?:\s+[A-ZÀ-Ú][a-zà-ú]+)*)",
    re.UNICODE
)

_ITALIAN_CITIES = {
    "roma", "milano", "napoli", "torino", "palermo", "genova", "bologna",
    "firenze", "bari", "catania", "venezia", "verona", "messina", "padova",
    "trieste", "brescia", "parma", "modena", "reggio calabria", "reggio emilia",
    "perugia", "cagliari", "livorno", "foggia", "rimini", "salerno", "ferrara",
    "sassari", "siracusa", "pescara", "monza", "bergamo", "trento", "vicenza",
    "terni", "novara", "piacenza", "ancona", "lecce", "bolzano", "catanzaro",
    "udine", "aosta", "potenza", "campobasso", "l'aquila",
}

def extract_city(text: str) -> str:
    """Estrae la città dal messaggio. Default: Roma."""
    match = _CITY_PATTERN.search(text)
    if match:
        city = match.group(1).strip()
        if city.lower() in _ITALIAN_CITIES:
            return city
        return city
    # Cerca menzione diretta di città italiane
    text_lower = text.lower()
    for city in _ITALIAN_CITIES:
        if city in text_lower:
            return city.title()
    return "Roma"


# ===============================
# 1. METEO — OpenWeatherMap
# ===============================

async def fetch_weather(user_message: str) -> Dict:
    """Chiama OpenWeatherMap e restituisce dati meteo reali."""
    api_key = _get_openweather_key()
    if not api_key:
        print("[FATTI][API_METEO] ❌ OPENWEATHER_API_KEY non configurata", flush=True)
        return {"error": "API meteo non configurata", "source": "openweathermap"}

    city = extract_city(user_message)
    print(f"[FATTI][API_METEO] città={city}", flush=True)

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # Current weather
            current_url = "https://api.openweathermap.org/data/2.5/weather"
            current_resp = await client.get(current_url, params={
                "q": city + ",IT",
                "appid": api_key,
                "units": "metric",
                "lang": "it"
            })
            current_data = current_resp.json()

            if current_resp.status_code != 200:
                # Riprova senza ,IT per città estere
                current_resp = await client.get(current_url, params={
                    "q": city,
                    "appid": api_key,
                    "units": "metric",
                    "lang": "it"
                })
                current_data = current_resp.json()

            # 5-day forecast
            forecast_url = "https://api.openweathermap.org/data/2.5/forecast"
            forecast_resp = await client.get(forecast_url, params={
                "q": city + ",IT",
                "appid": api_key,
                "units": "metric",
                "lang": "it",
                "cnt": 16  # ~48h di previsioni (ogni 3h)
            })
            forecast_data = forecast_resp.json()

            if forecast_resp.status_code != 200:
                forecast_resp = await client.get(forecast_url, params={
                    "q": city,
                    "appid": api_key,
                    "units": "metric",
                    "lang": "it",
                    "cnt": 16
                })
                forecast_data = forecast_resp.json()

            result = {
                "source": "openweathermap",
                "city": city,
                "timestamp": datetime.now().isoformat(),
                "current": {},
                "forecast": []
            }

            # Parse current
            if "main" in current_data:
                result["current"] = {
                    "temp": current_data["main"]["temp"],
                    "feels_like": current_data["main"]["feels_like"],
                    "temp_min": current_data["main"]["temp_min"],
                    "temp_max": current_data["main"]["temp_max"],
                    "humidity": current_data["main"]["humidity"],
                    "description": current_data.get("weather", [{}])[0].get("description", ""),
                    "wind_speed": current_data.get("wind", {}).get("speed", 0),
                }
                print(f"[FATTI][API_METEO] ✓ current: {result['current']['temp']}°C, {result['current']['description']}", flush=True)

            # Parse forecast
            if "list" in forecast_data:
                for item in forecast_data["list"]:
                    result["forecast"].append({
                        "datetime": item.get("dt_txt", ""),
                        "temp": item["main"]["temp"],
                        "temp_min": item["main"]["temp_min"],
                        "temp_max": item["main"]["temp_max"],
                        "description": item.get("weather", [{}])[0].get("description", ""),
                        "humidity": item["main"]["humidity"],
                        "wind_speed": item.get("wind", {}).get("speed", 0),
                    })
                print(f"[FATTI][API_METEO] ✓ forecast: {len(result['forecast'])} entries", flush=True)

            return result

        except Exception as e:
            print(f"[FATTI][API_METEO] ❌ errore: {e}", flush=True)
            return {"error": str(e), "source": "openweathermap"}


# ===============================
# 2. NEWS — GNews API
# ===============================

async def fetch_news(user_message: str) -> Dict:
    """Chiama GNews API per notizie aggiornate."""
    api_key = _get_newsapi_key()
    if not api_key:
        print("[FATTI][API_NEWS] ❌ NEWSAPI_KEY non configurata", flush=True)
        return {"error": "API news non configurata", "source": "gnews"}

    # Determina topic dal messaggio
    msg_lower = user_message.lower()
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

    # Determina se cerca notizie italiane o europee
    lang = "it"
    country = "it"
    if any(w in msg_lower for w in ["europa", "europee", "europeo", "mondo", "mondiale", "internazional"]):
        country = ""  # Non filtrare per paese

    print(f"[FATTI][API_NEWS] topic={topic} country={country}", flush=True)

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            # GNews API
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

            articles = []
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
