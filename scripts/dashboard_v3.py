"""
Cycling Analytics Dashboard v3
Streamlit + Plotly — reads from Supabase (apgia schema)
Run: streamlit run dashboard_v3.py

Requires:
  pip install streamlit plotly supabase pandas numpy
  Set SUPABASE_URL and SUPABASE_KEY env vars (or .streamlit/secrets.toml)
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import datetime
from supabase import create_client
from urllib.parse import urlencode

# ── Config ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="APGIA — Cycling Analytics",
    page_icon="🚴‍♀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

SCHEMA = "apgia"

# Azure AD / Supabase Auth config
SUPABASE_URL = "https://rqiwrlygeduzaaejlmrx.supabase.co"
ALLOWED_EMAIL = "eu@annagraboski.com"


# Anon key for auth operations (PKCE exchange needs anon, not service_role)
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InJxaXdybHlnZWR1emFhZWpsbXJ4Iiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzMyMjE5MjgsImV4cCI6MjA4ODc5NzkyOH0.qT2UV4EB3yPxqETZrpWz2Ypsy7a1RslWW51JmD8ttkw"


# ── Supabase connection (cached) ──────────────────────────────
@st.cache_resource
def get_sb():
    # Try streamlit secrets first, then env vars
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    except Exception:
        import os
        url = os.environ.get("SUPABASE_URL", SUPABASE_URL)
        key = os.environ.get("SUPABASE_KEY", "")
    if not key:
        st.error("Configure SUPABASE_KEY em .streamlit/secrets.toml ou variavel de ambiente.")
        st.stop()
    return create_client(url, key)


@st.cache_resource
def get_sb_auth():
    """Anon client for auth operations (PKCE exchange)."""
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


# ── Auth: Azure AD via Supabase OAuth (implicit flow) ────────────
REDIRECT_URL = "https://apgia-dashboard.streamlit.app/"


def auth_guard():
    """
    Check authentication via Azure AD + Supabase implicit OAuth.
    Implicit flow returns #access_token in URL fragment.
    st.markdown JS (runs in main context, not iframe) captures it.
    """
    # Step 1: Check if we have access_token in query params (from JS redirect)
    params = st.query_params
    token = params.get("access_token")

    if token:
        try:
            sb = get_sb_auth()
            user_resp = sb.auth.get_user(token)
            user = user_resp.user
            if user and user.email == ALLOWED_EMAIL:
                st.session_state["user"] = user
                st.session_state["access_token"] = token
                st.query_params.clear()
                return True
            else:
                st.error(f"Acesso negado. Email: {user.email if user else 'unknown'}")
                st.stop()
        except Exception as e:
            st.session_state.pop("user", None)
            st.session_state.pop("access_token", None)
            st.error(f"Erro na autentica\u00e7\u00e3o: {e}")

    # Step 2: Check session state (already logged in this session)
    if "user" in st.session_state:
        return True

    # Step 3: Inject fragment parser via st.markdown (runs in MAIN context)
    st.markdown("""
    <script>
    (function() {
        var hash = window.location.hash;
        if (hash && hash.indexOf('access_token=') !== -1) {
            var params = new URLSearchParams(hash.substring(1));
            var token = params.get('access_token');
            if (token) {
                var url = new URL(window.location.href);
                url.hash = '';
                url.searchParams.set('access_token', token);
                window.location.replace(url.toString());
            }
        }
    })();
    </script>
    """, unsafe_allow_html=True)

    # Step 4: Show login page
    st.markdown("""
    <style>
    .login-container {
        display: flex; flex-direction: column; align-items: center;
        justify-content: center; min-height: 60vh;
    }
    .login-title { font-size: 3rem; font-weight: 700; margin-bottom: 0.5rem; }
    </style>
    <div class="login-container">
        <div class="login-title">APGIA</div>
    </div>
    """, unsafe_allow_html=True)

    oauth_url = (
        f"{SUPABASE_URL}/auth/v1/authorize?"
        + urlencode({
            "provider": "azure",
            "redirect_to": REDIRECT_URL,
            "scopes": "email",
        })
    )

    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        st.link_button(
            "Login MS SSO",
            oauth_url,
            use_container_width=True,
            type="primary",
        )

    st.stop()
    return False


# ── Theme colors ────────────────────────────────────────────────
COLORS = {
    "ctl": "#2196F3",       # blue - fitness
    "atl": "#FF5722",       # red-orange - fatigue
    "tsb": "#4CAF50",       # green - form
    "power": "#9C27B0",     # purple
    "hr": "#F44336",        # red
    "ef": "#FF9800",        # orange
    "weight": "#607D8B",    # grey
    "cadence": "#00BCD4",   # cyan
    "tss": "#795548",       # brown
    "recovery": "#66BB6A",  # green
    "hrv": "#42A5F5",       # light blue
    "sleep": "#7E57C2",     # deep purple
}

PLOT_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", size=12),
    margin=dict(l=60, r=20, t=40, b=40),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)


# ── Data Loading (cached, from Supabase) ──────────────────────
@st.cache_data(ttl=300)
def load_cycling():
    sb = get_sb()
    result = sb.schema(SCHEMA).table("cycling_sessions").select("*").order("timestamp").execute()
    df = pd.DataFrame(result.data)
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = pd.to_datetime(df["date"])
    for col in ["avg_power", "normalized_power", "max_power", "training_stress_score",
                 "avg_heart_rate", "max_heart_rate", "avg_cadence", "duration_min",
                 "distance_km", "total_ascent", "total_descent", "total_calories",
                 "ef", "decoupling_pct", "intensity_factor", "ftp"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["weekday"] = df["timestamp"].dt.day_name()
    df["month"] = df["timestamp"].dt.to_period("M").astype(str)
    df["quarter"] = df["timestamp"].dt.to_period("Q").astype(str)
    df["year"] = df["timestamp"].dt.year
    return df


@st.cache_data(ttl=300)
def load_pmc():
    sb = get_sb()
    result = sb.schema(SCHEMA).table("pmc_daily").select("*").order("date").execute()
    df = pd.DataFrame(result.data)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    for col in ["tss", "ctl", "atl", "tsb"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=300)
def load_whoop():
    sb = get_sb()
    result = sb.schema(SCHEMA).table("whoop_daily").select("*").order("date").execute()
    df = pd.DataFrame(result.data)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    for col in df.columns:
        if col != "date":
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=300)
def load_weight():
    sb = get_sb()
    result = sb.schema(SCHEMA).table("weight_daily").select("*").order("date").execute()
    df = pd.DataFrame(result.data)
    if df.empty:
        return None
    df["date"] = pd.to_datetime(df["date"])
    df["weight_kg"] = pd.to_numeric(df["weight_kg"], errors="coerce")
    return df


@st.cache_data(ttl=300)
def load_lab_results():
    sb = get_sb()
    result = sb.schema(SCHEMA).table("lab_results").select("*").order("date").execute()
    df = pd.DataFrame(result.data)
    if df.empty:
        return None
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


# ── Auth Gate ──────────────────────────────────────────────────
auth_guard()

# ── Sidebar ─────────────────────────────────────────────────────
st.sidebar.title("🚴‍♀️ APGIA")
st.sidebar.caption("Saude & Performance")

page = st.sidebar.radio(
    "Navegação",
    [
        "📊 Visão Geral",
        "📈 PMC (Fitness/Fadiga)",
        "⚡ Potência & Eficiência",
        "💚 Recovery & Sono",
        "🩸 Exames",
        "⚖️ Peso",
    ],
)

# Date filter
try:
    cycling = load_cycling()
    if cycling.empty:
        st.error("⚠️ Sem dados em cycling_sessions.")
        st.stop()

    min_date = cycling["timestamp"].min().date()
    max_date = cycling["timestamp"].max().date()

    st.sidebar.markdown("---")
    st.sidebar.subheader("📅 Período")

    preset = st.sidebar.radio(
        "Período",
        ["Tudo", "12m", "6m", "3m", "Custom"],
        horizontal=True,
        index=0,
        label_visibility="collapsed",
    )
    if preset == "Tudo":
        start_date, end_date = min_date, max_date
    elif preset == "12m":
        start_date = max_date - datetime.timedelta(days=365)
        end_date = max_date
    elif preset == "6m":
        start_date = max_date - datetime.timedelta(days=180)
        end_date = max_date
    elif preset == "3m":
        start_date = max_date - datetime.timedelta(days=90)
        end_date = max_date
    else:
        date_range = st.sidebar.date_input(
            "Período",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )
        start_date, end_date = (date_range if len(date_range) == 2 else (min_date, max_date))

    st.sidebar.caption(f"{start_date} → {end_date}")

except Exception as e:
    st.error(f"⚠️ Erro ao carregar dados: {e}")
    st.stop()


def filter_by_date(df, date_col="timestamp"):
    if start_date and end_date:
        mask = (df[date_col].dt.date >= start_date) & (df[date_col].dt.date <= end_date)
        return df[mask].copy()
    return df.copy()


def filter_pmc_by_date(df):
    if start_date and end_date:
        mask = (df["date"].dt.date >= start_date) & (df["date"].dt.date <= end_date)
        return df[mask].copy()
    return df.copy()


# ═══════════════════════════════════════════════════════════════
# PAGE: VISÃO GERAL
# ═══════════════════════════════════════════════════════════════
if page == "📊 Visão Geral":
    bike = filter_by_date(cycling)

    st.title("Visão Geral")
    st.caption(f"📅 {start_date} → {end_date} • {len(bike)} treinos")

    # KPIs
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Treinos", f"{len(bike)}")
    col2.metric("Distância", f"{bike['distance_km'].sum():,.0f} km")
    col3.metric("Horas", f"{bike['duration_min'].sum() / 60:,.0f}h")
    col4.metric("Elevação", f"{bike['total_ascent'].sum():,.0f} m")
    col5.metric("Calorias", f"{bike['total_calories'].sum():,.0f} kcal")

    st.markdown("---")

    # Monthly volume
    monthly = bike.set_index("timestamp").resample("ME").agg(
        treinos=("distance_km", "count"),
        km=("distance_km", "sum"),
        horas=("duration_min", lambda x: x.sum() / 60),
        tss=("training_stress_score", "sum"),
        elevacao=("total_ascent", "sum"),
    ).reset_index()

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
        subplot_titles=("Volume Mensal (km)", "TSS Mensal"),
    )
    fig.add_trace(
        go.Bar(x=monthly["timestamp"], y=monthly["km"], name="Distância (km)",
               marker_color=COLORS["ctl"], opacity=0.8),
        row=1, col=1,
    )
    fig.add_trace(
        go.Bar(x=monthly["timestamp"], y=monthly["tss"], name="TSS",
               marker_color=COLORS["tss"], opacity=0.8),
        row=2, col=1,
    )
    fig.update_layout(**PLOT_LAYOUT, height=500)
    st.plotly_chart(fig, use_container_width=True)

    # Weekday distribution
    col1, col2 = st.columns(2)
    with col1:
        weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        weekday_labels = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        by_day = bike.groupby("weekday").agg(treinos=("distance_km", "count")).reindex(weekday_order)
        fig_day = go.Figure(go.Bar(
            x=weekday_labels, y=by_day["treinos"].values,
            marker_color=COLORS["ctl"], opacity=0.8,
        ))
        fig_day.update_layout(**PLOT_LAYOUT, height=300, title="Treinos por Dia da Semana")
        st.plotly_chart(fig_day, use_container_width=True)

    with col2:
        bins = [0, 20, 40, 60, 80, 100, 150, 300]
        labels = ["<20", "20-40", "40-60", "60-80", "80-100", "100-150", "150+"]
        bike["dist_faixa"] = pd.cut(bike["distance_km"], bins=bins, labels=labels)
        dist_counts = bike["dist_faixa"].value_counts().reindex(labels).fillna(0)
        fig_dist = go.Figure(go.Bar(
            x=labels, y=dist_counts.values,
            marker_color=COLORS["power"], opacity=0.8,
        ))
        fig_dist.update_layout(**PLOT_LAYOUT, height=300, title="Distribuição de Distância (km)")
        st.plotly_chart(fig_dist, use_container_width=True)

    # Yearly summary
    st.subheader("Evolução Anual")
    yearly = bike.groupby("year").agg(
        treinos=("distance_km", "count"),
        km=("distance_km", "sum"),
        horas=("duration_min", lambda x: x.sum() / 60),
        power_avg=("avg_power", "mean"),
        hr_avg=("avg_heart_rate", "mean"),
        tss_avg=("training_stress_score", "mean"),
    ).round(1)
    st.dataframe(yearly, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: PMC
# ═══════════════════════════════════════════════════════════════
elif page == "📈 PMC (Fitness/Fadiga)":
    st.title("Performance Management Chart")
    st.caption(f"📅 {start_date} → {end_date}")

    pmc = filter_pmc_by_date(load_pmc())
    if pmc.empty:
        st.warning("⚠️ Sem dados PMC.")
        st.stop()

    last = pmc.iloc[-1]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("CTL (Fitness)", f"{last['ctl']:.0f}")
    col2.metric("ATL (Fadiga)", f"{last['atl']:.0f}")
    col3.metric("TSB (Form)", f"{last['tsb']:.0f}")

    tsb_val = last["tsb"]
    if tsb_val > 15:
        estado = "🟢 Descansada"
    elif tsb_val > 0:
        estado = "🟡 Equilibrada"
    elif tsb_val > -15:
        estado = "🟠 Fadiga leve"
    else:
        estado = "🔴 Fadiga acumulada"
    col4.metric("Estado", estado)

    st.markdown("---")

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05,
        row_heights=[0.7, 0.3], subplot_titles=("CTL / ATL", "TSB (Form)"),
    )
    fig.add_trace(go.Scatter(x=pmc["date"], y=pmc["ctl"], name="CTL (Fitness)",
                              line=dict(color=COLORS["ctl"], width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=pmc["date"], y=pmc["atl"], name="ATL (Fadiga)",
                              line=dict(color=COLORS["atl"], width=1.5, dash="dot")), row=1, col=1)
    fig.add_trace(go.Scatter(x=pmc["date"], y=pmc["tsb"], name="TSB (Form)",
                              line=dict(color=COLORS["tsb"], width=1.5),
                              fill="tozeroy", fillcolor="rgba(76,175,80,0.15)"), row=2, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="gray", row=2, col=1)
    fig.add_trace(go.Bar(x=pmc["date"], y=pmc["tss"], name="TSS diário",
                          marker_color="rgba(255,255,255,0.1)", showlegend=False), row=1, col=1)
    fig.update_layout(**PLOT_LAYOUT, height=600)
    st.plotly_chart(fig, use_container_width=True)

    # Ramp rate
    st.subheader("Ramp Rate (variação semanal do CTL)")
    pmc_weekly = pmc.set_index("date").resample("W").last().reset_index()
    pmc_weekly["ramp"] = pmc_weekly["ctl"].diff()
    colors_ramp = ["#4CAF50" if v >= 0 else "#F44336" for v in pmc_weekly["ramp"].fillna(0)]
    fig_ramp = go.Figure()
    fig_ramp.add_trace(go.Bar(x=pmc_weekly["date"], y=pmc_weekly["ramp"],
                               marker_color=colors_ramp, opacity=0.7, name="Ramp Rate"))
    fig_ramp.add_hline(y=5, line_dash="dash", line_color="orange",
                        annotation_text="Limite seguro (+5/sem)")
    fig_ramp.add_hline(y=-5, line_dash="dash", line_color="orange")
    fig_ramp.update_layout(**PLOT_LAYOUT, height=300)
    st.plotly_chart(fig_ramp, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: POTÊNCIA & EFICIÊNCIA
# ═══════════════════════════════════════════════════════════════
elif page == "⚡ Potência & Eficiência":
    st.title("Potência & Eficiência")
    bike = filter_by_date(cycling)
    valid = bike[bike["avg_power"].notna() & bike["avg_heart_rate"].notna()].copy()
    st.caption(f"📅 {start_date} → {end_date} • {len(valid)} treinos com potência")

    # EF over time
    st.subheader("Efficiency Factor (NP / FC)")
    ef_data = valid[valid["ef"].notna()].copy().sort_values("timestamp")
    if len(ef_data) > 0:
        fig_ef = go.Figure()
        fig_ef.add_trace(go.Scatter(x=ef_data["timestamp"], y=ef_data["ef"],
                                     mode="markers", name="EF",
                                     marker=dict(color=COLORS["ef"], size=5, opacity=0.5)))
        ef_data["ef_roll"] = ef_data["ef"].rolling(window=20, min_periods=5).mean()
        fig_ef.add_trace(go.Scatter(x=ef_data["timestamp"], y=ef_data["ef_roll"],
                                     mode="lines", name="Média móvel (20)",
                                     line=dict(color=COLORS["ef"], width=3)))
        fig_ef.update_layout(**PLOT_LAYOUT, height=400, yaxis_title="EF (NP/HR)")
        st.plotly_chart(fig_ef, use_container_width=True)

    # Quarterly power
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Potência por Trimestre")
        quarterly = valid.groupby("quarter").agg(
            avg_power=("avg_power", "mean"), np_power=("normalized_power", "mean"),
        ).round(0)
        fig_pw = go.Figure()
        fig_pw.add_trace(go.Bar(x=quarterly.index, y=quarterly["avg_power"],
                                 name="Avg Power", marker_color=COLORS["power"], opacity=0.7))
        fig_pw.add_trace(go.Bar(x=quarterly.index, y=quarterly["np_power"],
                                 name="NP", marker_color=COLORS["ctl"], opacity=0.7))
        fig_pw.update_layout(**PLOT_LAYOUT, height=350, barmode="group")
        st.plotly_chart(fig_pw, use_container_width=True)

    with col2:
        st.subheader("FC por Trimestre")
        quarterly_hr = valid.groupby("quarter").agg(avg_hr=("avg_heart_rate", "mean")).round(0)
        fig_hr = go.Figure()
        fig_hr.add_trace(go.Bar(x=quarterly_hr.index, y=quarterly_hr["avg_hr"],
                                 name="Avg HR", marker_color=COLORS["hr"], opacity=0.7))
        fig_hr.update_layout(**PLOT_LAYOUT, height=350)
        st.plotly_chart(fig_hr, use_container_width=True)

    # Decoupling
    dec_data = valid[valid["decoupling_pct"].notna()].sort_values("timestamp")
    if len(dec_data) > 0:
        st.markdown("---")
        st.subheader("Aerobic Decoupling (%)")
        fig_dec = go.Figure()
        fig_dec.add_trace(go.Scatter(
            x=dec_data["timestamp"], y=dec_data["decoupling_pct"],
            mode="markers", name="Decoupling %",
            marker=dict(color=dec_data["decoupling_pct"],
                        colorscale=[[0, "#4CAF50"], [0.05, "#FF9800"], [0.1, "#F44336"], [1, "#F44336"]],
                        cmin=0, cmax=15, size=6, opacity=0.6)))
        dec_data["dec_roll"] = dec_data["decoupling_pct"].rolling(window=15, min_periods=5).mean()
        fig_dec.add_trace(go.Scatter(x=dec_data["timestamp"], y=dec_data["dec_roll"],
                                      mode="lines", name="Média móvel (15)",
                                      line=dict(color=COLORS["ef"], width=2)))
        fig_dec.add_hline(y=5, line_dash="dash", line_color="green",
                          annotation_text="<5% = bom acoplamento")
        fig_dec.update_layout(**PLOT_LAYOUT, height=350, yaxis_title="Decoupling %")
        st.plotly_chart(fig_dec, use_container_width=True)

    # TSS vs EF scatter
    st.markdown("---")
    st.subheader("TSS vs EF")
    scatter_data = valid[valid["ef"].notna() & valid["training_stress_score"].notna()]
    if len(scatter_data) > 0:
        fig_scatter = px.scatter(
            scatter_data, x="training_stress_score", y="ef", color="year",
            size="duration_min", hover_data=["timestamp", "distance_km", "avg_power"],
            opacity=0.6, labels={"training_stress_score": "TSS", "ef": "EF", "year": "Ano"},
        )
        fig_scatter.update_layout(**PLOT_LAYOUT, height=400)
        st.plotly_chart(fig_scatter, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: RECOVERY & SONO (NEW — Whoop data)
# ═══════════════════════════════════════════════════════════════
elif page == "💚 Recovery & Sono":
    st.title("Recovery & Sono (Whoop)")

    whoop = load_whoop()
    if whoop.empty:
        st.warning("⚠️ Sem dados Whoop.")
        st.stop()

    w = filter_pmc_by_date(whoop)
    st.caption(f"📅 {start_date} → {end_date} • {len(w)} dias")

    # KPIs
    recent = w.tail(7)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Recovery (7d)", f"{recent['recovery_score'].mean():.0f}%")
    col2.metric("HRV (7d)", f"{recent['hrv'].mean():.0f} ms")
    col3.metric("RHR (7d)", f"{recent['resting_hr'].mean():.0f} bpm")
    col4.metric("Sono (7d)", f"{recent['sleep_duration_min'].mean():.0f} min")

    st.markdown("---")

    # Recovery + HRV over time
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
        row_heights=[0.35, 0.35, 0.3],
        subplot_titles=("Recovery Score (%)", "HRV (ms)", "Sono (min)"),
    )

    fig.add_trace(go.Scatter(x=w["date"], y=w["recovery_score"], name="Recovery",
                              line=dict(color=COLORS["recovery"], width=1), opacity=0.4), row=1, col=1)
    w_sorted = w.sort_values("date")
    w_sorted["rec_roll"] = w_sorted["recovery_score"].rolling(7, min_periods=3).mean()
    fig.add_trace(go.Scatter(x=w_sorted["date"], y=w_sorted["rec_roll"], name="Recovery 7d",
                              line=dict(color=COLORS["recovery"], width=3)), row=1, col=1)

    fig.add_trace(go.Scatter(x=w["date"], y=w["hrv"], name="HRV",
                              line=dict(color=COLORS["hrv"], width=1), opacity=0.4), row=2, col=1)
    w_sorted["hrv_roll"] = w_sorted["hrv"].rolling(7, min_periods=3).mean()
    fig.add_trace(go.Scatter(x=w_sorted["date"], y=w_sorted["hrv_roll"], name="HRV 7d",
                              line=dict(color=COLORS["hrv"], width=3)), row=2, col=1)

    fig.add_trace(go.Bar(x=w["date"], y=w["sleep_duration_min"], name="Sono",
                          marker_color=COLORS["sleep"], opacity=0.5), row=3, col=1)
    w_sorted["sleep_roll"] = w_sorted["sleep_duration_min"].rolling(7, min_periods=3).mean()
    fig.add_trace(go.Scatter(x=w_sorted["date"], y=w_sorted["sleep_roll"], name="Sono 7d",
                              line=dict(color=COLORS["sleep"], width=3)), row=3, col=1)

    fig.update_layout(**PLOT_LAYOUT, height=700)
    st.plotly_chart(fig, use_container_width=True)

    # Sleep stages
    st.subheader("Estágios de Sono")
    sleep_cols = ["sleep_deep_min", "sleep_rem_min", "sleep_light_min", "sleep_awake_min"]
    if all(c in w.columns for c in sleep_cols):
        monthly_sleep = w.set_index("date").resample("ME")[sleep_cols].mean().reset_index()
        fig_sleep = go.Figure()
        colors_sleep = ["#1A237E", "#4A148C", "#7E57C2", "#E0E0E0"]
        names_sleep = ["Deep", "REM", "Light", "Awake"]
        for col, color, name in zip(sleep_cols, colors_sleep, names_sleep):
            fig_sleep.add_trace(go.Bar(x=monthly_sleep["date"], y=monthly_sleep[col],
                                        name=name, marker_color=color, opacity=0.8))
        fig_sleep.update_layout(**PLOT_LAYOUT, height=350, barmode="stack",
                                 yaxis_title="Minutos")
        st.plotly_chart(fig_sleep, use_container_width=True)

    # Recovery vs TSB correlation
    st.markdown("---")
    st.subheader("Recovery vs TSB")
    pmc = load_pmc()
    if not pmc.empty:
        merged = pd.merge(w[["date", "recovery_score"]], pmc[["date", "tsb"]],
                          on="date", how="inner")
        merged = merged.dropna()
        if len(merged) > 10:
            fig_corr = px.scatter(merged, x="tsb", y="recovery_score",
                                  trendline="ols", opacity=0.4,
                                  labels={"tsb": "TSB (Form)", "recovery_score": "Whoop Recovery %"})
            fig_corr.update_layout(**PLOT_LAYOUT, height=350)
            st.plotly_chart(fig_corr, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: EXAMES
# ═══════════════════════════════════════════════════════════════
elif page == "🩸 Exames":
    st.title("Exames de Sangue")
    labs = load_lab_results()

    if labs is None or labs.empty:
        st.info("Sem dados de exames ainda. Use `ingest_exam.py` pra adicionar.")
        st.stop()

    markers = labs["marker"].unique()
    selected = st.multiselect("Marcadores", markers, default=list(markers)[:6])

    filtered = labs[labs["marker"].isin(selected)]
    for marker in selected:
        mdata = filtered[filtered["marker"] == marker].sort_values("date")
        if len(mdata) > 0:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=mdata["date"], y=mdata["value"],
                                      mode="lines+markers", name=marker,
                                      line=dict(width=2)))
            # Add reference range
            if "ref_min" in mdata.columns and mdata["ref_min"].notna().any():
                fig.add_hline(y=mdata["ref_min"].iloc[0], line_dash="dash",
                              line_color="green", opacity=0.5)
            if "ref_max" in mdata.columns and mdata["ref_max"].notna().any():
                fig.add_hline(y=mdata["ref_max"].iloc[0], line_dash="dash",
                              line_color="red", opacity=0.5)
            unit = mdata["unit"].iloc[0] if "unit" in mdata.columns else ""
            fig.update_layout(**PLOT_LAYOUT, height=250, title=f"{marker} ({unit})",
                               margin=dict(l=60, r=20, t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: PESO
# ═══════════════════════════════════════════════════════════════
elif page == "⚖️ Peso":
    st.title("Evolução de Peso")
    st.caption(f"📅 {start_date} → {end_date}")
    weight = load_weight()

    if weight is None or weight.empty:
        st.info("Sem dados de peso. Use `ingest_weight.py` pra adicionar.")
        st.stop()

    if start_date and end_date:
        mask = (weight["date"].dt.date >= start_date) & (weight["date"].dt.date <= end_date)
        w = weight[mask].copy()
    else:
        w = weight.copy()

    recent_w = w[w["weight_kg"].notna()].tail(30)
    if len(recent_w) > 0:
        col1, col2, col3 = st.columns(3)
        col1.metric("Peso Atual", f"{recent_w['weight_kg'].iloc[-1]:.1f} kg")
        col2.metric("Média 30 dias", f"{recent_w['weight_kg'].mean():.1f} kg")
        col3.metric("Variação",
                     f"{recent_w['weight_kg'].iloc[-1] - recent_w['weight_kg'].iloc[0]:+.1f} kg")

    fig_w = go.Figure()
    fig_w.add_trace(go.Scatter(x=w["date"], y=w["weight_kg"], mode="lines", name="Peso",
                                line=dict(color=COLORS["weight"], width=1), opacity=0.4))
    w_sorted = w.sort_values("date")
    w_sorted["w_roll"] = w_sorted["weight_kg"].rolling(window=30, min_periods=7).mean()
    fig_w.add_trace(go.Scatter(x=w_sorted["date"], y=w_sorted["w_roll"], mode="lines",
                                name="Média 30 dias", line=dict(color=COLORS["ef"], width=3)))
    fig_w.update_layout(**PLOT_LAYOUT, height=400, yaxis_title="kg")
    st.plotly_chart(fig_w, use_container_width=True)


# ── Footer ──────────────────────────────────────────────────────
st.sidebar.markdown("---")
if st.sidebar.button("Sair", type="secondary"):
    st.session_state.pop("user", None)
    st.session_state.pop("access_token", None)
    st.rerun()
st.sidebar.caption("APGIA v3 • Supabase + Azure AD SSO")
"""
Cycling Analytics Dashboard v3
Streamlit + Plotly — reads from Supabase (apgia schema)
Run: streamlit run dashboard_v3.py

