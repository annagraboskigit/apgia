"""
APGIA Pipeline — Ingest weight data into Supabase
Usage:
  python -m pipeline.ingest_weight --date 2026-04-07 --kg 62.5
  python -m pipeline.ingest_weight --csv /path/to/weight.csv
"""
import argparse
import pandas as pd
from .config import get_client, SCHEMA


def ingest_weight_single(date: str, weight_kg: float, verbose: bool = True):
    """Insert or update a single weight entry."""
    sb = get_client()
    result = sb.schema(SCHEMA).table("weight_daily").upsert(
        {"date": date, "weight_kg": weight_kg},
        on_conflict="date"
    ).execute()
    if verbose:
        print(f"  ✓ {date}: {weight_kg} kg")
    return result.data


def ingest_weight_csv(csv_path: str, verbose: bool = True):
    """Import weight CSV (columns: date, weight or weight_kg)."""
    sb = get_client()
    df = pd.read_csv(csv_path)

    # Normalize column names
    if "weight" in df.columns:
        df = df.rename(columns={"weight": "weight_kg"})
    if "Date" in df.columns:
        df = df.rename(columns={"Date": "date"})

    df["date"] = pd.to_datetime(df["date"]).dt.date.astype(str)
    rows = df[["date", "weight_kg"]].dropna().to_dict("records")

    result = sb.schema(SCHEMA).table("weight_daily").upsert(
        rows, on_conflict="date"
    ).execute()

    if verbose:
        print(f"  ✓ {len(result.data)} weight entries upserted from {csv_path}")
    return result.data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest weight into APGIA/Supabase")
    parser.add_argument("--date", help="Date YYYY-MM-DD")
    parser.add_argument("--kg", type=float, help="Weight in kg")
    parser.add_argument("--csv", help="CSV file with date,weight columns")
    args = parser.parse_args()

    if args.csv:
        ingest_weight_csv(args.csv)
    elif args.date and args.kg:
        ingest_weight_single(args.date, args.kg)
    else:
        parser.print_help()
