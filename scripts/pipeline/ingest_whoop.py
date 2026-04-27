"""
APGIA Pipeline — Ingest Whoop CSV exports into Supabase
Usage:
  python -m pipeline.ingest_whoop --dir /path/to/whoop/exports/

Expects these CSVs in the directory:
  - physiological_cycles.csv  (recovery, HRV, strain, etc.)
  - sleeps.csv                (sleep stages, duration)
  - journal_entries.csv       (daily journal boolean flags)
  - workouts.csv              (optional — workout details)
"""
import argparse
import pandas as pd
import numpy as np
from pathlib import Path

from .config import get_client, SCHEMA


# ── Column mappings: Whoop CSV → Supabase table ──

PHYSIO_MAP = {
    "Recovery score %": "recovery_score",
    "Resting heart rate (bpm)": "resting_hr",
    "Heart rate variability (ms)": "hrv",
    "Skin temp (celsius)": "skin_temp",
    "Blood oxygen %": "spo2",
    "Day Strain": "day_strain",
    "Kilojoule (kJ)": "calories",  # will convert kJ → kcal
    "Max HR (bpm)": "max_hr",
    "Average HR (bpm)": "avg_hr",
}

SLEEP_MAP = {
    "Sleep performance %": "sleep_performance",
    "Respiratory rate (rpm)": "sleep_respiratory_rate",
    "Asleep duration (min)": "sleep_duration_min",
    "In bed duration (min)": "sleep_in_bed_min",
    "Light sleep duration (min)": "sleep_light_min",
    "Slow wave sleep duration (min)": "sleep_deep_min",
    "REM duration (min)": "sleep_rem_min",
    "Awake duration (min)": "sleep_awake_min",
    "Sleep need (min)": "sleep_need_min",
    "Sleep debt (min)": "sleep_debt_min",
    "Sleep efficiency %": "sleep_efficiency",
    "Sleep consistency %": "sleep_consistency",
}

JOURNAL_MAP = {
    "Consumed Caffeine": "consumed_caffeine",
    "Connected with Family and/or Friends": "connected_with_family_or_friends",
    "Ate Food Close to Bedtime": "ate_close_to_bedtime",
    "Engaged in Sexual Activity": "engaged_in_sexual_activity",
    "Masturbated": "masturbated",
    "Experienced Stress": "experienced_stress",
    "Experienced Bloating": "experienced_bloating",
    "Received Massage Therapy": "received_massage_therapy",
    "Felt Irritable": "felt_irritable",
    "Consumed Protein": "consumed_protein",
    "Had a Dog in the Room While Sleeping": "had_dog_in_room",
    "Took Vitamin B-12": "took_vitamin_b12",
    "Experienced a Headache": "experienced_headache",
    "Experienced Food Cravings": "experienced_food_cravings",
    "Took Vitamin D": "took_vitamin_d",
    "Experienced Increased Libido": "experienced_increased_libido",
    "Experienced Mood Swings": "experienced_mood_swings",
    "Experienced Back Pain": "experienced_back_pain",
    "Felt Energized Throughout the Day": "felt_energized",
    "Hydrated Sufficiently": "hydrated_sufficiently",
    "Experienced Constipation": "experienced_constipation",
    "Experienced Acne": "experienced_acne",
    "Made Progress on an Important Goal": "made_progress_on_goal",
    "Used Testosterone Gel or Cream": "used_testosterone_gel",
    "Snacked in Between Meals": "snacked_between_meals",
    "Took a Magnesium Supplement": "took_magnesium",
    "Feeling Sick or Ill": "feeling_sick",
    "Experienced Memory Lapses or Forgetfulness": "experienced_memory_lapses",
    "Took Prescription Pain Medication": "took_prescription_pain_medication",
    "Took an Ice Bath": "took_ice_bath",
    "Felt Emotionally and Mentally Stable": "felt_emotionally_stable",
    "Experienced Fatigue": "experienced_fatigue",
    "Felt Socially Fulfilled": "felt_socially_fulfilled",
    "Feel Generally Positive About the Future": "feel_positive_about_future",
    "Consumed Carbohydrates": "consumed_carbohydrates",
    "Felt You Had the Resources/Skills Needed to Complete Your Daily Goals": "felt_had_resources_for_goals",
    "Took Weight-Loss Medication": "took_weight_loss_medication",
    "Took Prescription Sleep Medication": "took_prescription_sleep_medication",
    "Felt Recovered": "felt_recovered",
    "Took Creatine": "took_creatine",
    "Experienced Joint Pain or Stiffness": "experienced_joint_pain",
    "Worked Late": "worked_late",
    "Consumed Beans": "consumed_beans",
    "Felt Socially Drained": "felt_socially_drained",
    "Traveled on a Plane": "traveled_on_plane",
    "Faced Threats": "faced_threats",
}


