"""
APGIA Pipeline — Sync activities from Garmin Connect via garminconnect
Usage:
  # First time: authenticate
  python -m pipeline.sync_garmin --login

  # Sync recent activities (default: last 30 days)
  python -m pipeline.sync_garmin --days 30

  # Sync specific date range
  python -m pipeline.sync_garmin --from 2025-01-01 --to 2025-12-31

Requires: pip install garminconnect fitparse
Session tokens are cached in ~/.garmin/ after first login.
"""
import argparse
import json
import sys
import tempfile
from datetime import datetime, date, timedelta
from pathlib import Path

from garminconnect import Garmin, GarminConnectAuthenticationError

from .config import get_client, SCHEMA
from .ingest_garmin import parse_fit

TOKEN_DIR = Path.home() / ".garmin"
TOKEN_FILE = TOKEN_DIR / "session.json"

# Garmin activity type IDs (cycling = 2)
CYCLING_TYPE_ID = 2


def save_session(api: Garmin):
    """Save session tokens for reuse."""
    TOKEN_DIR.mkdir(exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(api.session_data))


def login():
    """Interactive login to Garmin Connect. Saves session for future use."""
    email = input("Garmin email: ").strip()
    password = input("Garmin password: ").strip()

    try:
        api = Garmin(email, password)
        api.login()
        save_session(api)
        print(f"✓ Login OK. Session saved to {TOKEN_FILE}")
        print("  Next runs will use saved session automatically.")
    except GarminConnectAuthenticationError as e:
        print(f"✗ Authentication failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"✗ Login failed: {e}")
        sys.exit(1)


def get_api() -> Garmin:
    """Resume saved session or fail with instructions."""
    if not TOKEN_FILE.exists():
        print("⚠ No saved session. Run: python -m pipeline.sync_garmin --login")
        sys.exit(1)

    try:
        session_data = json.loads(TOKEN_FILE.read_text())
        api = Garmin()
        api.login(session_data)
        # Refresh & save updated tokens
        save_session(api)
        return api
    except GarminConnectAuthenticationError:
        print("⚠ Session expired. Run: python -m pipeline.sync_garmin --login")
        sys.exit(1)
    except Exception as e:
        print(f"⚠ Session error: {e}")
        print("  Try: python -m pipeline.sync_garmin --login")
        sys.exit(1)


def sync(days: int = 30, start_date: str = None, end_date: str = None,
         activity_type: str = "cycling", fetch_weather: bool = True,
         verbose: bool = True):
    """Sync recent Garmin activities to Supabase."""

    api = get_api()

    # Date range
    if start_date:
        d_start = date.fromisoformat(start_date)
    else:
        d_start = date.today() - timedelta(days=days)

    d_end = date.fromisoformat(end_date) if end_date else date.today()

    if verbose:
        print(f"Fetching activities from {d_start} to {d_end}...")

    # Fetch activity list
    try:
        activities = api.get_activities_by_date(
            d_start.isoformat(), d_end.isoformat(),
            activitytype=activity_type if activity_type != "all" else None
        )
    except Exception as e:
        print(f"✗ Failed to fetch activities: {e}")
        return

    if not activities:
        print("  No activities found in date range.")
        return

    if verbose:
        print(f"  Found {len(activities)} activities")

    # Get existing timestamps to avoid duplicates
    sb = get_client()
    existing = sb.schema(SCHEMA).table("cycling_sessions") \
        .select("timestamp") \
        .gte("date", d_start.isoformat()) \
        .lte("date", d_end.isoformat()) \
        .execute()
    existing_ts = set()
    for r in existing.data:
        ts = r.get("timestamp", "")
        if ts:
            existing_ts.add(ts[:19])

    inserted = 0
    skipped = 0
    errors = 0

    for act in activities:
        act_id = act.get("activityId")
        act_name = act.get("activityName", "?")
        act_start = act.get("startTimeLocal", "")

        # Check if already exists
        ts_check = act_start[:19] if act_start else ""
        if ts_check in existing_ts:
            skipped += 1
            if verbose:
                print(f"  ⊘ {act_name} ({act_start[:10]}) — already exists")
            continue

        # Download .fit file and parse
        try:
            fit_bytes = api.download_activity(
                act_id,
                dl_fmt=Garmin.ActivityDownloadFormat.ORIGINAL
            )

            # garminconnect returns a zip for ORIGINAL format
            # Extract the .fit file from the zip
            import zipfile
            import io

            tmp_path = None
            with zipfile.ZipFile(io.BytesIO(fit_bytes)) as zf:
                fit_files = [f for f in zf.namelist() if f.endswith('.fit')]
                if fit_files:
                    with tempfile.NamedTemporaryFile(suffix=".fit", delete=False) as tmp:
                        tmp.write(zf.read(fit_files[0]))
                        tmp_path = tmp.name

            if not tmp_path:
                # Fallback: try treating the response as raw .fit
                with tempfile.NamedTemporaryFile(suffix=".fit", delete=False) as tmp:
                    tmp.write(fit_bytes)
                    tmp_path = tmp.name

            data = parse_fit(tmp_path)

            if not data.get("timestamp"):
                data["timestamp"] = act_start

            if data.get("timestamp"):
                data["date"] = data["timestamp"][:10]

            # Extract lat/lon from activity summary if available
            if act.get("startLatitude") and act.get("startLongitude"):
                data["lat"] = round(act["startLatitude"], 6)
                data["lon"] = round(act["startLongitude"], 6)

            # Fetch weather from Garmin if requested
            if fetch_weather and act_id:
                try:
                    weather = api.get_activity_weather(act_id)
                    if weather:
                        w_temp = weather.get("temp")
                        w_cond = weather.get("weatherTypeDTO", {}).get("desc")
                        w_humidity = weather.get("relativeHumidity")
                        w_wind = weather.get("windSpeed")
                        w_wind_dir = weather.get("windDirection", {}).get("desc") if isinstance(weather.get("windDirection"), dict) else None

                        if w_temp is not None:
                            data["weather_temp_c"] = round(w_temp, 1)
                        if w_humidity is not None:
                            data["weather_humidity_pct"] = round(w_humidity, 1)
                        if w_wind is not None:
                            data["weather_wind_speed_kmh"] = round(w_wind, 1)
                        if w_cond:
                            data["weather_condition"] = w_cond.lower().replace(" ", "_")
                except Exception:
                    pass  # Weather is optional, don't fail the sync

            # Insert into DB
            result = sb.schema(SCHEMA).table("cycling_sessions").insert(data).execute()
            inserted += 1

            if verbose:
                dur = data.get("duration_min", 0) or 0
                pwr = data.get("avg_power", "?")
                tss = data.get("training_stress_score", "?")
                print(f"  ✓ {act_name} ({data.get('date', '?')}): "
                      f"{dur:.0f}min, avg {pwr}W, TSS={tss}")

            # Cleanup temp file
            if tmp_path:
                Path(tmp_path).unlink(missing_ok=True)

        except Exception as e:
            errors += 1
            if verbose:
                print(f"  ✗ {act_name} ({act_start[:10]}): {e}")

    if verbose:
        print(f"\n  Done: {inserted} inserted, {skipped} duplicates, {errors} errors")
        if inserted > 0:
            print(f"  PMC auto-recalculated via trigger.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sync Garmin Connect activities → APGIA/Supabase"
    )
    parser.add_argument("--login", action="store_true",
                        help="Authenticate with Garmin Connect")
    parser.add_argument("--days", type=int, default=30,
                        help="Sync last N days (default: 30)")
    parser.add_argument("--from", dest="start_date",
                        help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to", dest="end_date",
                        help="End date (YYYY-MM-DD)")
    parser.add_argument("--type", dest="activity_type", default="cycling",
                        help="Activity type filter (default: cycling)")
    parser.add_argument("--all-types", action="store_true",
                        help="Fetch all activity types")
    parser.add_argument("--no-weather", action="store_true",
                        help="Skip fetching weather from Garmin")
    args = parser.parse_args()

    if args.login:
        login()
    else:
        atype = "all" if args.all_types else args.activity_type
        sync(
            days=args.days,
            start_date=args.start_date,
            end_date=args.end_date,
            activity_type=atype,
            fetch_weather=not args.no_weather,
        )
