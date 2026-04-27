"""
Cycling Analytics Dashboard
Streamlit + Plotly — reads from data/processed/ CSVs
Run: streamlit run dashboard.py
"""
import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from pathlib import Path
import os

# ── Config ──────────────────────────────────────────────────────
st.set_page_config(
    page_title="Cycling Analytics",
    page_icon="🚴‍♀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

DATA_DIR = Path("data/processed")

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
    "bg": "#0E1117",        # dark bg
    "grid": "#1E1E1E",
}

PLOT_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter, sans-serif", size=12),
    margin=dict(l=60, r=20, t=40, b=40),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
)


# ── Data Loading (cached) ──────────────────────────────────────
@st.cache_data
def load_cycling():
    df = pd.read_csv(DATA_DIR / "cycling.csv")
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.date
    df["month"] = df["timestamp"].dt.to_period("M").astype(str)
    df["quarter"] = df["timestamp"].dt.to_period("Q").astype(str)
    df["year"] = df["timestamp"].dt.year
    return df


@st.cache_data
def load_pmc():
    df = pd.read_csv(DATA_DIR / "pmc.csv")
    df["date"] = pd.to_datetime(df["date"])
    return df


@st.cache_data
def load_weight():
    path = DATA_DIR / "weight_daily.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df["date"] = pd.to_datetime(df["date"])
    return df


@st.cache_data
def load_wprime():
    path = DATA_DIR / "wprime_balance.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


@st.cache_data
def load_gradient():
    path = DATA_DIR / "gradient_analysis.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    return df


@st.cache_data
def load_pacing():
    path = DATA_DIR / "pacing_analysis.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


@st.cache_data
def load_records_metrics():
    path = DATA_DIR / "records_metrics.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


# ── Sidebar ─────────────────────────────────────────────────────
st.sidebar.title("🚴‍♀️ Cycling Analytics")

# Check which data files exist
available = []
for name, path in [
    ("cycling.csv", DATA_DIR / "cycling.csv"),
    ("pmc.csv", DATA_DIR / "pmc.csv"),
    ("weight_daily.csv", DATA_DIR / "weight_daily.csv"),
    ("wprime_balance.csv", DATA_DIR / "wprime_balance.csv"),
    ("gradient_analysis.csv", DATA_DIR / "gradient_analysis.csv"),
    ("pacing_analysis.csv", DATA_DIR / "pacing_analysis.csv"),
    ("records_metrics.csv", DATA_DIR / "records_metrics.csv"),
]:
    if path.exists():
        available.append(name)

st.sidebar.caption(f"📂 {len(available)} datasets carregados")

# Navigation
page = st.sidebar.radio(
    "Navegação",
    [
        "📊 Visão Geral",
        "📈 PMC (Fitness/Fadiga)",
        "⚡ Potência & Eficiência",
        "⚖️ Peso",
        "🔋 W' Balance",
        "🏔️ Gradiente & Climbing",
        "🎯 Pacing",
    ],
)

# Date filter
try:
    cycling = load_cycling()
    min_date = cycling["timestamp"].min().date()
    max_date = cycling["timestamp"].max().date()

    st.sidebar.markdown("---")
    st.sidebar.subheader("Filtro de Período")
    date_range = st.sidebar.date_input(
        "Período",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date,
    )
    if len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date, end_date = min_date, max_date