def clean_val(v):
    """Convert NaN/None to None for JSON."""
    if pd.isna(v):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


def extract_date(df, date_col="Cycle start time"):
    """Extract date from Whoop datetime column."""
    df = df.copy()
    if date_col in df.columns:
        df["date"] = pd.to_datetime(df[date_col]).dt.date.astype(str)
    elif "Date" in df.columns:
        df["date"] = pd.to_datetime(df["Date"]).dt.date.astype(str)
    return df


def ingest_whoop(directory: str, verbose: bool = True):
    """Ingest Whoop CSV exports into Supabase."""
    sb = get_client()
    dir_path = Path(directory)

    stats = {}

    # ── Physiological cycles → whoop_daily ──
    physio_file = dir_path / "physiological_cycles.csv"
    if physio_file.exists():
        df = pd.read_csv(physio_file)
        df = extract_date(df)

        rows = []
        for _, r in df.iterrows():
            row = {"date": r["date"]}
            for csv_col, db_col in PHYSIO_MAP.items():
                if csv_col in df.columns:
                    row[db_col] = clean_val(r.get(csv_col))
            rows.append(row)

        # Merge with sleep data if available
        sleep_file = dir_path / "sleeps.csv"
        if sleep_file.exists():
            sdf = pd.read_csv(sleep_file)
            sdf = extract_date(sdf, "Cycle start time" if "Cycle start time" in sdf.columns else "Date")

            sleep_by_date = {}
            for _, r in sdf.iterrows():
                d = r["date"]
                if d not in sleep_by_date:
                    sleep_by_date[d] = {}
                for csv_col, db_col in SLEEP_MAP.items():
                    if csv_col in sdf.columns:
                        val = clean_val(r.get(csv_col))
                        if val is not None:
                            sleep_by_date[d][db_col] = val

            for row in rows:
                if row["date"] in sleep_by_date:
                    row.update(sleep_by_date[row["date"]])

        result = sb.schema(SCHEMA).table("whoop_daily").upsert(
            rows, on_conflict="date"
        ).execute()
        stats["whoop_daily"] = len(result.data)
    else:
        if verbose:
            print(f"  ⚠ {physio_file} not found, skipping whoop_daily")

    # ── Journal entries → whoop_journal ──
    journal_file = dir_path / "journal_entries.csv"
    if journal_file.exists():
        df = pd.read_csv(journal_file)
        df = extract_date(df, "Cycle start time" if "Cycle start time" in df.columns else "Date")

        rows = []
        for _, r in df.iterrows():
            row = {"date": r["date"]}
            for csv_col, db_col in JOURNAL_MAP.items():
                if csv_col in df.columns:
                    val = clean_val(r.get(csv_col))
                    if isinstance(val, str):
                        val = val.lower() == "true"
                    row[db_col] = val
            rows.append(row)

        result = sb.schema(SCHEMA).table("whoop_journal").upsert(
            rows, on_conflict="date"
        ).execute()
        stats["whoop_journal"] = len(result.data)
    else:
        if verbose:
            print(f"  ⚠ {journal_file} not found, skipping whoop_journal")

    if verbose:
        print(f"\n{'='*50}")
        print(f"  WHOOP INGEST")
        print(f"{'='*50}")
        for table, count in stats.items():
            print(f"  {table}: {count} rows upserted")
        print()

    return stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ingest Whoop exports into APGIA/Supabase")
    parser.add_argument("--dir", required=True, help="Directory with Whoop CSV exports")
    args = parser.parse_args()
    ingest_whoop(args.dir)
