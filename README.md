# APGIA

Dashboard pessoal de saúde e performance — treinos (Strava + Garmin .fit), recovery/sono (Whoop), exames de sangue, peso.

## Arquitetura

```
Strava API   → strava-sync    → cycling_sessions → trigger → pmc_daily (CTL/ATL/TSB)
Garmin .fit  → ingest_garmin  → cycling_sessions   (parse local)
Garmin API   → sync_garmin    → cycling_sessions   (garminconnect — backup)
Whoop API    → whoop-sync     → whoop_daily         (Edge Function — OAuth2)
Whoop CSV    → ingest_whoop   → whoop_daily + whoop_journal
Open-Meteo   → weather-enrich → cycling_sessions.weather_*
Exame        → ingest_exam    → lab_results
Peso         → ingest_weight  → weight_daily
                                  ↓
                       health_unified (VIEW)
                                  ↓
                       Dashboard (Streamlit)
```

**Backend:** Supabase (schema `apgia`, projeto `rqiwrlygeduzaaejlmrx`)
**Dashboard:** Streamlit Cloud (`dashboard_v3.py`)
**Site estático:** GitHub Pages → `apgia.annagraboski.com`

## Dados (abr/2026)

| Tabela | Rows | Range |
|--------|------|-------|
| cycling_sessions | 559 | mai/2024 → abr/2026 |
| pmc_daily | 728 | — |
| whoop_daily | 440 | fev/2025 → abr/2026 |
| whoop_journal | 350 | — |
| lab_results | 0 | pendente |
| weight_daily | 0 | pendente |

Sources dos rides: 378 strava, 160 garmin_fit, 21 strava+fit (merged).

## Estrutura

```
apgia-repo/
├── index.html                  ← site estático (GitHub Pages)
├── scripts/
│   ├── dashboard_v3.py         ← Streamlit dashboard (Supabase)
│   ├── analyze_ride.py         ← análise pós-treino (Supabase)
│   ├── .streamlit/
│   │   └── secrets.toml        ← credenciais (gitignored)
│   └── pipeline/
│       ├── config.py           ← conexão Supabase + LAB_RANGES
│       ├── ingest_garmin.py    ← .fit → cycling_sessions
│       ├── ingest_whoop.py     ← CSV → whoop_daily + journal
│       ├── ingest_exam.py      ← exames → lab_results
│       ├── ingest_weight.py    ← peso → weight_daily
│       ├── sync_garmin.py      ← Garmin Connect API (garminconnect)
│       ├── enrich_weather.py   ← Open-Meteo → weather p/ rides
│       ├── query.py            ← helpers de leitura (DataFrames)
│       └── requirements.txt
├── docs/
│   ├── architecture.png        ← diagrama de arquitetura
│   └── icon.png                ← ícone do app (Strava/Whoop)
├── archive/dashboards/         ← versões anteriores
└── scripts/dashboard.py        ← v1 legado (local)
    scripts/dashboard_v2.py     ← v2 legado (local)
```

## Setup

```bash
cd scripts
pip install -r pipeline/requirements.txt

export SUPABASE_URL="https://rqiwrlygeduzaaejlmrx.supabase.co"
export SUPABASE_KEY="<service_role_key>"
```

## Ingestão de dados

### Strava (caminho principal — Edge Function)

```bash
# 1. Autorizar (uma vez, refresh token automático depois):
#    https://rqiwrlygeduzaaejlmrx.supabase.co/functions/v1/strava-auth

# 2. Sync:
#    https://rqiwrlygeduzaaejlmrx.supabase.co/functions/v1/strava-sync?days=30

# Backfill histórico completo:
#    https://rqiwrlygeduzaaejlmrx.supabase.co/functions/v1/strava-sync?days=730
```

Filtra só cycling (Ride, VirtualRide, MTB, Gravel, EBike). Dedup por strava_id. Puxa power, NP, HR, cadence, calories, elevation, lat/lon. Token auto-refresh.

