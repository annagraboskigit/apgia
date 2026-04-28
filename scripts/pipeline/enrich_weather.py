"""
APGIA Pipeline — Enrich cycling_sessions with weather data from Open-Meteo
Usage:
  python -m pipeline.enrich_weather                    # enrich all rides missing weather
  python -m pipeline.enrich_weather --date 2025-06-15  # enrich specific date
  python -m pipeline.enrich_weather --backfill         # backfill all historical rides

Open-Meteo Archive API — free, no API key needed.
Uses ride timestamp + lat/lon (from .fit or default location) to fetch hourly weather.
"""
import argparse
import sys
import time
from datetime import datetime, timedelta
from urllib.request import urlopen
import json

from .config import get_client, SCHEMA

# Default coordinates — fallback if no lat/lon on ride
# Rio de Janeiro, RJ, Brazil
DEFAULT_LAT = -22.9068
DEFAULT_LON = -43.1729

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"

# WMO Weather interpretation codes → human condition
WMO_CODES = {
    0: "clear", 1: "clear", 2: "cloudy", 3: "overcast",
    45: "fog", 48: "fog",
    51: "drizzle", 53: "drizzle", 55: "drizzle",
    61: "rain", 63: "rain", 65: "heavy_rain",
    71: "snow", 73: "snow", 75: "heavy_snow",
    80: "rain_showers", 81: "rain_showers", 82: "heavy_rain",
    95: "storm", 96: "storm", 99: "storm",
}


def fetch_weather(lat: float, lon: float, date: str, hour: int = 10) -> dict:
    """Fetch hourly weather from Open-Meteo for a specific date and location.

    Args:
        lat, lon: coordinates
        date: YYYY-MM-DD
        hour: hour of day to sample (default 10 = morning ride)

    Returns:
        dict with weather fields or empty dict on error
    """
    params = (
        f"?latitude={lat}&longitude={lon}"
        f"&start_date={date}&end_date={date}"
        f"&hourly=temperature_2m,relative_humidity_2m,"
        f"wind_speed_10m,wind_gusts_10m,precipitation,weather_code"
        f"&timezone=America/Sao_Paulo"
    )

    url = OPEN_METEO_URL + params

    try:
        with urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"  ⚠ Weather API error for {date}: {e}")
        return {}

    hourly = data.get("hourly", {})
    times = hourly.get("time", [])

    if not times:
        return {}

    # Find the closest hour index
    target_idx = min(hour, len(times) - 1)

    # For rides, average over a window (e.g., 3 hours around the start)
    start_idx = max(0, target_idx - 1)
    end_idx = min(len(times), target_idx + 2)

    def avg(key):
        vals = [hourly[key][i] for i in range(start_idx, end_idx) if hourly[key][i] is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    def max_val(key):
        vals = [hourly[key][i] for i in range(start_idx, end_idx) if hourly[key][i] is not None]
        return round(max(vals), 1) if vals else None

    def total(key):
        vals = [hourly[key][i] for i in range(start_idx, end_idx) if hourly[key][i] is not None]
        return round(sum(vals), 1) if vals else None

    # Weather code at ride hour
    wcode = hourly.get("weather_code", [None] * len(times))[target_idx]
    condition = WMO_CODES.get(wcode, "unknown") if wcode is not None else None

    return {
        "weather_temp_c": avg("temperature_2m"),
        "weather_humidity_pct": avg("relative_humidity_2m"),
        "weather_wind_speed_kmh": avg("wind_speed_10m"),
        "weather_wind_gusts_kmh": max_val("wind_gusts_10m"),
        "weather_precip_mm": total("precipitation"),
        "weather_condition": condition,
    }


def get_ride_hour(timestamp_str: str) -> int:
    """Extract hour from ride timestamp."""
    try:
        dt = datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
        # Adjust to BRT (UTC-3) roughly
        dt_local = dt - timedelta(hours=3)
        return dt_local.hour
    except Exception:
        return 10  # default morning ride


def enrich_rides(specific_date: str = None, backfill: bool = False, verbose: bool = True):
    """Enrich cycling_sessions with weather data."""
    sb = get_client()

    # Fetch rides needing weather
    query = sb.schema(SCHEMA).table("cycling_sessions") \
        .select("id, date, timestamp, lat, lon")

    if specific_date:
        query = query.eq("date", specific_date)
    elif not backfill:
        query = query.is_("weather_temp_c", "null")

    result = query.order("date", desc=True).execute()
    rides = result.data

    if not rides:
        print("  No rides to enrich.")
        return

    if verbose:
        print(f"  Enriching {len(rides)} rides with weather data...")

    enriched = 0
    errors = 0

    for ride in rides:
        ride_date = ride.get("date")
        ride_ts = ride.get("timestamp", "")
        lat = ride.get("lat") or DEFAULT_LAT
        lon = ride.get("lon") or DEFAULT_LON
        hour = get_ride_hour(ride_ts) if ride_ts else 10

        weather = fetch_weather(lat, lon, ride_date, hour)

        if not weather:
            errors += 1
            continue

        # Update ride
        try:
            sb.schema(SCHEMA).table("cycling_sessions") \
                .update(weather) \
                .eq("id", ride["id"]) \
                .execute()
            enriched += 1

            if verbose:
                cond = weather.get("weather_condition", "?")
                temp = weather.get("weather_temp_c", "?")
                wind = weather.get("weather_wind_speed_kmh", "?")
                print(f"  ✓ {ride_date}: {temp}°C, {cond}, vento {wind}km/h")
        except Exception as e:
            errors += 1
            if verbose:
                print(f"  ✗ {ride_date}: {e}")

        # Rate limit: Open-Meteo allows ~600 req/min, be gentle
        time.sleep(0.15)

    if verbose:
        print(f"\n  Done: {enriched} enriched, {errors} errors")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Enrich cycling sessions with Open-Meteo weather data"
    )
    parser.add_argument("--date", help="Enrich specific date (YYYY-MM-DD)")
    parser.add_argument("--backfill", action="store_true",
                        help="Backfill all rides (even those with weather)")
    parser.add_argument("--lat", type=float, help="Override default latitude")
    parser.add_argument("--lon", type=float, help="Override default longitude")
    args = parser.parse_args()

    if args.lat:
        DEFAULT_LAT = args.lat
    if args.lon:
        DEFAULT_LON = args.lon

    enrich_rides(specific_date=args.date, backfill=args.backfill)