except Exception:
    start_date, end_date = None, None
    st.error("⚠️ Não encontrei `data/processed/cycling.csv`. Rode os scripts de processamento primeiro.")
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
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.08,
        subplot_titles=("Volume Mensal (km)", "TSS Mensal"),
    )
    fig.add_trace(
        go.Bar(x=monthly["timestamp"], y=monthly["km"], name="Distância (km)",
               marker_color=COLORS["ctl"], opacity=0.8),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(x=monthly["timestamp"], y=monthly["horas"], name="Horas",
                   mode="lines+markers", line=dict(color=COLORS["ef"], width=2),
                   yaxis="y2"),
        row=1, col=1,
    )
    fig.add_trace(
        go.Bar(x=monthly["timestamp"], y=monthly["tss"], name="TSS",
               marker_color=COLORS["tss"], opacity=0.8),
        row=2, col=1,
    )
    fig.update_layout(**PLOT_LAYOUT, height=500, showlegend=True)
    st.plotly_chart(fig, use_container_width=True)

    # Weekday distribution
    col1, col2 = st.columns(2)

    with col1:
        weekday_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        weekday_labels = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]
        by_day = bike.groupby("weekday").agg(treinos=("distance_km", "count")).reindex(weekday_order)
        fig_day = go.Figure(go.Bar(
            x=weekday_labels,
            y=by_day["treinos"].values,
            marker_color=COLORS["ctl"],
            opacity=0.8,
        ))
        fig_day.update_layout(**PLOT_LAYOUT, height=300, title="Treinos por Dia da Semana")
        st.plotly_chart(fig_day, use_container_width=True)

    with col2:
        bins = [0, 20, 40, 60, 80, 100, 150, 300]
        labels = ["<20", "20-40", "40-60", "60-80", "80-100", "100-150", "150+"]
        bike["dist_faixa"] = pd.cut(bike["distance_km"], bins=bins, labels=labels)
        dist_counts = bike["dist_faixa"].value_counts().reindex(labels).fillna(0)
        fig_dist = go.Figure(go.Bar(
            x=labels,
            y=dist_counts.values,
            marker_color=COLORS["power"],
            opacity=0.8,
        ))
        fig_dist.update_layout(**PLOT_LAYOUT, height=300, title="Distribuição de Distância (km)")
        st.plotly_chart(fig_dist, use_container_width=True)

    # Year over year comparison
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

    try:
        pmc = filter_pmc_by_date(load_pmc())
    except Exception:
        st.warning("⚠️ pmc.csv não encontrado.")
        st.stop()

    # Current state
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

    # PMC Chart
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.7, 0.3],
        subplot_titles=("CTL / ATL", "TSB (Form)"),
    )

    fig.add_trace(
        go.Scatter(x=pmc["date"], y=pmc["ctl"], name="CTL (Fitness)",
                   line=dict(color=COLORS["ctl"], width=2)),
        row=1, col=1,
    )
    fig.add_trace(
        go.Scatter(x=pmc["date"], y=pmc["atl"], name="ATL (Fadiga)",
                   line=dict(color=COLORS["atl"], width=1.5, dash="dot")),
        row=1, col=1,
    )

    # TSB with color fill
    fig.add_trace(
        go.Scatter(x=pmc["date"], y=pmc["tsb"], name="TSB (Form)",
                   line=dict(color=COLORS["tsb"], width=1.5),
                   fill="tozeroy", fillcolor="rgba(76,175,80,0.15)"),
        row=2, col=1,
    )
    fig.add_hline(y=0, line_dash="dash", line_color="gray", row=2, col=1)

    # Daily TSS as faint bars behind CTL/ATL
    fig.add_trace(
        go.Bar(x=pmc["date"], y=pmc["tss"], name="TSS diário",
               marker_color="rgba(255,255,255,0.1)", showlegend=False),
        row=1, col=1,
    )

    fig.update_layout(**PLOT_LAYOUT, height=600)
    st.plotly_chart(fig, use_container_width=True)

    # Ramp rate
    st.subheader("Ramp Rate (variação semanal do CTL)")
    pmc_weekly = pmc.set_index("date").resample("W").last().reset_index()
    pmc_weekly["ramp"] = pmc_weekly["ctl"].diff()
    fig_ramp = go.Figure()
    colors_ramp = ["#4CAF50" if v >= 0 else "#F44336" for v in pmc_weekly["ramp"].fillna(0)]
    fig_ramp.add_trace(go.Bar(
        x=pmc_weekly["date"], y=pmc_weekly["ramp"],
        marker_color=colors_ramp, opacity=0.7, name="Ramp Rate",
    ))
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

    # EF over time
    st.subheader("Efficiency Factor (NP / FC)")
    if "ef" in valid.columns:
        ef_data = valid[valid["ef"].notna()].copy()

        fig_ef = go.Figure()
        fig_ef.add_trace(go.Scatter(
            x=ef_data["timestamp"], y=ef_data["ef"],
            mode="markers", name="EF",
            marker=dict(color=COLORS["ef"], size=5, opacity=0.5),
        ))

        # Rolling average
        ef_data = ef_data.sort_values("timestamp")
        ef_data["ef_roll"] = ef_data["ef"].rolling(window=20, min_periods=5).mean()
        fig_ef.add_trace(go.Scatter(
            x=ef_data["timestamp"], y=ef_data["ef_roll"],
            mode="lines", name="Média móvel (20 treinos)",
            line=dict(color=COLORS["ef"], width=3),
        ))
        fig_ef.update_layout(**PLOT_LAYOUT, height=400, yaxis_title="EF (NP/HR)")
        st.plotly_chart(fig_ef, use_container_width=True)

    # Power and HR trends
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Potência Média por Trimestre")
        quarterly = valid.groupby("quarter").agg(
            avg_power=("avg_power", "mean"),
            np_power=("normalized_power", "mean"),
        ).round(0)
        fig_pw = go.Figure()
        fig_pw.add_trace(go.Bar(
            x=quarterly.index, y=quarterly["avg_power"], name="Avg Power",
            marker_color=COLORS["power"], opacity=0.7,
        ))
        fig_pw.add_trace(go.Bar(
            x=quarterly.index, y=quarterly["np_power"], name="NP",
            marker_color=COLORS["ctl"], opacity=0.7,
        ))
        fig_pw.update_layout(**PLOT_LAYOUT, height=350, barmode="group")
        st.plotly_chart(fig_pw, use_container_width=True)

    with col2:
        st.subheader("FC Média por Trimestre")
        quarterly_hr = valid.groupby("quarter").agg(
            avg_hr=("avg_heart_rate", "mean"),
            max_hr=("max_heart_rate", "mean"),
        ).round(0)
        fig_hr = go.Figure()
        fig_hr.add_trace(go.Bar(
            x=quarterly_hr.index, y=quarterly_hr["avg_hr"], name="Avg HR",
            marker_color=COLORS["hr"], opacity=0.7,
        ))
        fig_hr.update_layout(**PLOT_LAYOUT, height=350)
        st.plotly_chart(fig_hr, use_container_width=True)

    # Decoupling
    rec_metrics = load_records_metrics()
    if rec_metrics is not None and "decoupling_pct" in rec_metrics.columns:
        st.markdown("---")
        st.subheader("Aerobic Decoupling (%)")
        dec = filter_by_date(rec_metrics)
        dec = dec[dec["decoupling_pct"].notna()].sort_values("timestamp")

        fig_dec = go.Figure()
        fig_dec.add_trace(go.Scatter(
            x=dec["timestamp"], y=dec["decoupling_pct"],
            mode="markers", name="Decoupling %",
            marker=dict(
                color=dec["decoupling_pct"],
                colorscale=[[0, "#4CAF50"], [0.05, "#FF9800"], [0.1, "#F44336"], [1, "#F44336"]],
                cmin=0, cmax=15,
                size=6, opacity=0.6,
            ),
        ))
        dec["dec_roll"] = dec["decoupling_pct"].rolling(window=15, min_periods=5).mean()
        fig_dec.add_trace(go.Scatter(
            x=dec["timestamp"], y=dec["dec_roll"],
            mode="lines", name="Média móvel (15)",
            line=dict(color=COLORS["ef"], width=2),
        ))
        fig_dec.add_hline(y=5, line_dash="dash", line_color="green",
                          annotation_text="<5% = bom acoplamento")
        fig_dec.update_layout(**PLOT_LAYOUT, height=350, yaxis_title="Decoupling %")
        st.plotly_chart(fig_dec, use_container_width=True)

    # TSS vs EF scatter
    st.markdown("---")
    st.subheader("TSS vs EF (carga vs eficiência)")
    if "ef" in valid.columns:
        scatter_data = valid[valid["ef"].notna() & valid["training_stress_score"].notna()]
        fig_scatter = px.scatter(
            scatter_data,
            x="training_stress_score", y="ef",
            color="year",
            size="duration_min",
            hover_data=["timestamp", "distance_km", "avg_power"],
            opacity=0.6,
            labels={"training_stress_score": "TSS", "ef": "EF", "year": "Ano"},
        )
        fig_scatter.update_layout(**PLOT_LAYOUT, height=400)
        st.plotly_chart(fig_scatter, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: PESO
# ═══════════════════════════════════════════════════════════════
elif page == "⚖️ Peso":
    st.title("Evolução de Peso")
    weight = load_weight()

    if weight is None:
        st.warning("⚠️ weight_daily.csv não encontrado.")
        st.stop()

    # Filter by date range
    if start_date and end_date:
        mask = (weight["date"].dt.date >= start_date) & (weight["date"].dt.date <= end_date)
        w = weight[mask].copy()
    else:
        w = weight.copy()

    # Current weight
    recent_w = w[w["weight"].notna()].tail(30)
    if len(recent_w) > 0:
        col1, col2, col3 = st.columns(3)
        col1.metric("Peso Atual", f"{recent_w['weight'].iloc[-1]:.1f} kg")
        col2.metric("Média 30 dias", f"{recent_w['weight'].mean():.1f} kg")
        col3.metric("Variação 30 dias",
                     f"{recent_w['weight'].iloc[-1] - recent_w['weight'].iloc[0]:+.1f} kg")

    fig_w = go.Figure()
    fig_w.add_trace(go.Scatter(
        x=w["date"], y=w["weight"],
        mode="lines", name="Peso diário",
        line=dict(color=COLORS["weight"], width=1),
        opacity=0.4,
    ))

    # 30-day rolling
    w_sorted = w.sort_values("date")
    w_sorted["weight_roll"] = w_sorted["weight"].rolling(window=30, min_periods=7).mean()
    fig_w.add_trace(go.Scatter(
        x=w_sorted["date"], y=w_sorted["weight_roll"],
        mode="lines", name="Média 30 dias",
        line=dict(color=COLORS["ef"], width=3),
    ))

    fig_w.update_layout(**PLOT_LAYOUT, height=400, yaxis_title="kg")
    st.plotly_chart(fig_w, use_container_width=True)

    # W/kg evolution if we have power data
    st.subheader("Impacto no W/kg")
    bike = filter_by_date(cycling)
    pw_rides = bike[bike["avg_power"].notna()].copy()
    if len(pw_rides) > 0 and len(w) > 0:
        # Merge weight to rides by nearest date
        w_lookup = w.set_index("date")["weight"]
        pw_rides["weight"] = pw_rides["timestamp"].dt.date.map(
            lambda d: w_lookup.asof(pd.Timestamp(d)) if pd.Timestamp(d) >= w_lookup.index.min() else np.nan
        )
        pw_rides = pw_rides[pw_rides["weight"].notna()]
        pw_rides["wkg"] = pw_rides["avg_power"] / pw_rides["weight"]

        quarterly_wkg = pw_rides.groupby("quarter").agg(
            wkg=("wkg", "mean"),
            weight=("weight", "mean"),
            power=("avg_power", "mean"),
        ).round(2)

        fig_wkg = make_subplots(specs=[[{"secondary_y": True}]])
        fig_wkg.add_trace(
            go.Bar(x=quarterly_wkg.index, y=quarterly_wkg["wkg"], name="W/kg",
                   marker_color=COLORS["power"], opacity=0.7),
            secondary_y=False,
        )
        fig_wkg.add_trace(
            go.Scatter(x=quarterly_wkg.index, y=quarterly_wkg["weight"], name="Peso (kg)",
                       line=dict(color=COLORS["weight"], width=2), mode="lines+markers"),
            secondary_y=True,
        )
        fig_wkg.update_layout(**PLOT_LAYOUT, height=350)
        fig_wkg.update_yaxes(title_text="W/kg", secondary_y=False)
        fig_wkg.update_yaxes(title_text="Peso (kg)", secondary_y=True)
        st.plotly_chart(fig_wkg, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: W' BALANCE
# ═══════════════════════════════════════════════════════════════
elif page == "🔋 W' Balance":
    st.title("W' Balance — Capacidade Anaeróbica")
    wprime = load_wprime()

    if wprime is None:
        st.warning("⚠️ wprime_balance.csv não encontrado.")
        st.stop()

    wp = filter_by_date(wprime)

    # Check available columns
    wp_cols = wp.columns.tolist()

    # Summary metrics
    if "wprime_min_pct" in wp_cols:
        pct_col = "wprime_min_pct"
    elif "min_wprime_pct" in wp_cols:
        pct_col = "min_wprime_pct"
    else:
        pct_col = None

    zeroed_col = None
    for candidate in ["zeroed", "wprime_zeroed", "hit_zero"]:
        if candidate in wp_cols:
            zeroed_col = candidate
            break

    if pct_col:
        col1, col2, col3 = st.columns(3)
        col1.metric("Treinos analisados", f"{len(wp)}")
        if zeroed_col:
            col2.metric("Zerou W'", f"{wp[zeroed_col].sum():.0f} treinos")
        col3.metric(f"W' mín. médio", f"{wp[pct_col].mean():.0f}%")

        # W' min % over time
        fig_wp = go.Figure()
        fig_wp.add_trace(go.Scatter(
            x=wp["timestamp"], y=wp[pct_col],
            mode="markers", name="W' mínimo (%)",
            marker=dict(
                color=wp[pct_col],
                colorscale=[[0, "#F44336"], [0.3, "#FF9800"], [0.7, "#4CAF50"], [1, "#2196F3"]],
                cmin=0, cmax=100,
                size=6, opacity=0.6,
                colorbar=dict(title="%"),
            ),
        ))
        fig_wp.add_hline(y=0, line_dash="solid", line_color="red")
        fig_wp.update_layout(**PLOT_LAYOUT, height=400, yaxis_title="W' Balance Mínimo (%)")
        st.plotly_chart(fig_wp, use_container_width=True)

        # By quarter
        wp["quarter"] = wp["timestamp"].dt.to_period("Q").astype(str)
        by_q = wp.groupby("quarter").agg(
            treinos=(pct_col, "count"),
            wprime_min_avg=(pct_col, "mean"),
        ).round(1)
        if zeroed_col:
            by_q_z = wp.groupby("quarter")[zeroed_col].sum()
            by_q["zeroed"] = by_q_z

        st.subheader("Resumo por Trimestre")
        st.dataframe(by_q, use_container_width=True)
    else:
        st.info(f"Colunas disponíveis: {wp_cols}")
        st.dataframe(wp.head(20))


# ═══════════════════════════════════════════════════════════════
# PAGE: GRADIENTE & CLIMBING
# ═══════════════════════════════════════════════════════════════
elif page == "🏔️ Gradiente & Climbing":
    st.title("Análise de Gradiente")
    gradient = load_gradient()

    if gradient is None:
        st.warning("⚠️ gradient_analysis.csv não encontrado.")
        st.stop()

    # Check what columns we have
    grad_cols = gradient.columns.tolist()

    # Try to identify gradient bin column
    grad_col = None
    for candidate in ["gradient_bin", "gradient_range", "gradient", "grad_bin"]:
        if candidate in grad_cols:
            grad_col = candidate
            break

    power_col = None
    for candidate in ["avg_power", "power_avg", "power", "mean_power"]:
        if candidate in grad_cols:
            power_col = candidate
            break

    if grad_col and power_col:
        fig_grad = go.Figure()

        # Power by gradient
        fig_grad.add_trace(go.Bar(
            x=gradient[grad_col].astype(str),
            y=gradient[power_col],
            marker_color=COLORS["power"],
            opacity=0.8,
            name="Potência média",
        ))

        fig_grad.update_layout(**PLOT_LAYOUT, height=400,
                                xaxis_title="Gradiente (%)",
                                yaxis_title="Potência (W)")
        st.plotly_chart(fig_grad, use_container_width=True)

        # Show VAM if available
        vam_col = None
        for candidate in ["vam", "avg_vam", "vam_avg"]:
            if candidate in grad_cols:
                vam_col = candidate
                break

        if vam_col:
            fig_vam = go.Figure()
            fig_vam.add_trace(go.Bar(
                x=gradient[grad_col].astype(str),
                y=gradient[vam_col],
                marker_color=COLORS["ctl"],
                opacity=0.8,
                name="VAM (m/h)",
            ))
            fig_vam.update_layout(**PLOT_LAYOUT, height=350,
                                   xaxis_title="Gradiente (%)",
                                   yaxis_title="VAM (m/h)")
            st.plotly_chart(fig_vam, use_container_width=True)
    else:
        st.info(f"Colunas disponíveis: {grad_cols}")
        st.dataframe(gradient.head(20))

    # Climbing distribution from rides
    st.markdown("---")
    st.subheader("Distribuição de Elevação por Treino")
    bike = filter_by_date(cycling)
    climb_data = bike[bike["total_ascent"].notna()]
    if len(climb_data) > 0:
        fig_climb = px.histogram(
            climb_data, x="total_ascent", nbins=30,
            labels={"total_ascent": "Elevação (m)"},
            color_discrete_sequence=[COLORS["ctl"]],
        )
        fig_climb.update_layout(**PLOT_LAYOUT, height=300)
        st.plotly_chart(fig_climb, use_container_width=True)


# ═══════════════════════════════════════════════════════════════
# PAGE: PACING
# ═══════════════════════════════════════════════════════════════
elif page == "🎯 Pacing":
    st.title("Análise de Pacing")
    pacing = load_pacing()

    if pacing is None:
        st.warning("⚠️ pacing_analysis.csv não encontrado.")
        st.stop()

    pac = filter_by_date(pacing)
    pac_cols = pac.columns.tolist()

    # VI over time
    vi_col = None
    for candidate in ["vi", "variability_index", "VI"]:
        if candidate in pac_cols:
            vi_col = candidate
            break

    if vi_col:
        col1, col2 = st.columns(2)
        col1.metric("VI médio", f"{pac[vi_col].mean():.3f}")
        col2.metric("Treinos", f"{len(pac)}")

        fig_vi = go.Figure()
        pac_sorted = pac.sort_values("timestamp")
        fig_vi.add_trace(go.Scatter(
            x=pac_sorted["timestamp"], y=pac_sorted[vi_col],
            mode="markers", name="VI",
            marker=dict(color=COLORS["cadence"], size=5, opacity=0.4),
        ))
        pac_sorted["vi_roll"] = pac_sorted[vi_col].rolling(window=20, min_periods=5).mean()
        fig_vi.add_trace(go.Scatter(
            x=pac_sorted["timestamp"], y=pac_sorted["vi_roll"],
            mode="lines", name="Média móvel (20)",
            line=dict(color=COLORS["cadence"], width=3),
        ))
        fig_vi.add_hline(y=1.05, line_dash="dash", line_color="green",
                         annotation_text="Pacing perfeito = 1.0")
        fig_vi.update_layout(**PLOT_LAYOUT, height=350, yaxis_title="Variability Index")
        st.plotly_chart(fig_vi, use_container_width=True)

    # Negative split %
    ns_col = None
    for candidate in ["negative_split", "is_negative_split", "neg_split"]:
        if candidate in pac_cols:
            ns_col = candidate
            break

    if ns_col:
        st.subheader("Negative Splits por Trimestre")
        pac["quarter"] = pac["timestamp"].dt.to_period("Q").astype(str)
        ns_by_q = pac.groupby("quarter").agg(
            treinos=(ns_col, "count"),
            neg_splits=(ns_col, "sum"),
        )
        ns_by_q["pct_neg_split"] = (ns_by_q["neg_splits"] / ns_by_q["treinos"] * 100).round(1)

        fig_ns = go.Figure()
        fig_ns.add_trace(go.Bar(
            x=ns_by_q.index, y=ns_by_q["pct_neg_split"],
            marker_color=COLORS["tsb"], opacity=0.8,
            name="% Negative Splits",
        ))
        fig_ns.update_layout(**PLOT_LAYOUT, height=300, yaxis_title="% Negative Splits")
        st.plotly_chart(fig_ns, use_container_width=True)

    # Terrain breakdown
    terrain_col = None
    for candidate in ["terrain", "terrain_type", "classification"]:
        if candidate in pac_cols:
            terrain_col = candidate
            break

    if terrain_col and vi_col:
        st.subheader("VI por Tipo de Terreno")
        by_terrain = pac.groupby(terrain_col).agg(
            treinos=(vi_col, "count"),
            vi_medio=(vi_col, "mean"),
        ).round(3)
        st.dataframe(by_terrain, use_container_width=True)

    if not vi_col:
        st.info(f"Colunas disponíveis: {pac_cols}")
        st.dataframe(pac.head(20))


# ── Footer ──────────────────────────────────────────────────────
st.sidebar.markdown("---")
st.sidebar.caption("Garmin AI Analytics • Built with Streamlit + Plotly")