Requires:
  pip install streamlit plotly supabase pandas numpy
  Set SUPABASE_URL and SUPABASE_KEY env vars (or .streamlit/secrets.toml)
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
import datetime
from supabase import create_client
from urllib.parse import urlencode

# ── Config ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="APGIA — Cycling Analytics",
    page_icon="🚴‍♀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

SCHEMA = "apgia"

# Azure AD / Supabase Auth config
SUPABASE_URL = "https://rqiwrlygeduzaaejlmrx.supabase.co"
ALLOWED_EMAIL = "eu@annagraboski.com"


# ── Supabase connection (cached) ──────────────────────────────
@st.cache_resource
def get_sb():
    # Try streamlit secrets first, then env vars
    try:
        url = st.secrets["SUPABASE_URL"]
        key = st.secrets["SUPABASE_KEY"]
    except Exception:
        import os
        url = os.environ.get("SUPABASE_URL", SUPABASE_URL)
        key = os.environ.get("SUPABASE_KEY", "")
    if not key:
        st.error("Configure SUPABASE_KEY em .streamlit/secrets.toml ou variavel de ambiente.")
        st.stop()
    return create_client(url, key)


# ── Theme colors ────────────────────────────────────────────────
COLORS = {
    "ctl": "#2196F3",       # blue - fitness
    "atl": "#FF5722",       # red-orange - fatigue
    "tsb": "#4CAF50",       # green - form
    "power": "#9C27B0",     # purple
    "hr": "#F44336",        # red
    "ef": "#FF9800",        # orange
    "weight": "#607D8B",    # grey
    "cadence": "#00BCD4",   # cyan
    "tss": "#795548",       # brown
    "recovery": "#66BB6A",  # green
    "hrv": "#42A5F5",       # light blue
    "sleep": "#7E57C2",     # deep purple
}

