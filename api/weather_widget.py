import os
from datetime import datetime, timezone as dt_timezone

import httpx
from fastapi import APIRouter, Query, HTTPException, Depends
from fastapi.responses import JSONResponse
from typing import Optional
from auth.router import require_auth
from auth.models import AuthUser
from core.storage import storage
from core.models.profile_model import UserProfile
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/weather-widget", tags=["weather-widget"])

OPENWEATHER_BASE = "https://api.openweathermap.org/data/2.5/weather"
OPENWEATHER_GEO  = "https://api.openweathermap.org/geo/1.0/reverse"
IPAPI_FALLBACK   = "http://ip-api.com/json"

TIMEOUT_SECONDS = 8


def _no_cache_headers() -> dict[str, str]:
    """Prevent browser/proxy caches from serving stale weather payloads."""
    return {
        "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
        "Pragma": "no-cache",
        "Expires": "0",
    }


@router.get("")
async def get_weather_widget(
    lat: float | None = Query(None, description="Latitudine da Geolocation API"),
    lon: float | None = Query(None, description="Longitudine da Geolocation API"),
    tz: str | None = Query(None, description="Timezone passata dal client"),
    user: Optional[AuthUser] = Depends(require_auth)
):
    """
    Endpoint per il weather widget della homepage.
    - Se lat/lon forniti: usa coordinate dirette
    - Altrimenti: fallback IP-based tramite ip-api.com
    Restituisce JSON pulito e normalizzato, pronto per il frontend.
    """
    api_key = os.getenv("OPENWEATHER_API_KEY")
    if not api_key:
        logger.warning("WEATHER_WIDGET_DEMO_MODE: OPENWEATHER_API_KEY missing. Providing simulated data.")
        # Simulated payload for Siderno
        payload = {
            "city": "Siderno",
            "temp": 18,
            "feels_like": 17,
            "humidity": 65,
            "description": "Cielo parzialmente nuvoloso (Simulato)",
            "icon_code": "02d",
            "wind_speed": 12,
            "condition": "clouds"
        }
        payload["updated_at"] = datetime.now(dt_timezone.utc).isoformat()
        return JSONResponse(content=payload, headers=_no_cache_headers())
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:

            # ── 1. Risolvi coordinate e Timezone ─────────────────────────
            resolved_timezone = tz or "Europe/Rome"
            
            # Solo se tz non è fornito, proviamo a indovinare da IP
            if not tz:
                try:
                    ip_resp = await client.get(IPAPI_FALLBACK)
                    ip_data = ip_resp.json()
                    resolved_timezone = ip_data.get("timezone", "Europe/Rome")
                except Exception:
                    pass

            if lat is not None and lon is not None:
                resolved_lat, resolved_lon = lat, lon
                city_name = "—"
                # Reverse geocoding per nome città
                geo_resp = await client.get(
                    OPENWEATHER_GEO,
                    params={"lat": lat, "lon": lon, "limit": 1, "appid": api_key}
                )
                if geo_resp.status_code == 200:
                    geo_data = geo_resp.json()
                    if geo_data:
                        city_name = (
                            geo_data[0].get("local_names", {}).get("it")
                            or geo_data[0].get("name", "—")
                        )
            else:
                # Priorità ai GPS salvati nel profilo utente (più accurati dell'IP server).
                resolved_lat = None
                resolved_lon = None
                city_name = "—"

                if user:
                    profile_for_geo = await storage.load(f"profile:{user.id}", default={})
                    if isinstance(profile_for_geo, dict):
                        gps_lat = profile_for_geo.get("gps_lat")
                        gps_lon = profile_for_geo.get("gps_lon")
                        if gps_lat is not None and gps_lon is not None:
                            resolved_lat = gps_lat
                            resolved_lon = gps_lon
                            city_name = profile_for_geo.get("city") or "—"
                            logger.info(
                                f"WEATHER_WIDGET_GPS_PROFILE_USED user={user.id} city={city_name} "
                                f"lat={resolved_lat} lon={resolved_lon}"
                            )
                        elif profile_for_geo.get("city"):
                            city_name = profile_for_geo.get("city")

                # Se non abbiamo GPS salvati, fallback IP-based.
                if resolved_lat is None or resolved_lon is None:
                    if 'ip_data' not in locals():
                        ip_resp = await client.get(IPAPI_FALLBACK)
                        ip_data = ip_resp.json()

                    resolved_lat = ip_data.get("lat")
                    resolved_lon = ip_data.get("lon")
                    if city_name == "—":
                        city_name = ip_data.get("city", "—")

                    if resolved_lat is None or resolved_lon is None:
                        raise ValueError("Impossibile determinare posizione da IP")
            
            # ── 1.5 Salva Posizione nel Profilo ───────────────────────────
            if user:
                user_id = user.id
                raw_profile = await storage.load(f"profile:{user_id}", default={})
                if not isinstance(raw_profile, dict):
                    raw_profile = {}

                profile_updated = False
                # Aggiorna city SOLO se non è già stata impostata dall'utente.
                # Il widget meteo usa GPS/IP che può puntare a una città diversa
                # rispetto a quella dichiarata dall'utente (es. Roma vs Imola).
                if city_name != "—" and not raw_profile.get("city"):
                    raw_profile["city"] = city_name
                    profile_updated = True
                    logger.info(f"PROFILE_CITY_SET_FROM_GPS user={user_id} city={city_name}")
                elif city_name != "—" and raw_profile.get("city") != city_name:
                    logger.info(f"PROFILE_CITY_GPS_SKIP user={user_id} existing={raw_profile.get('city')} gps={city_name}")

                # Salva coordinate GPS per meteo locale ("che tempo fa fuori?")
                if lat is not None and lon is not None:
                    if raw_profile.get("gps_lat") != lat or raw_profile.get("gps_lon") != lon:
                        raw_profile["gps_lat"] = lat
                        raw_profile["gps_lon"] = lon
                        profile_updated = True

                # Se abbiamo una timezone (da IP/client), salviamola
                current_tz = raw_profile.get("timezone", "Europe/Rome")
                new_tz = resolved_timezone if 'resolved_timezone' in locals() else current_tz

                if raw_profile.get("timezone") != new_tz:
                    raw_profile["timezone"] = new_tz
                    profile_updated = True

                if profile_updated:
                    await storage.save(f"profile:{user_id}", raw_profile)
                    logger.info(f"PROFILE_LOCATION_UPDATED user={user_id} city={city_name} tz={new_tz}")

            # ── 2. Dati meteo ──────────────────────────────────────────────
            weather_resp = await client.get(
                OPENWEATHER_BASE,
                params={
                    "lat"   : resolved_lat,
                    "lon"   : resolved_lon,
                    "appid" : api_key,
                    "units" : "metric",
                    "lang"  : "it",
                }
            )

            if weather_resp.status_code != 200:
                logger.error(
                    f"WEATHER_WIDGET_API_ERROR status={weather_resp.status_code}"
                )
                raise HTTPException(status_code=502, detail="weather_api_error")

            data = weather_resp.json()

            # ── 3. Payload normalizzato ────────────────────────────────────
            if city_name == "—":
                city_name = data.get("name", "—")

            payload = {
                "city"       : city_name,
                "temp"       : round(data["main"]["temp"]),
                "feels_like" : round(data["main"]["feels_like"]),
                "humidity"   : data["main"]["humidity"],
                "description": data["weather"][0]["description"].capitalize(),
                "icon_code"  : data["weather"][0]["icon"],
                "wind_speed" : round(data["wind"]["speed"] * 3.6),  # m/s → km/h
                "condition"  : data["weather"][0]["main"].lower(),  # clear/clouds/rain/...
                "updated_at" : datetime.now(dt_timezone.utc).isoformat(),
            }

            logger.info(
                f"WEATHER_WIDGET_OK city={payload['city']} "
                f"temp={payload['temp']} condition={payload['condition']}"
            )
            return JSONResponse(content=payload, headers=_no_cache_headers())

    except httpx.TimeoutException:
        logger.warning("WEATHER_WIDGET_TIMEOUT")
        return JSONResponse(
            status_code=504,
            content={"error": "timeout", "message": "Servizio meteo non risponde"},
            headers=_no_cache_headers(),
        )
    except Exception as e:
        logger.error(f"WEATHER_WIDGET_ERROR {type(e).__name__}: {e}")
        return JSONResponse(
            status_code=503,
            content={"error": "weather_unavailable", "message": "Servizio non disponibile"},
            headers=_no_cache_headers(),
        )
