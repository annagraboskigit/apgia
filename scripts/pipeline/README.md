# APGIA Pipeline — Supabase

Pipeline de ingestão de dados de saúde e performance no Supabase.

## Setup

```bash
pip install -r requirements.txt

# Configurar credenciais (service_role key)
export SUPABASE_URL="https://rqiwrlygeduzaaejlmrx.supabase.co"
export SUPABASE_KEY="<service_role_key>"
```

## Scripts

### Ingestão

```bash
# Exame de sangue
python -m pipeline.ingest_exam --date 2026-03-15 --data '{"ferritina": 75, "hematocrito": 45}'
python -m pipeline.ingest_exam --interactive

# Whoop (export CSV)
python -m pipeline.ingest_whoop --dir /path/to/whoop/csvs/

# Garmin .fit
python -m pipeline.ingest_garmin --fit arquivo.fit
python -m pipeline.ingest_garmin --fit-dir /path/to/fit/files/
python -m pipeline.ingest_garmin --quick 90 180 150 45  # dur avgW NP TSS

# Peso
python -m pipeline.ingest_weight --date 2026-04-07 --kg 62.5
python -m pipeline.ingest_weight --csv weight.csv
```

### Consulta (para scripts/dashboard)

```python
from pipeline.query import get_pmc, get_cycling, get_whoop, get_lab_results

pmc = get_pmc(since="2025-06-01")
rides = get_cycling(days=30)
whoop = get_whoop()
labs = get_lab_results(long=False)  # wide format
```

## Fluxo

```
Garmin .fit → ingest_garmin → cycling_sessions → trigger → pmc_daily recalc
Whoop CSV  → ingest_whoop  → whoop_daily + whoop_journal
Exame      → ingest_exam   → lab_results
Peso       → ingest_weight → weight_daily
                               ↓
                    health_unified (view)
                               ↓
                    Dashboard (Streamlit)
```

## PMC Trigger

O PMC (CTL/ATL/TSB) é recalculado automaticamente via trigger PL/pgSQL quando:
- INSERT em cycling_sessions (novo treino)
- UPDATE em cycling_sessions (correção de TSS)
- DELETE em cycling_sessions (remoção de treino)
