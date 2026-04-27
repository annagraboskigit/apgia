"""
APGIA Pipeline — Sync activities from Garmin Connect via garth
Usage:
  # First time: authenticate
  python -m pipeline.sync_garmin --login

  # Sync recent activities (default: last 30 days)
  python -m pipeline.sync_garmin --days 30

  # Sync specific date range
  python -m pipeline.sync_garmin --from 2025-01-01 --to 2025-12-31

Requires: pip install garth fitparse
Tokens are cached in ~/.garth/ after first login.
"""
import argparse
import json
import sys
import tempfile
from datetime import datetime, date, timedelta, timezone
from pathlib import Path

import garth

from .config import get_client, SCHEMA
from .ingest_garmin import parse_fit

# Garmin Connect API endpoints
ACTIVITIES_URL = "/activitylist-service/activities/search/activities"
FIT_DOWNLOAD_URL = "/download-service/files/activity/{id}"

TOKEN_DIR = Path.home() / ".garth"


def login():
    """Interactive login to Garmin Connect. Saves tokens for future use."""
    email = input("Garmin email: ").strip()
    password = input("Garmin password: ").strip()

    try:
        garth.login(email, password)
        garth.save(str(TOKEN_DIR))
        print(f"✓ Login OK. Tokens saved to {TOKEN_DIR}")
        print("  Next runs will use saved tokens automatically.")
    except Exception as e:
        print(f"✗ Login failed: {e}")
        sys.exit(1)


def ensure_session():
    """Resume saved session or prompt for login."""
    try:
        garth.resume(str(TOKEN_DIR))
        # Test the session with a simple call
        garth.connectapi("/userprofile-service/usersettings")
        return True
    except Exception:
        print("⚠ No valid session. Run: python -m pipeline.sync_garmin --login")
        return False


def fetch_activities(start_date: date, end_date: date, activity_type: str = "cycling") -> list:
    """Fetch activity list from Garmin Connect."""
    activities = []
    batch_size = 20
    offset = 0

    while True:
        params = {
            "start": offset,
            "limit": batch_size,
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
        }
        if activity_type:
            params["activityType"] = activity_type

        batch = garth.connectapi(ACTIVITIES_URL, params=params)

        if not batch:
            break

        activities.extend(batch)
        offset += batch_size

        if len(batch) < batch_size:
            break

    return activities


def download_fit(activity_id: int) -> bytes:
    """Download .fit file for an activity."""
    url = FIT_DOWNLOAD_URL.format(id=activity_id)
    response = garth.download(url)
    return response


def sync(days: int = 30, start_date: str = None, end_date: str = None,
         activity_type: str = "cycling", verbose: bool = True):
    """Sync recent Garmin activities to Supabase."""

    if not ensure_session():
        return

    # Date range
    if start_date:
        d_start = date.fromisoformat(start_date)
    else:
        d_start = date.today() - timedelta(days=days)

    d_end = date.fromisoformat(end_date) if end_date else date.today()

    if verbose:
        print(f"Fetching activities from {d_start} to {d_end}...")

    # Fetch activity list
    activities = fetch_activities(d_start, d_end, activity_type)

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
            # Normalize: strip microseconds for comparison
            existing_ts.add(ts[:19])

    inserted = 0
    skipped = 0
    errors = 0

    for act in activities:
        act_id = act.get("activityId")
        act_name = act.get("activityName", "?")
        act_start = act.get("startTimeLocal", "")

        # Check if already exists (compare first 19 chars of timestamp)
        ts_check = act_start[:19] if act_start else ""
        if ts_check in existing_ts:
            skipped += 1
            if verbose:
                print(f"  ⊘ {act_name} ({act_start[:10]}) — already exists")
            continue

        # Download .fit file
        try:
            fit_bytes = download_fit(act_id)

            # Write to temp file and parse
            with tempfile.NamedTemporaryFile(suffix=".fit", delete=False) as tmp:
                tmp.write(fit_bytes)
                tmp_path = tmp.name

            data = parse_fit(tmp_path)

            if not data.get("timestamp"):
                # Fallback: use activity start time from API
                data["timestamp"] = act_start

            # Add date field
            if data.get("timestamp"):
                data["date"] = data["timestamp"][:10]

            # Insert into DB
            result = sb.schema(SCHEMA).table("cycling_sessions").insert(data).execute()
            inserted += 1

            if verbose:
                print(f"  ✓ {act_name} ({data.get('date', '?')}): "
                      f"{data.get('duration_min', '?'):.0f}min, "
                      f"avg {data.get('avg_power', '?')}W, "
                      f"TSS={data.get('training_stress_score', '?')}")

            # Cleanup temp file
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
    args = parser.parse_args()

    if args.login:
        login()
    else:
        atype = None if args.all_types else args.activity_type
        sync(
            days=args.days,
            start_date=args.start_date,
            end_date=args.end_date,
            activity_type=atype,
        )
