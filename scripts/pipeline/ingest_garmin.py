"""
APGIA Pipeline — Ingest Garmin .fit files into Supabase
Usage:
  python -m pipeline.ingest_garmin --fit-dir /path/to/fit/files/
  python -m pipeline.ingest_garmin --fit /path/to/single/file.fit
  python -m pipeline.ingest_garmin --quick 90 180 150 45  (dur avgW NP TSS)

Requires: pip install fitparse
"""
import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from .config import get_client, SCHEMA

try:
    from fitparse import FitFile
    HAS_FITPARSE = True
except ImportError:
    HAS_FITPARSE = False


def parse_fit(fit_path: str) -> dict:
    """Parse a .fit file and extract session-level metrics."""
    if not HAS_FITPARSE:
        raise ImportError("fitparse not installed. Run: pip install fitparse")

    ff = FitFile(fit_path)

    session = {}
    for record in ff.get_messages("session"):
        for field in record.fields:
            session[field.name] = field.value

    # Map fitparse fields → our schema
    ts = session.get("start_time") or session.get("timestamp")
    if ts and not isinstance(ts, str):
        ts = ts.isoformat()

    result = {
        "timestamp": ts,
        "duration_min": round(session.get("total_timer_time", 0) / 60, 2) if session.get("total_timer_time") else None,
        "distance_km": round(session.get("total_distance", 0) / 1000, 5) if session.get("total_distance") else None,
        "total_ascent": session.get("total_ascent"),
        "total_descent": session.get("total_descent"),
        "avg_power": session.get("avg_power"),
        "normalized_power": session.get("normalized_power"),
        "max_power": session.get("max_power"),
        "avg_heart_rate": session.get("avg_heart_rate"),
        "max_heart_rate": session.get("max_heart_rate"),
        "avg_cadence": session.get("avg_cadence"),
        "total_calories": session.get("total_calories"),
        "avg_temp": session.get("avg_temperature"),
    }

    # Calculate derived metrics if we have power data
    ftp = session.get("threshold_power")
    if ftp and result["normalized_power"]:
        result["ftp"] = ftp
        result["intensity_factor"] = round(result["normalized_power"] / ftp, 3)
        duration_h = (result["duration_min"] or 0) / 60
        result["training_stress_score"] = round(
            (duration_h * result["normalized_power"] * result["intensity_factor"]) / ftp * 100, 1
        )

    if result["normalized_power"] and result["avg_heart_rate"]:
        result["ef"] = round(result["normalized_power"] / result["avg_heart_rate"], 3)

    # Calculate work in kJ
    if result["avg_power"] and result["duration_min"]:
        result["total_work_kj"] = round(result["avg_power"] * result["duration_min"] * 60 / 1000, 3)

    # Filter out None values
    return {k: v for k, v in result.items() if v is not None}


def ingest_fit(fit_path: str, verbose: bool = True) -> dict:
    """Parse a .fit file and insert into cycling_sessions."""
    sb = get_client()
    data = parse_fit(fit_path)

    if not data.get("timestamp"):
        print(f"  ⚠ No timestamp found in {fit_path}, skipping")
        return {}

    result = sb.schema(SCHEMA).table("cycling_sessions").insert(data).execute()

    if verbose:
        print(f"  ✓ {Path(fit_path).name}: {data.get('duration_min', '?')}min, "
              f"avg {data.get('avg_power', '?')}W, TSS={data.get('training_stress_score', '?')}")
        print(f"    → PMC auto-recalculated via trigger")

    return result.data[0] if result.data else {}


def ingest_fit_dir(fit_dir: str, verbose: bool = True) -> list:
    """Process all .fit files in a directory."""
    dir_path = Path(fit_dir)
    fit_files = sorted(dir_path.glob("*.fit")) + sorted(dir_path.glob("*.FIT"))

    if not fit_files:
        print(f"  No .fit files found in {fit_dir}")
        return []

    # Check which timestamps already exist to avoid duplicates
    sb = get_client()
    existing = sb.schema(SCHEMA).table("cycling_sessions") \
        .select("timestamp") \
        .execute()
    existing_ts = {r["timestamp"] for r in existing.data}

    results = []
    skipped = 0
    for f in fit_files:
        try:
            data = parse_fit(str(f))
            ts = data.get("timestamp")
            if ts and ts in existing_ts:
                skipped += 1
                continue
            result = sb.schema(SCHEMA).table("cycling_sessions").insert(data).execute()
            results.append(result.data[0] if result.data else {})
            if verbose:
                print(f"  ✓ {f.name}: {data.get('duration_min', '?')}min, TSS={data.get('training_stress_score', '?')}")
        except Exception as e:
            print(f"  ✗ {f.name}: {e}")

    if verbose:
        print(f"\n  {len(results)} new sessions inserted, {skipped} duplicates skipped.")
        print(f"  PMC auto-recalculated via trigger.")

    return results


def quick_input(args: list) -> dict:
    """Quick input: duration_min avg_power normalized_power tss"""
    if len(args) < 4:
        print("Usage: --quick duration_min avg_power normalized_power tss")
        sys.exit(1)

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "duration_min": float(args[0]),
        "avg_power": float(args[1]),
        "normalized_power": float(args[2]),
        "training_stress_score": float(args[3]),
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Garmin .fit files into APGIA/Supabase")
    parser.add_argument("--fit", help="Single .fit file to process")
    parser.add_argument("--fit-dir", help="Directory of .fit files")
    parser.add_argument("--quick", nargs="+", help="Quick input: dur avgW NP TSS")
    args = parser.parse_args()

    if args.fit:
        ingest_fit(args.fit)
    elif args.fit_dir:
        ingest_fit_dir(args.fit_dir)
    elif args.quick:
        sb = get_client()
        data = quick_input(args.quick)
        result = sb.schema(SCHEMA).table("cycling_sessions").insert(data).execute()
        print(f"  ✓ Quick ride: TSS={data['training_stress_score']} → PMC recalculated")
    else:
        parser.print_help()
