import sys
import os
import asyncio

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

async def _get_quick_weather_summary(city_name: str) -> str:
    import httpx
    OPENWEATHER_API_KEY = os.environ.get("OPENWEATHER_API_KEY", "")
    if not OPENWEATHER_API_KEY:
        return "Key non trovata"
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            # 1. Geocoding
            geo_url = "https://api.openweathermap.org/geo/1.0/direct"
            q_query = f"{city_name},IT"
            geo_params = {"q": q_query, "limit": 3, "appid": OPENWEATHER_API_KEY}
            geo_resp = await client.get(geo_url, params=geo_params)
            if geo_resp.status_code != 200:
                return f"{city_name}: Errore geocoding"
            geo_data = geo_resp.json()
            if not geo_data:
                # Prova senza ",IT" in caso di frazioni particolari
                geo_params["q"] = city_name
                geo_resp = await client.get(geo_url, params=geo_params)
                if geo_resp.status_code != 200 or not geo_resp.json():
                    return f"{city_name}: Non trovata"
                geo_data = geo_resp.json()
            
            geo = geo_data[0]
            lat, lon = geo["lat"], geo["lon"]
            resolved_name = geo.get("name", city_name)
            state = geo.get("state", "")
            
            # 2. Weather
            weather_url = "https://api.openweathermap.org/data/2.5/weather"
            weather_params = {
                "lat": lat,
                "lon": lon,
                "appid": OPENWEATHER_API_KEY,
                "units": "metric",
                "lang": "it"
            }
            w_resp = await client.get(weather_url, params=weather_params)
            if w_resp.status_code != 200:
                return f"{city_name}: Errore meteo"
            
            w_data = w_resp.json()
            temp = round(w_data.get("main", {}).get("temp", 0))
            desc = w_data.get("weather", [{}])[0].get("description", "").capitalize()
            return f"{city_name} ({resolved_name}, {state}): {desc}, {temp}°C"
    except Exception as e:
        return f"{city_name}: Eccezione: {e}"

async def test_weather():
    cities = [
        "Motta Sant'Anastasia",
        "Bracciano",
        "Lentini",
        "Imola",
        "Franchetto"
    ]
    print("=== TEST METEO DIRETTO ===")
    tasks = [_get_quick_weather_summary(c) for c in cities]
    results = await asyncio.gather(*tasks)
    for r in results:
        print(r)

if __name__ == "__main__":
    asyncio.run(test_weather())
