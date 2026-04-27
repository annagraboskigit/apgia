"""
APGIA Pipeline — Config & Supabase connection
Requires: pip install supabase
Environment variables:
  SUPABASE_URL  — project URL (https://rqiwrlygeduzaaejlmrx.supabase.co)
  SUPABASE_KEY  — service_role key (bypasses RLS)
"""
import os
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://rqiwrlygeduzaaejlmrx.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")

SCHEMA = "apgia"

# Biomarker reference ranges (female cyclist, sport-optimized)
LAB_RANGES = {
    "ferritina":        {"unit": "ng/mL",   "min": 50,   "max": 200},
    "hematocrito":      {"unit": "%",       "min": 36,   "max": 48},
    "hemoglobina":      {"unit": "g/dL",    "min": 12,   "max": 16},
    "sat_transferrina": {"unit": "%",       "min": 20,   "max": 50},
    "hemacias":         {"unit": "M/uL",    "min": 4.0,  "max": 5.5},
    "rdw":              {"unit": "%",       "min": 11.5, "max": 15.5},
    "cortisol":         {"unit": "ug/dL",   "min": 5,    "max": 25},
    "insulina":         {"unit": "uU/mL",   "min": 2,    "max": 25},
    "hba1c":            {"unit": "%",       "min": 4.0,  "max": 5.7},
    "glicose":          {"unit": "mg/dL",   "min": 70,   "max": 100},
    "col_total":        {"unit": "mg/dL",   "min": 0,    "max": 200},
    "hdl":              {"unit": "mg/dL",   "min": 40,   "max": 100},
    "ldl":              {"unit": "mg/dL",   "min": 0,    "max": 130},
    "triglicerideos":   {"unit": "mg/dL",   "min": 0,    "max": 150},
    "tst_total":        {"unit": "ng/dL",   "min": 15,   "max": 70},
    "vit_d":            {"unit": "ng/mL",   "min": 40,   "max": 100},
    "vit_b12":          {"unit": "pg/mL",   "min": 200,  "max": 900},
    "calcio":           {"unit": "mg/dL",   "min": 8.5,  "max": 10.5},
}


def get_client() -> Client:
    """Return authenticated Supabase client (service_role)."""
    if not SUPABASE_KEY:
        raise ValueError(
            "Set SUPABASE_KEY env var to the service_role key.\n"
            "Find it at: https://supabase.com/dashboard/project/rqiwrlygeduzaaejlmrx/settings/api"
        )
    return create_client(SUPABASE_URL, SUPABASE_KEY)