### Garmin .fit (arquivo local)

```bash
python -m pipeline.ingest_garmin --fit arquivo.fit
python -m pipeline.ingest_garmin --fit-dir /path/to/fits/
python -m pipeline.ingest_garmin --quick 90 180 150 45   # dur avgW NP TSS
```

### Garmin Connect API (backup — rate limited)

```bash
python -m pipeline.sync_garmin --login           # primeira vez
python -m pipeline.sync_garmin --days 30          # sync
```

Usa `garminconnect`. Garmin bloqueia IPs com rate limit agressivo — Strava é o caminho preferido.

### Whoop (Edge Functions)

```bash
# 1. Abrir: https://rqiwrlygeduzaaejlmrx.supabase.co/functions/v1/whoop-auth
# 2. Autorizar no Whoop
# 3. Abrir: https://rqiwrlygeduzaaejlmrx.supabase.co/functions/v1/whoop-sync?days=30
```

App em test mode — sem refresh token, re-auth manual. Submetido pra aprovação (abr/2026).

### Weather (Edge Function)

```bash
# Enriquecer rides sem weather (usa lat/lon do ride ou default Rio de Janeiro):
# https://rqiwrlygeduzaaejlmrx.supabase.co/functions/v1/weather-enrich?limit=50
# https://rqiwrlygeduzaaejlmrx.supabase.co/functions/v1/weather-enrich?backfill=true
```

### Outros

```bash
# Exame de sangue
python -m pipeline.ingest_exam --date 2026-03-15 --data '{"ferritina": 75}'

# Peso
python -m pipeline.ingest_weight --date 2026-04-07 --kg 62.5
python -m pipeline.ingest_weight --csv weight.csv

# Whoop CSV (legado)
python -m pipeline.ingest_whoop --dir /path/to/whoop/csvs/
```

## Manutenção

### Merge de duplicatas

Quando tem rides tanto do Strava quanto do .fit (mesmo treino), rodar:

```sql
SELECT public.merge_duplicate_rides();
```

Copia campos granulares do .fit (IF, TSS, EF, decoupling, power zones) pro registro do Strava, marca source como 'strava+fit', deleta o .fit duplicado.

### Weather enrich (Python)

```bash
python -m pipeline.enrich_weather              # rides sem weather
python -m pipeline.enrich_weather --backfill   # todas
python -m pipeline.enrich_weather --date 2026-04-15
```

## Edge Functions (Supabase)

| Function | O que faz |
|----------|-----------|
| strava-auth | Redirect → OAuth Strava (scopes: activity:read_all, profile:read_all) |
| strava-callback | Troca code → tokens, salva em public.strava_tokens |
| strava-sync | Busca /athlete/activities → filtra cycling → upsert via RPC. `?days=N` |
| whoop-auth | Redirect → OAuth Whoop |
| whoop-callback | Troca code → tokens, salva em public.whoop_tokens |
| whoop-sync | Busca /v2/recovery, cycle, sleep → upsert via RPC. `?days=N` |
| weather-enrich | Open-Meteo → enrich rides sem weather. `?limit=N`, `?backfill=true` |

## PMC Auto-recalculation

O PMC (CTL/ATL/TSB) recalcula automaticamente via trigger PL/pgSQL quando há INSERT/UPDATE/DELETE em `cycling_sessions`. Fórmula EMA padrão: CTL 42d, ATL 7d, TSB = CTL - ATL.

## Dashboard (Streamlit)

```bash
streamlit run dashboard_v3.py
```

6 páginas: Visão Geral, PMC, Potência & Eficiência, Recovery & Sono, Exames, Peso.

### Deploy Streamlit Cloud

1. Conectar repo no Streamlit Cloud
2. Main file: `scripts/dashboard_v3.py`
3. Settings → Secrets → colar conteúdo de `.streamlit/secrets.toml` com a key real
