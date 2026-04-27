# APGIA

Dashboard pessoal de saúde e performance — treinos (Garmin .fit), recovery/sono (Whoop), exames de sangue, peso.

## Arquitetura

```
Garmin .fit  → ingest_garmin  → cycling_sessions → trigger → pmc_daily (CTL/ATL/TSB)
Garmin API   → sync_garmin    → cycling_sessions   (garth — Connect API)
Whoop API    → whoop-sync     → whoop_daily         (Edge Function — OAuth2)
Whoop CSV    → ingest_whoop   → whoop_daily + whoop_journal
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
│       ├── sync_garmin.py      ← Garmin Connect API → cycling_sessions
│       ├── query.py            ← helpers de leitura (DataFrames)
│       └── requirements.txt
├── docs/
│   └── architecture.png        ← diagrama de arquitetura
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

```bash
# Garmin .fit (arquivo local)
python -m pipeline.ingest_garmin --fit arquivo.fit
python -m pipeline.ingest_garmin --fit-dir /path/to/fits/
python -m pipeline.ingest_garmin --quick 90 180 150 45   # dur avgW NP TSS

# Garmin Connect API (sync automático)
python -m pipeline.sync_garmin --login           # primeira vez: autenticar
python -m pipeline.sync_garmin --days 30          # sync últimos 30 dias
python -m pipeline.sync_garmin --from 2025-01-01  # sync por data

# Whoop API (Edge Functions — automático)
# 1. Abrir: https://rqiwrlygeduzaaejlmrx.supabase.co/functions/v1/whoop-auth
# 2. Autorizar no Whoop
# 3. Abrir: https://rqiwrlygeduzaaejlmrx.supabase.co/functions/v1/whoop-sync?days=30

# Whoop (export CSV — legado)
python -m pipeline.ingest_whoop --dir /path/to/whoop/csvs/

# Exame de sangue
python -m pipeline.ingest_exam --date 2026-03-15 --data '{"ferritina": 75}'
python -m pipeline.ingest_exam --interactive

# Peso
python -m pipeline.ingest_weight --date 2026-04-07 --kg 62.5
python -m pipeline.ingest_weight --csv weight.csv
```

## Análise pós-treino

```bash
python analyze_ride.py --quick 90 180 150 45
python analyze_ride.py --fit arquivo.fit
python analyze_ride.py --manual
```

Gera `output/last_ride_analysis.json` com contexto completo (PMC, Whoop, lab, treinos semelhantes, sugestões).

## Dashboard (Streamlit)

```bash
streamlit run dashboard_v3.py
```

6 páginas: Visão Geral, PMC, Potência & Eficiência, Recovery & Sono, Exames, Peso.

### Deploy Streamlit Cloud

1. Conectar repo no Streamlit Cloud
2. Main file: `scripts/dashboard_v3.py`
3. Settings → Secrets → colar conteúdo de `.streamlit/secrets.toml` com a key real

## Whoop Sync (Edge Functions)

3 Edge Functions no Supabase:

- `whoop-auth` — redireciona pro OAuth2 do Whoop
- `whoop-callback` — recebe o token e salva em `public.whoop_tokens`
- `whoop-sync` — busca `/v2/recovery`, `/v2/cycle`, `/v2/activity/sleep` e faz upsert via RPC

Aceita `?days=N` pra controlar o range (default: 3). Sem refresh token (app em test mode), precisa re-auth a cada sync.

## Garmin Sync (Python)

Usa a lib `garth` pra autenticar no Garmin Connect e baixar .fit files automaticamente. Tokens ficam em `~/.garth/`. Requer `pip install garth`.

## PMC Auto-recalculation

O PMC (CTL/ATL/TSB) recalcula automaticamente via trigger PL/pgSQL quando há INSERT/UPDATE/DELETE em `cycling_sessions`. Fórmula EMA padrão: CTL 42d, ATL 7d, TSB = CTL - ATL.

## Deploy GitHub Pages

```bash
git add index.html
git commit -m "atualiza dashboard"
git push
```

Site atualiza em ~1-2 min → `apgia.annagraboski.com`