PLOT_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", size=12),
    margin=dict(l=60, r=20, t=40, b=40),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)


# ── Data Loading (cached, from Supabase) ──────────────────────
@st.cache_data(ttl=300)
def load_cycling():
    sb = get_sb()
    result = sb.schema(SCHEMA).table("cycling_sessions").select("*").order("timestamp").execute()
    df = pd.DataFrame(result.data)
    if df.empty:
        return df
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = pd.to_datetime(df["date"])
    for col in ["avg_power", "normalized_power", "max_power", "training_stress_score",
                 "avg_heart_rate", "max_heart_rate", "avg_cadence", "duration_min",
                 "distance_km", "total_ascent", "total_descent", "total_calories",
                 "ef", "decoupling_pct", "intensity_factor", "ftp"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["weekday"] = df["timestamp"].dt.day_name()
    df["month"] = df["timestamp"].dt.to_period("M").astype(str)
    df["quarter"] = df["timestamp"].dt.to_period("Q").astype(str)
    df["year"] = df["timestamp"].dt.year
    return df


@st.cache_data(ttl=300)
def load_pmc():
    sb = get_sb()
    result = sb.schema(SCHEMA).table("pmc_daily").select("*").order("date").execute()
    df = pd.DataFrame(result.data)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    for col in ["tss", "ctl", "atl", "tsb"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=300)
def load_whoop():
    sb = get_sb()
    result = sb.schema(SCHEMA).table("whoop_daily").select("*").order("date").execute()
    df = pd.DataFrame(result.data)
    if df.empty:
        return df
    df["date"] = pd.to_datetime(df["date"])
    for col in df.columns:
        if col != "date":
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


@st.cache_data(ttl=300)
def load_weight():
    sb = get_sb()
    result = sb.schema(SCHEMA).table("weight_daily").select("*").order("date").execute()
    df = pd.DataFrame(result.data)
    if df.empty:
        return None
    df["date"] = pd.to_datetime(df["date"])
    df["weight_kg"] = pd.to_numeric(df["weight_kg"], errors="coerce")
    return df


@st.cache_data(ttl=300)
def load_lab_results():
    sb = get_sb()
    result = sb.schema(SCHEMA).table("lab_results").select("*").order("date").execute()
    df = pd.DataFrame(result.data)
    if df.empty:
        return None
    df["date"] = pd.to_datetime(df["date"])
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df


# ── Auth Gate ──────────────────────────────────────────────────
auth_guard()

# ── Sidebar ─────────────────────────────────────────────────────
st.sidebar.title("🚴‍♀️ APGIA")
st.sidebar.caption("Saude & Performance")

page = st.sidebar.radio(
    "Navegação",
    [
        "📊 Visão Geral",
        "📈 PMC (Fitness/Fadiga)",
        "⚡ Potência & Eficiência",
        "💚 Recovery & Sono",
        "🩸 Exames",
        "⚖️ Peso",
    ],
)

# Date filter
try:
    cycling = load_cycling()
    if cycling.empty:
        st.error("⚠️ Sem dados em cycling_sessions.")
        st.stop()

    min_date = cycling["timestamp"].min().date()
    max_date = cycling["timestamp"].max().date()

    st.sidebar.markdown("---")
    st.sidebar.subheader("📅 Período")

    preset = st.sidebar.radio(
        "Período",
        ["Tudo", "12m", "6m", "3m", "Custom"],
        horizontal=True,
        index=0,
        label_visibility="collapsed",
    )
    if preset == "Tudo":
        start_date, end_date = min_date, max_date
    elif preset == "12m":
        start_date = max_date - datetime.timedelta(days=365)
        end_date = max_date
    elif preset == "6m":
        start_date = max_date - datetime.timedelta(days=180)
        end_date = max_date
    elif preset == "3m":
        start_date = max_date - datetime.timedelta(days=90)
        end_date = max_date
    else:
        date_range = st.sidebar.date_input(
            "Período",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
        )
        start_date, end_date = (date_range if len(date_range) == 2 else (min_date, max_date))

    st.sidebar.caption(f"{start_date} → {end_date}")

except Exception as e:
    st.error(f"⚠️ Erro ao carregar dados: {e}")
    st.stop()


def filter_by_date(df, date_col="timestamp"):
    if start_date and end_date:
        mask = (df[date_col].dt.date >= start_date) & (df[date_col].dt.date <= end_date)
        return df[mask].copy()
    return df.copy()


def filter_pmc_by_date(df):
    if start_date and end_date:
        mask = (df["date"].dt.date >= start_date) & (df["date"].dt.date <= end_date)
        return df[mask].copy()
    return df.copy()


# ═══════════════════════════════════════════════════════════════
# PAGE: VISÃO GERAL
# ═══════════════════════════════════════════════════════════════
if page == "📊 Visão Geral":
    bike = filter_by_date(cycling)

    st.title("Visão Geral")
    st.caption(f"📅 {start_date} → {end_date} • {len(bike)} treinos")

    # KPIs
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Treinos", f"{len(bike)}")
    col2.metric("Distância", f"{bike['distance_km'].sum():,.0f} km")
    col3.metric("Horas", f"{bike['duration_min'].sum() / 60:,.0f}h")
    col4.metric("Elevação", f"{bike['total_ascent'].sum():,.0f} m")
    col5.metric("Calorias", f"{bike['total_calories'].sum():,.0f} kcal")

    st.markdown("---")

    # Monthly volume
    monthly = bike.set_index("timestamp").resample("ME").agg(
        treinos=("distance_km", "count"),
        km=("distance_km", "sum"),
        horas=("duration_min", lambda x: x.sum() / 60),
        tss=("training_stress_score", "sum"),
        elevacao=("total_ascent", "sum"),
    ).reset_index()

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
        subplot_titles=("Volume Mensal (km)", "TSS Mensal"),
    )
    fig.add_trace(
        go.Bar(x=monthly["timestamp"], y=monthly["km"], name="Distância (km)",
               marker_color=COLORS["ctl"], opacity=0.8),
        row=1, col=1,
    )
    fig.add_trace(
        go.Bar(x=monthly["timestamp"], y=monthly["tss"], name="TSS",
               marker_color=COLORS["tss"], opacity=0.8),
        row=2, col=1,
    )
    fig.update_layout(**PLOT_LAYOUT, height=500)
    st.plotly_chart(fig, use_container_width=True)

    # Weekday distribution
    col1, col2 = st.columns(2)
    with col1:
        weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        weekday_labels = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        by_day = bike.groupby("weekday").agg(treinos=("distance_km", "count")).reindex(weekday_order)
        fig_day = go.Figure(go.Bar(
            x=weekday_labels, y=by_day["treinos"].values,
            marker_color=COLORS["ctl"], opacity=0.8,
        ))
        fig_day.update_layout(**PLOT_LAYOUT, height=300, title="Treinos por Dia da Semana")
        st.plotly_chart(fig_day, use_container_width=True)

    with col2:
        bins = [0, 20, 40, 60, 80, 100, 150, 300]
        labels = ["<20", "20-40", "40-60", "60-80", "80-100", "100-150", "150+"]
        bike["dist_faixa"] = pd.cut(bike["distance_km"], bins=bins, labels=labels)
        dist_counts = bike["dist_faixa"].value_counts().reindex(labels).fillna(0)
        fig_dist = go.Figure(go.Bar(
            x=labels, y=dist_counts.values,
            marker_color=COLORS["power"], opacity=0.8,
        ))
        fig_dist.update_layout(**PLOT_LAYOUT, height=300, title="Distribuição de Distância (km)")
        st.plotly_chart(fig_dist, use_container_width=True)

    # Yearly summary
    st.subheader("Evolução Anual")
    yearly = bike.groupby("year").agg(
        treinos=("distance_km", "count"),
        km=("distance_km", "sum"),
        horas=("duration_min", lambda x: x.sum() / 60),
        power_avg=("avg_power", "mean"),
        hr_avg=("avg_heart_rate", "mean"),
        tss_avg=("training_stress_score", "mean"),
    ).round(1)
    st.dataframe(yearly, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: PMC
# ═══════════════════════════════════════════════════════════════
elif page == "📈 PMC (Fitness/Fadiga)":
    st.title("Performance Management Chart")
    st.caption(f"📅 {start_date} → {end_date}")

    pmc = filter_pmc_by_date(load_pmc())
    if pmc.empty:
        st.warning("⚠️ Sem dados PMC.")
        st.stop()

    last = pmc.iloc[-1]
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("CTL (Fitness)", f"{last['ctl']:.0f}")
    col2.metric("ATL (Fadiga)", f"{last['atl']:.0f}")
    col3.metric("TSB (Form)", f"{last['tsb']:.0f}")

    tsb_val = last["tsb"]
    if tsb_val > 15:
        estado = "🟢 Descansada"
    elif tsb_val > 0:
        estado = "🟡 Equilibrada"
    elif tsb_val > -15:
        estado = "🟠 Fadiga leve"
    else:
        estado = "🔴 Fadiga acumulada"
    col4.metric("Estado", estado)

    st.markdown("---")

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.05,
        row_heights=[0.7, 0.3], subplot_titles=("CTL / ATL", "TSB (Form)"),
    )
    fig.add_trace(go.Scatter(x=pmc["date"], y=pmc["ctl"], name="CTL (Fitness)",
                              line=dict(color=COLORS["ctl"], width=2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=pmc["date"], y=pmc["atl"], name="ATL (Fadiga)",
                              line=dict(color=COLORS["atl"], width=1.5, dash="dot")), row=1, col=1)
    fig.add_trace(go.Scatter(x=pmc["date"], y=pmc["tsb"], name="TSB (Form)",
                              line=dict(color=COLORS["tsb"], width=1.5),
                              fill="tozeroy", fillcolor="rgba(76,175,80,0.15)"), row=2, col=1)
    fig.add_hline(y=0, line_dash="dash", line_color="gray", row=2, col=1)
    fig.add_trace(go.Bar(x=pmc["date"], y=pmc["tss"], name="TSS diário",
                          marker_color="rgba(255,255,255,0.1)", showlegend=False), row=1, col=1)
    fig.update_layout(**PLOT_LAYOUT, height=600)
    st.plotly_chart(fig, use_container_width=True)

    # Ramp rate
    st.subheader("Ramp Rate (variação semanal do CTL)")
    pmc_weekly = pmc.set_index("date").resample("W").last().reset_index()
    pmc_weekly["ramp"] = pmc_weekly["ctl"].diff()
    colors_ramp = ["#4CAF50" if v >= 0 else "#F44336" for v in pmc_weekly["ramp"].fillna(0)]
    fig_ramp = go.Figure()
    fig_ramp.add_trace(go.Bar(x=pmc_weekly["date"], y=pmc_weekly["ramp"],
                               marker_color=colors_ramp, opacity=0.7, name="Ramp Rate"))
    fig_ramp.add_hline(y=5, line_dash="dash", line_color="orange",
                        annotation_text="Limite seguro (+5/sem)")
    fig_ramp.add_hline(y=-5, line_dash="dash", line_color="orange")
    fig_ramp.update_layout(**PLOT_LAYOUT, height=300)
    st.plotly_chart(fig_ramp, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: POTÊNCIA & EFICIÊNCIA
# ═══════════════════════════════════════════════════════════════
elif page == "⚡ Potência & Eficiência":
    st.title("Potência & Eficiência")
    bike = filter_by_date(cycling)
    valid = bike[bike["avg_power"].notna() & bike["avg_heart_rate"].notna()].copy()
    st.caption(f"📅 {start_date} → {end_date} • {len(valid)} treinos com potência")

    # EF over time
    st.subheader("Efficiency Factor (NP / FC)")
    ef_data = valid[valid["ef"].notna()].copy().sort_values("timestamp")
    if len(ef_data) > 0:
        fig_ef = go.Figure()
        fig_ef.add_trace(go.Scatter(x=ef_data["timestamp"], y=ef_data["ef"],
                                     mode="markers", name="EF",
                                     marker=dict(color=COLORS["ef"], size=5, opacity=0.5)))
        ef_data["ef_roll"] = ef_data["ef"].rolling(window=20, min_periods=5).mean()
        fig_ef.add_trace(go.Scatter(x=ef_data["timestamp"], y=ef_data["ef_roll"],
                                     mode="lines", name="Média móvel (20)",
                                     line=dict(color=COLORS["ef"], width=3)))
        fig_ef.update_layout(**PLOT_LAYOUT, height=400, yaxis_title="EF (NP/HR)")
        st.plotly_chart(fig_ef, use_container_width=True)

    # Quarterly power
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Potência por Trimestre")
        quarterly = valid.groupby("quarter").agg(
            avg_power=("avg_power", "mean"), np_power=("normalized_power", "mean"),
        ).round(0)
        fig_pw = go.Figure()
        fig_pw.add_trace(go.Bar(x=quarterly.index, y=quarterly["avg_power"],
                                 name="Avg Power", marker_color=COLORS["power"], opacity=0.7))
        fig_pw.add_trace(go.Bar(x=quarterly.index, y=quarterly["np_power"],
                                 name="NP", marker_color=COLORS["ctl"], opacity=0.7))
        fig_pw.update_layout(**PLOT_LAYOUT, height=350, barmode="group")
        st.plotly_chart(fig_pw, use_container_width=True)

    with col2:
        st.subheader("FC por Trimestre")
        quarterly_hr = valid.groupby("quarter").agg(avg_hr=("avg_heart_rate", "mean")).round(0)
        fig_hr = go.Figure()
        fig_hr.add_trace(go.Bar(x=quarterly_hr.index, y=quarterly_hr["avg_hr"],
                                 name="Avg HR", marker_color=COLORS["hr"], opacity=0.7))
        fig_hr.update_layout(**PLOT_LAYOUT, height=350)
        st.plotly_chart(fig_hr, use_container_width=True)

    # Decoupling
    dec_data = valid[valid["decoupling_pct"].notna()].sort_values("timestamp")
    if len(dec_data) > 0:
        st.markdown("---")
        st.subheader("Aerobic Decoupling (%)")
        fig_dec = go.Figure()
        fig_dec.add_trace(go.Scatter(
            x=dec_data["timestamp"], y=dec_data["decoupling_pct"],
            mode="markers", name="Decoupling %",
            marker=dict(color=dec_data["decoupling_pct"],
                        colorscale=[[0, "#4CAF50"], [0.05, "#FF9800"], [0.1, "#F44336"], [1, "#F44336"]],
                        cmin=0, cmax=15, size=6, opacity=0.6)))
        dec_data["dec_roll"] = dec_data["decoupling_pct"].rolling(window=15, min_periods=5).mean()
        fig_dec.add_trace(go.Scatter(x=dec_data["timestamp"], y=dec_data["dec_roll"],
                                      mode="lines", name="Média móvel (15)",
                                      line=dict(color=COLORS["ef"], width=2)))
        fig_dec.add_hline(y=5, line_dash="dash", line_color="green",
                          annotation_text="<5% = bom acoplamento")
        fig_dec.update_layout(**PLOT_LAYOUT, height=350, yaxis_title="Decoupling %")
        st.plotly_chart(fig_dec, use_container_width=True)

    # TSS vs EF scatter
    st.markdown("---")
    st.subheader("TSS vs EF")
    scatter_data = valid[valid["ef"].notna() & valid["training_stress_score"].notna()]
    if len(scatter_data) > 0:
        fig_scatter = px.scatter(
            scatter_data, x="training_stress_score", y="ef", color="year",
            size="duration_min", hover_data=["timestamp", "distance_km", "avg_power"],
            opacity=0.6, labels={"training_stress_score": "TSS", "ef": "EF", "year": "Ano"},
        )
        fig_scatter.update_layout(**PLOT_LAYOUT, height=400)
        st.plotly_chart(fig_scatter, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: RECOVERY & SONO (NEW — Whoop data)
# ═══════════════════════════════════════════════════════════════
elif page == "💚 Recovery & Sono":
    st.title("Recovery & Sono (Whoop)")

    whoop = load_whoop()
    if whoop.empty:
        st.warning("⚠️ Sem dados Whoop.")
        st.stop()

    w = filter_pmc_by_date(whoop)
    st.caption(f"📅 {start_date} → {end_date} • {len(w)} dias")

    # KPIs
    recent = w.tail(7)
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Recovery (7d)", f"{recent['recovery_score'].mean():.0f}%")
    col2.metric("HRV (7d)", f"{recent['hrv'].mean():.0f} ms")
    col3.metric("RHR (7d)", f"{recent['resting_hr'].mean():.0f} bpm")
    col4.metric("Sono (7d)", f"{recent['sleep_duration_min'].mean():.0f} min")

    st.markdown("---")

    # Recovery + HRV over time
    fig = make_subplots(
        rows=3, cols=1, shared_xaxes=True, vertical_spacing=0.05,
        row_heights=[0.35, 0.35, 0.3],
        subplot_titles=("Recovery Score (%)", "HRV (ms)", "Sono (min)"),
    )

    fig.add_trace(go.Scatter(x=w["date"], y=w["recovery_score"], name="Recovery",
                              line=dict(color=COLORS["recovery"], width=1), opacity=0.4), row=1, col=1)
    w_sorted = w.sort_values("date")
    w_sorted["rec_roll"] = w_sorted["recovery_score"].rolling(7, min_periods=3).mean()
    fig.add_trace(go.Scatter(x=w_sorted["date"], y=w_sorted["rec_roll"], name="Recovery 7d",
                              line=dict(color=COLORS["recovery"], width=3)), row=1, col=1)

    fig.add_trace(go.Scatter(x=w["date"], y=w["hrv"], name="HRV",
                              line=dict(color=COLORS["hrv"], width=1), opacity=0.4), row=2, col=1)
    w_sorted["hrv_roll"] = w_sorted["hrv"].rolling(7, min_periods=3).mean()
    fig.add_trace(go.Scatter(x=w_sorted["date"], y=w_sorted["hrv_roll"], name="HRV 7d",
                              line=dict(color=COLORS["hrv"], width=3)), row=2, col=1)

    fig.add_trace(go.Bar(x=w["date"], y=w["sleep_duration_min"], name="Sono",
                          marker_color=COLORS["sleep"], opacity=0.5), row=3, col=1)
    w_sorted["sleep_roll"] = w_sorted["sleep_duration_min"].rolling(7, min_periods=3).mean()
    fig.add_trace(go.Scatter(x=w_sorted["date"], y=w_sorted["sleep_roll"], name="Sono 7d",
                              line=dict(color=COLORS["sleep"], width=3)), row=3, col=1)

    fig.update_layout(**PLOT_LAYOUT, height=700)
    st.plotly_chart(fig, use_container_width=True)

    # Sleep stages
    st.subheader("Estágios de Sono")
    sleep_cols = ["sleep_deep_min", "sleep_rem_min", "sleep_light_min", "sleep_awake_min"]
    if all(c in w.columns for c in sleep_cols):
        monthly_sleep = w.set_index("date").resample("ME")[sleep_cols].mean().reset_index()
        fig_sleep = go.Figure()
        colors_sleep = ["#1A237E", "#4A148C", "#7E57C2", "#E0E0E0"]
        names_sleep = ["Deep", "REM", "Light", "Awake"]
        for col, color, name in zip(sleep_cols, colors_sleep, names_sleep):
            fig_sleep.add_trace(go.Bar(x=monthly_sleep["date"], y=monthly_sleep[col],
                                        name=name, marker_color=color, opacity=0.8))
        fig_sleep.update_layout(**PLOT_LAYOUT, height=350, barmode="stack",
                                 yaxis_title="Minutos")
        st.plotly_chart(fig_sleep, use_container_width=True)

    # Recovery vs TSB correlation
    st.markdown("---")
    st.subheader("Recovery vs TSB")
    pmc = load_pmc()
    if not pmc.empty:
        merged = pd.merge(w[["date", "recovery_score"]], pmc[["date", "tsb"]],
                          on="date", how="inner")
        merged = merged.dropna()
        if len(merged) > 10:
            fig_corr = px.scatter(merged, x="tsb", y="recovery_score",
                                  trendline="ols", opacity=0.4,
                                  labels={"tsb": "TSB (Form)", "recovery_score": "Whoop Recovery %"})
            fig_corr.update_layout(**PLOT_LAYOUT, height=350)
            st.plotly_chart(fig_corr, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: EXAMES
# ═══════════════════════════════════════════════════════════════
elif page == "🩸 Exames":
    st.title("Exames de Sangue")
    labs = load_lab_results()

    if labs is None or labs.empty:
        st.info("Sem dados de exames ainda. Use `ingest_exam.py` pra adicionar.")
        st.stop()

    markers = labs["marker"].unique()
    selected = st.multiselect("Marcadores", markers, default=list(markers)[:6])

    filtered = labs[labs["marker"].isin(selected)]
    for marker in selected:
        mdata = filtered[filtered["marker"] == marker].sort_values("date")
        if len(mdata) > 0:
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=mdata["date"], y=mdata["value"],
                                      mode="lines+markers", name=marker,
                                      line=dict(width=2)))
            # Add reference range
            if "ref_min" in mdata.columns and mdata["ref_min"].notna().any():
                fig.add_hline(y=mdata["ref_min"].iloc[0], line_dash="dash",
                              line_color="green", opacity=0.5)
            if "ref_max" in mdata.columns and mdata["ref_max"].notna().any():
                fig.add_hline(y=mdata["ref_max"].iloc[0], line_dash="dash",
                              line_color="red", opacity=0.5)
            unit = mdata["unit"].iloc[0] if "unit" in mdata.columns else ""
            fig.update_layout(**PLOT_LAYOUT, height=250, title=f"{marker} ({unit})",
                               margin=dict(l=60, r=20, t=40, b=20))
            st.plotly_chart(fig, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: PESO
# ═══════════════════════════════════════════════════════════════
elif page == "⚖️ Peso":
    st.title("Evolução de Peso")
    st.caption(f"📅 {start_date} → {end_date}")
    weight = load_weight()

    if weight is None or weight.empty:
        st.info("Sem dados de peso. Use `ingest_weight.py` pra adicionar.")
        st.stop()

    if start_date and end_date:
        mask = (weight["date"].dt.date >= start_date) & (weight["date"].dt.date <= end_date)
        w = weight[mask].copy()
    else:
        w = weight.copy()

    recent_w = w[w["weight_kg"].notna()].tail(30)
    if len(recent_w) > 0:
        col1, col2, col3 = st.columns(3)
        col1.metric("Peso Atual", f"{recent_w['weight_kg'].iloc[-1]:.1f} kg")
        col2.metric("Média 30 dias", f"{recent_w['weight_kg'].mean():.1f} kg")
        col3.metric("Variação",
                     f"{recent_w['weight_kg'].iloc[-1] - recent_w['weight_kg'].iloc[0]:+.1f} kg")

    fig_w = go.Figure()
    fig_w.add_trace(go.Scatter(x=w["date"], y=w["weight_kg"], mode="lines", name="Peso",
                                line=dict(color=COLORS["weight"], width=1), opacity=0.4))
    w_sorted = w.sort_values("date")
    w_sorted["w_roll"] = w_sorted["weight_kg"].rolling(window=30, min_periods=7).mean()
    fig_w.add_trace(go.Scatter(x=w_sorted["date"], y=w_sorted["w_roll"], mode="lines",
                                name="Média 30 dias", line=dict(color=COLORS["ef"], width=3)))
    fig_w.update_layout(**PLOT_LAYOUT, height=400, yaxis_title="kg")
    st.plotly_chart(fig_w, use_container_width=True)


# ── Footer ──────────────────────────────────────────────────────
st.sidebar.markdown("---")
if st.sidebar.button("Sair", type="secondary"):
    st.session_state.pop("user", None)
    st.session_state.pop("access_token", None)
    st.rerun()
st.sidebar.caption("APGIA v3 • Supabase + Azure AD SSO")
