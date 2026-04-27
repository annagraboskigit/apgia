"""
APGIA Pipeline — Ingest lab exam results into Supabase
Usage:
  python -m pipeline.ingest_exam --date 2026-03-15 --data '{
    "ferritina": 75, "hematocrito": 45, "hemoglobina": 14.5,
    "sat_transferrina": 40, "hemacias": 5.1, "rdw": 14.8,
    "hdl": 42, "insulina": 2.5, "hba1c": 5.4, "glicose": 85,
    "col_total": 150, "ldl": 100, "triglicerideos": 60,
    "tst_total": 30, "cortisol": 10.5, "vit_d": 70, "vit_b12": 400,
    "calcio": 9.3
  }'

  python -m pipeline.ingest_exam --interactive
"""
import argparse
import json
import sys
from datetime import datetime

from .config import get_client, LAB_RANGES, SCHEMA


def classify(marker: str, value: float) -> str:
    """Classify a lab value as normal/high/low."""
    ref = LAB_RANGES.get(marker)
    if not ref:
        return "normal"
    if value < ref["min"]:
        return "low"
    if value > ref["max"]:
        return "high"
    return "normal"


def ingest_exam(date: str, markers: dict, verbose: bool = True):
    """Insert exam markers into apgia.lab_results via Supabase."""
    sb = get_client()

    rows = []
    alerts = []
    for marker, value in markers.items():
        ref = LAB_RANGES.get(marker, {})
        status = classify(marker, value)
        row = {
            "date": date,
            "marker": marker,
            "value": value,
            "unit": ref.get("unit", ""),
            "ref_min": ref.get("min"),
            "ref_max": ref.get("max"),
            "status": status,
        }
        rows.append(row)
        if status != "normal":
            alerts.append(f"  ⚠ {marker}: {value} {ref.get('unit','')} ({status})")

    # Upsert (on conflict date+marker do update)
    result = sb.schema(SCHEMA).table("lab_results").upsert(
        rows,
        on_conflict="date,marker"
    ).execute()

    if verbose:
        print(f"\n{'='*50}")
        print(f"  EXAME {date} — {len(rows)} marcadores")
        print(f"{'='*50}")
        for r in rows:
            flag = "✓" if r["status"] == "normal" else "⚠"
            print(f"  {flag} {r['marker']}: {r['value']} {r['unit']} [{r['status']}]")

        if alerts:
            print(f"\n  ALERTAS:")
            for a in alerts:
                print(a)

        # Compare with previous exam
        prev = sb.schema(SCHEMA).table("lab_results") \
            .select("date, marker, value") \
            .lt("date", date) \
            .order("date", desc=True) \
            .limit(len(rows)) \
            .execute()

        if prev.data:
            prev_by_marker = {}
            for p in prev.data:
                if p["marker"] not in prev_by_marker:
                    prev_by_marker[p["marker"]] = p

            if prev_by_marker:
                print(f"\n  DELTAS vs exame anterior:")
                for marker, value in markers.items():
                    if marker in prev_by_marker:
                        prev_val = prev_by_marker[marker]["value"]
                        prev_date = prev_by_marker[marker]["date"]
                        delta = value - prev_val
                        pct = (delta / prev_val * 100) if prev_val else 0
                        arrow = "↑" if delta > 0 else "↓" if delta < 0 else "="
                        print(f"    {marker}: {prev_val} → {value} ({arrow}{abs(delta):.1f}, {pct:+.1f}%) [vs {prev_date}]")

        print(f"\n  {len(result.data)} rows upserted.\n")

    return result.data


def interactive_input():
    """Prompt for exam values interactively."""
    date = input("  Data do exame (YYYY-MM-DD): ").strip()
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    markers = {}
    print("\n  Marcadores (enter pra pular):")
    for marker, ref in LAB_RANGES.items():
        val = input(f"    {marker} ({ref['unit']}) [{ref['min']}-{ref['max']}]: ").strip()
        if val:
            markers[marker] = float(val)

    return date, markers


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest lab exam into APGIA/Supabase")
    parser.add_argument("--date", help="Exam date YYYY-MM-DD")
    parser.add_argument("--data", help="JSON dict of marker:value pairs")
    parser.add_argument("--interactive", action="store_true", help="Interactive input mode")
    args = parser.parse_args()

    if args.interactive:
        date, markers = interactive_input()
    elif args.date and args.data:
        date = args.date
        markers = json.loads(args.data)
    else:
        parser.print_help()
        sys.exit(1)

    ingest_exam(date, markers)
