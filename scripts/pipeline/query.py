"""
APGIA Pipeline — Query helpers for reading data from Supabase
Used by dashboard and analysis scripts.
"""
import pandas as pd
from .config import get_client, SCHEMA


def get_cycling(days: int = None, since: str = None) -> pd.DataFrame:
    """Fetch cycling sessions, optionally filtered."""
    sb = get_client()
    q = sb.schema(SCHEMA).table("cycling_sessions").select("*").order("timestamp", desc=True)
    if since:
        q = q.gte("date", since)
    if days:
        q = q.limit(days * 2)  # rough estimate, may have 0-2 rides/day
    result = q.execute()
    df = pd.DataFrame(result.data)
    if not df.empty:
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["date"] = pd.to_datetime(df["date"])
    return df


def get_pmc(since: str = None) -> pd.DataFrame:
    """Fetch PMC daily data."""
    sb = get_client()
    q = sb.schema(SCHEMA).table("pmc_daily").select("*").order("date")
    if since:
        q = q.gte("date", since)
    result = q.execute()
    df = pd.DataFrame(result.data)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
        for col in ["tss", "ctl", "atl", "tsb"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def get_whoop(since: str = None) -> pd.DataFrame:
    """Fetch Whoop daily data."""
    sb = get_client()
    q = sb.schema(SCHEMA).table("whoop_daily").select("*").order("date")
    if since:
        q = q.gte("date", since)
    result = q.execute()
    df = pd.DataFrame(result.data)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def get_lab_results(long: bool = True) -> pd.DataFrame:
    """Fetch lab results. long=True returns long format, False returns wide."""
    sb = get_client()
    result = sb.schema(SCHEMA).table("lab_results").select("*").order("date").execute()
    df = pd.DataFrame(result.data)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    if not long:
        df = df.pivot(index="date", columns="marker", values="value").reset_index()
    return df


def get_weight(since: str = None) -> pd.DataFrame:
    """Fetch weight data."""
    sb = get_client()
    q = sb.schema(SCHEMA).table("weight_daily").select("*").order("date")
    if since:
        q = q.gte("date", since)
    result = q.execute()
    df = pd.DataFrame(result.data)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df


def get_health_unified(since: str = None) -> pd.DataFrame:
    """Fetch the unified health view (PMC + Whoop + Weight joined by date)."""
    sb = get_client()
    q = sb.schema(SCHEMA).from_("health_unified").select("*").order("date")
    if since:
        q = q.gte("date", since)
    result = q.execute()
    df = pd.DataFrame(result.data)
    if not df.empty:
        df["date"] = pd.to_datetime(df["date"])
    return df
