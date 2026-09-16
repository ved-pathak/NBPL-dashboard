"""
=============================================================================
CBG Plant Operations & Capital Planning Dashboard Tool
FILE: app.py
PURPOSE: Executive-grade Streamlit dashboard with dark-mode theme, custom
         glassmorphism KPI cards, and fully interactive Plotly charts.

VIEWS:
  1. Capital Planning, Solvency & Debt Risk Engine
  2. Feedstock Unit Economics & Quality RCA Hub

RUN: streamlit run app.py
=============================================================================
"""

import warnings
warnings.filterwarnings("ignore")

import os
import sys
import subprocess

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

# Ensure db_engine is importable from same directory
sys.path.insert(0, os.path.dirname(__file__))
import db_engine as dbe

# ---------------------------------------------------------------------------
# PAGE CONFIGURATION
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CBG Operations & Capital Planning Dashboard",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# CUSTOM CSS — Dark Mode + Glassmorphism KPI Cards
# ---------------------------------------------------------------------------
CUSTOM_CSS = """
<style>
/* ─── Global & Font ─────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Space+Grotesk:wght@400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
    background-color: #0a0f1e !important;
    color: #e2e8f0 !important;
}
.main { background-color: #0a0f1e !important; }
.block-container { padding: 1.5rem 2rem 2rem 2rem !important; max-width: 100% !important; }

/* ─── Sidebar ────────────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0d1b2a 0%, #0a1628 100%) !important;
    border-right: 1px solid rgba(56,189,248,0.15);
}
section[data-testid="stSidebar"] * { color: #cbd5e1 !important; }
section[data-testid="stSidebar"] h1, 
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 { color: #38bdf8 !important; }

/* ─── KPI Card Container ─────────────────────────────────────── */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1rem;
    margin-bottom: 1.5rem;
}
.kpi-card {
    background: linear-gradient(135deg, rgba(15,23,42,0.95) 0%, rgba(30,41,59,0.90) 100%);
    border: 1px solid rgba(56,189,248,0.20);
    border-radius: 16px;
    padding: 1.25rem 1.5rem;
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    box-shadow: 0 4px 24px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.05);
    transition: transform 0.2s ease, box-shadow 0.2s ease;
    position: relative;
    overflow: hidden;
}
.kpi-card:hover {
    transform: translateY(-3px);
    box-shadow: 0 8px 32px rgba(56,189,248,0.15), inset 0 1px 0 rgba(255,255,255,0.08);
}
.kpi-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 2px;
    background: var(--card-accent, linear-gradient(90deg, #38bdf8, #818cf8));
    border-radius: 16px 16px 0 0;
}
.kpi-label {
    font-size: 0.72rem;
    font-weight: 500;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #64748b;
    margin-bottom: 0.4rem;
}
.kpi-value {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.85rem;
    font-weight: 700;
    line-height: 1;
    margin-bottom: 0.3rem;
}
.kpi-delta {
    font-size: 0.78rem;
    font-weight: 500;
    padding: 2px 8px;
    border-radius: 20px;
    display: inline-block;
}
.kpi-delta.positive { background: rgba(34,197,94,0.15); color: #4ade80; }
.kpi-delta.negative { background: rgba(239,68,68,0.15); color: #f87171; }
.kpi-delta.warning  { background: rgba(251,191,36,0.15); color: #fbbf24; }
.kpi-delta.neutral  { background: rgba(100,116,139,0.15); color: #94a3b8; }

/* ─── Section Headers ────────────────────────────────────────── */
.section-header {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.0rem;
    font-weight: 600;
    color: #38bdf8;
    letter-spacing: 0.03em;
    text-transform: uppercase;
    margin: 1.5rem 0 0.75rem 0;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid rgba(56,189,248,0.2);
}
.page-title {
    font-family: 'Space Grotesk', sans-serif;
    font-size: 1.6rem;
    font-weight: 700;
    background: linear-gradient(135deg, #38bdf8 0%, #818cf8 50%, #c084fc 100%);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 0.25rem;
}
.page-subtitle {
    font-size: 0.82rem;
    color: #475569;
    margin-bottom: 1.5rem;
}

/* ─── Severity Badges ────────────────────────────────────────── */
.badge {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 20px;
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.04em;
}
.badge-critical  { background: rgba(239,68,68,0.2);  color: #f87171; border: 1px solid rgba(239,68,68,0.3); }
.badge-high      { background: rgba(251,146,60,0.2); color: #fb923c; border: 1px solid rgba(251,146,60,0.3); }
.badge-medium    { background: rgba(251,191,36,0.2); color: #fbbf24; border: 1px solid rgba(251,191,36,0.3); }
.badge-low       { background: rgba(34,197,94,0.2);  color: #4ade80; border: 1px solid rgba(34,197,94,0.3); }
.badge-healthy   { background: rgba(34,197,94,0.15); color: #4ade80; border: 1px solid rgba(34,197,94,0.25); }
.badge-tight     { background: rgba(251,191,36,0.15);color: #fbbf24; border: 1px solid rgba(251,191,36,0.25); }
.badge-breach    { background: rgba(239,68,68,0.15); color: #f87171; border: 1px solid rgba(239,68,68,0.25); }

/* ─── Plotly Chart Container ─────────────────────────────────── */
.chart-container {
    background: linear-gradient(135deg, rgba(15,23,42,0.95) 0%, rgba(22,33,52,0.90) 100%);
    border: 1px solid rgba(56,189,248,0.12);
    border-radius: 16px;
    padding: 0.5rem;
    margin-bottom: 1rem;
    box-shadow: 0 2px 16px rgba(0,0,0,0.3);
}

/* ─── DataFrame Styling ──────────────────────────────────────── */
[data-testid="stDataFrame"] { border-radius: 12px; overflow: hidden; }

/* ─── Divider ────────────────────────────────────────────────── */
hr { border-color: rgba(56,189,248,0.1) !important; margin: 1.5rem 0 !important; }

/* ─── Selectbox / Radio ──────────────────────────────────────── */
.stSelectbox > div > div, .stMultiSelect > div > div {
    background-color: rgba(15,23,42,0.8) !important;
    border: 1px solid rgba(56,189,248,0.2) !important;
    border-radius: 8px !important;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# PLOTLY DARK THEME DEFAULTS
# ---------------------------------------------------------------------------
PLOTLY_LAYOUT = dict(
    paper_bgcolor="rgba(10,15,30,0.0)",
    plot_bgcolor="rgba(10,15,30,0.0)",
    font=dict(family="Inter, sans-serif", color="#94a3b8", size=12),
    title_font=dict(family="Space Grotesk, sans-serif", color="#e2e8f0", size=14),
    legend=dict(
        bgcolor="rgba(15,23,42,0.8)",
        bordercolor="rgba(56,189,248,0.2)",
        borderwidth=1,
        font=dict(size=11),
    ),
    margin=dict(l=50, r=20, t=50, b=40),
    xaxis=dict(
        gridcolor="rgba(56,189,248,0.07)",
        zeroline=False,
        linecolor="rgba(56,189,248,0.15)",
        tickfont=dict(size=10),
    ),
    yaxis=dict(
        gridcolor="rgba(56,189,248,0.07)",
        zeroline=False,
        linecolor="rgba(56,189,248,0.15)",
        tickfont=dict(size=10),
    ),
    hoverlabel=dict(
        bgcolor="rgba(15,23,42,0.95)",
        bordercolor="rgba(56,189,248,0.3)",
        font=dict(family="Inter", size=12),
    ),
)

COLORS = {
    "primary":   "#38bdf8",
    "secondary": "#818cf8",
    "accent":    "#c084fc",
    "success":   "#4ade80",
    "warning":   "#fbbf24",
    "danger":    "#f87171",
    "orange":    "#fb923c",
    "teal":      "#2dd4bf",
    "yellow":    "#facc15",
    "gray":      "#475569",
}


# ---------------------------------------------------------------------------
# HELPER: KPI CARD HTML
# ---------------------------------------------------------------------------

def kpi_card(label: str, value: str, delta: str = "", delta_type: str = "neutral",
             accent: str = "#38bdf8,#818cf8", icon: str = "📊") -> str:
    """Render a KPI card using fully inline styles (compatible with Streamlit 1.33+)."""
    colors = accent.split(",")
    c1 = colors[0].strip()
    c2 = colors[1].strip() if len(colors) > 1 else c1

    delta_bg  = {"positive": "rgba(34,197,94,0.15)",  "negative": "rgba(239,68,68,0.15)",
                 "warning":  "rgba(251,191,36,0.15)",  "neutral":  "rgba(100,116,139,0.15)"}
    delta_col = {"positive": "#4ade80", "negative": "#f87171",
                 "warning":  "#fbbf24", "neutral":  "#94a3b8"}
    bg  = delta_bg.get(delta_type,  delta_bg["neutral"])
    col = delta_col.get(delta_type, delta_col["neutral"])

    delta_html = ""
    if delta:
        delta_html = (
            f'<div style="display:inline-block;padding:2px 10px;border-radius:20px;'
            f'font-size:0.76rem;font-weight:500;background:{bg};color:{col};'
            f'margin-top:0.35rem;">{delta}</div>'
        )

    return f"""
    <div style="
        background: linear-gradient(135deg, rgba(15,23,42,0.97) 0%, rgba(30,41,59,0.93) 100%);
        border: 1px solid rgba(56,189,248,0.20);
        border-top: 2px solid {c1};
        border-radius: 14px;
        padding: 1.2rem 1.4rem;
        box-shadow: 0 4px 20px rgba(0,0,0,0.35);
        flex: 1;
    ">
        <div style="font-size:0.68rem;font-weight:600;letter-spacing:0.09em;
                    text-transform:uppercase;color:#64748b;margin-bottom:0.4rem;">
            {icon}&nbsp;&nbsp;{label}
        </div>
        <div style="font-family:'Space Grotesk',sans-serif;font-size:1.75rem;
                    font-weight:700;color:#e2e8f0;line-height:1.1;">
            {value}
        </div>
        {delta_html}
    </div>
    """


def kpi_row(cards: list[dict]) -> None:
    """Render a row of KPI cards in Streamlit columns (no CSS grid dependency)."""
    cols = st.columns(len(cards))
    for col, c in zip(cols, cards):
        with col:
            st.markdown(kpi_card(**c), unsafe_allow_html=True)


def section_header(title: str) -> None:
    """Render a styled section header using inline styles."""
    st.markdown(
        f'<div style="font-size:0.85rem;font-weight:700;color:#38bdf8;'
        f'letter-spacing:0.05em;text-transform:uppercase;padding:0.5rem 0;'
        f'border-bottom:1px solid rgba(56,189,248,0.2);margin:1.2rem 0 0.8rem 0;">'
        f'◈ {title}</div>',
        unsafe_allow_html=True,
    )



# ---------------------------------------------------------------------------
# DATA LOADING (cached)
# ---------------------------------------------------------------------------

@st.cache_resource(show_spinner=False)
def load_engine():
    """Cache the database engine across sessions."""
    return dbe.get_engine()


@st.cache_data(ttl=300, show_spinner=False)
def load_all_data():
    """Load all datasets and KPIs in one pass."""
    eng = load_engine()
    return {
        "kpis":             dbe.get_kpi_summary(eng),
        "capex_scurve":     dbe.get_capex_scurve(eng),
        "capex_category":   dbe.get_capex_category_summary(eng),
        "dscr":             dbe.get_dscr_data(eng),
        "treasury":         dbe.get_treasury_logs(eng),
        "rolling_cash":     dbe.get_rolling_cash(eng),
        "production":       dbe.get_production_logs(eng),
        "feedstock_detail": dbe.get_feedstock_detail(eng),
        "supplier_rank":    dbe.get_supplier_ranking(eng),
        "rca_detail":       dbe.get_rca_detail(eng),
        "rca_summary":      dbe.get_rca_summary(eng),
    }


# ---------------------------------------------------------------------------
# CHECK DATABASE — Prompt to seed if missing
# ---------------------------------------------------------------------------

def check_database_ready() -> bool:
    """Check if database exists and is seeded."""
    db_path = dbe.DB_PATH
    if not db_path.exists():
        return False
    try:
        eng = dbe.get_engine()
        count = dbe.run_query("SELECT COUNT(*) AS cnt FROM digester_production_logs", eng)
        return int(count["cnt"].iloc[0]) > 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# SIDEBAR
# ---------------------------------------------------------------------------

def render_sidebar(data: dict) -> dict:
    """Render sidebar with navigation and filters. Returns filter state."""
    with st.sidebar:
        # Brand header
        st.markdown("""
        <div style="text-align:center; padding: 1rem 0 1.5rem 0;">
            <div style="font-family:'Space Grotesk',sans-serif; font-size:1.5rem;
                 font-weight:800; background:linear-gradient(135deg,#38bdf8,#c084fc);
                 -webkit-background-clip:text; -webkit-text-fill-color:transparent;">
                ⚙️ CBG Analytics
            </div>
            <div style="font-size:0.7rem; color:#475569; margin-top:0.25rem;
                 letter-spacing:0.1em; text-transform:uppercase;">
                Operations & Capital Planning Tool
            </div>
            <div style="font-size:0.65rem; color:#334155; margin-top:0.5rem;">
                Commercial 3.0 TPD Industrial Facility
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")

        # Navigation
        st.markdown("**Navigation**")
        page = st.radio(
            "Select View",
            options=[
                "🏦 Capital Planning & Solvency",
                "🌿 Feedstock Economics & RCA"
            ],
            label_visibility="collapsed",
        )

        st.markdown("---")

        # Date filter (operations period)
        prod_df = data["production"]
        if not prod_df.empty:
            min_date = prod_df["production_date"].min().date()
            max_date = prod_df["production_date"].max().date()
        else:
            from datetime import date
            min_date = date(2024, 1, 1)
            max_date = date(2024, 6, 28)

        st.markdown("**Operations Date Range**")
        date_range = st.date_input(
            "Filter Range",
            value=(min_date, max_date),
            min_value=min_date,
            max_value=max_date,
            label_visibility="collapsed",
        )

        if len(date_range) == 2:
            start_date, end_date = date_range
        else:
            start_date = end_date = date_range[0]

        st.markdown("---")

        # Anomaly highlight toggle
        show_anomalies = st.toggle("🔴 Highlight Anomaly Clusters", value=True)

        st.markdown("---")

        # Quick stats in sidebar
        kpis = data["kpis"]
        st.markdown("**Live KPIs**")
        col1, col2 = st.columns(2)
        with col1:
            st.metric("Avg CBG/Day", f"{kpis.get('avg_cbg_kg', 0):,.0f} kg")
            st.metric("DSCR (Latest)", f"{kpis.get('current_dscr', 0):.2f}x")
        with col2:
            st.metric("CUF %", f"{kpis.get('avg_cuf_pct', 0):.1f}%")
            st.metric("CH4 %", f"{kpis.get('avg_ch4_pct', 0):.1f}%")

        st.markdown("---")
        st.markdown(
            "<div style='font-size:0.65rem;color:#334155;text-align:center;'>"
            "Data through: 180-Day Operations Window<br>"
            "© 2024 Narmada Biofuels Pvt. Ltd.</div>",
            unsafe_allow_html=True,
        )

    return {
        "page":            page,
        "start_date":      pd.Timestamp(start_date),
        "end_date":        pd.Timestamp(end_date),
        "show_anomalies":  show_anomalies,
    }


# ---------------------------------------------------------------------------
# VIEW 1: CAPITAL PLANNING, SOLVENCY & DEBT RISK ENGINE
# ---------------------------------------------------------------------------

def render_view1(data: dict, filters: dict) -> None:
    """Render Capital Planning & Solvency view."""

    # ── Page Title
    st.markdown(
        '<div class="page-title">Capital Planning, Solvency & Debt Risk Engine</div>'
        '<div class="page-subtitle">CAPEX milestone tracking • DSCR covenant monitoring • '
        'Working capital treasury analysis — Narmada Biofuels Pvt. Ltd.</div>',
        unsafe_allow_html=True,
    )

    kpis = data["kpis"]

    # ── KPI Cards Row
    capex_delta_type = "negative" if kpis.get("capex_variance_pct", 0) > 5 else "positive"

    # DSCR — show peak healthy value with period label
    dscr_val    = kpis.get("current_dscr", 0)
    dscr_period = kpis.get("dscr_period", "")
    dscr_type   = "positive" if dscr_val >= 1.35 else ("warning" if dscr_val >= 1.25 else "negative")

    # Cash — show anomaly context when A3 is active
    anomaly_on  = kpis.get("anomaly_active", False)
    last_cash   = kpis.get("closing_cash_lakhs", 0)
    peak_cash   = kpis.get("peak_cash_lakhs", 0)
    cash_type   = "negative" if anomaly_on else ("positive" if last_cash > 10 else "warning")
    cash_delta  = (f"⚠ A3 Anomaly: ₹{last_cash:.1f}L (Peak: ₹{peak_cash:.1f}L)"
                   if anomaly_on else f"Peak Cash: ₹{peak_cash:.1f}L")

    runway      = kpis.get("cash_runway_days", 0)
    runway_type = "negative" if (anomaly_on or runway < 30) else ("warning" if runway < 60 else "positive")
    runway_val  = "⚠ A3 Active" if anomaly_on else f"{runway} days"

    kpi_row([
        dict(
            label="Total CAPEX Deployed",
            value=f"₹{kpis.get('capex_actual_lakhs', 0):.1f}L",
            delta=f"Budget: ₹{kpis.get('capex_budget_lakhs', 0):.1f}L  (+{kpis.get('capex_variance_pct', 0):.1f}%)",
            delta_type=capex_delta_type,
            accent="#38bdf8,#2dd4bf",
            icon="🏗️",
        ),
        dict(
            label=f"Peak DSCR ({dscr_period})",
            value=f"{dscr_val:.3f}x",
            delta=f"{kpis.get('dscr_status','N/A')} | Latest: {kpis.get('latest_dscr',0):.2f}x",
            delta_type=dscr_type,
            accent="#818cf8,#c084fc",
            icon="📊",
        ),
        dict(
            label="Daily Cash Burn",
            value=f"₹{kpis.get('daily_burn_inr', 0)/1000:.1f}K",
            delta=cash_delta,
            delta_type=cash_type,
            accent="#f87171,#fb923c",
            icon="🔥",
        ),
        dict(
            label="Liquidity Runway",
            value=runway_val,
            delta=kpis.get("liquidity_status", ""),
            delta_type=runway_type,
            accent="#4ade80,#38bdf8",
            icon="⏱️",
        ),
    ])


    # ── Row 1: S-Curve + Category Variance
    section_header("CAPEX S-Curve & Construction Burn Rate")
    col1, col2 = st.columns([2, 1])

    with col1:
        capex_df = data["capex_scurve"].copy()
        fig = go.Figure()

        # Planned S-curve
        fig.add_trace(go.Scatter(
            x=capex_df["target_date"],
            y=capex_df["cumulative_budget_lakhs"],
            name="Cumulative Budget (Planned)",
            mode="lines+markers",
            line=dict(color=COLORS["primary"], width=2.5, dash="dot"),
            marker=dict(size=5, color=COLORS["primary"]),
            hovertemplate="<b>%{x|%b %Y}</b><br>Planned: ₹%{y:.1f}L<extra></extra>",
        ))

        # Actual S-curve
        fig.add_trace(go.Scatter(
            x=capex_df["target_date"],
            y=capex_df["cumulative_actual_lakhs"],
            name="Cumulative Actual Spend",
            mode="lines+markers",
            line=dict(color=COLORS["danger"], width=2.5),
            marker=dict(size=6, color=COLORS["danger"]),
            fill="tonexty",
            fillcolor="rgba(248,113,113,0.07)",
            hovertemplate="<b>%{x|%b %Y}</b><br>Actual: ₹%{y:.1f}L<extra></extra>",
        ))

        # Annotate major overrun points
        overrun_df = capex_df[capex_df["variance_lakhs"] > 5]
        for _, row in overrun_df.iterrows():
            fig.add_annotation(
                x=row["target_date"],
                y=row["cumulative_actual_lakhs"],
                text=f"+₹{row['variance_lakhs']:.1f}L",
                showarrow=True,
                arrowhead=2,
                arrowcolor=COLORS["warning"],
                font=dict(size=9, color=COLORS["warning"]),
                bgcolor="rgba(15,23,42,0.8)",
                bordercolor=COLORS["warning"],
            )

        layout = dict(**PLOTLY_LAYOUT)
        layout.update(
            title="CAPEX S-Curve: Cumulative Planned vs. Actual Spend",
            xaxis_title="Project Timeline",
            yaxis_title="Cumulative Spend (₹ Lakhs)",
            height=340,
        )
        fig.update_layout(**layout)
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.plotly_chart(fig, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        cat_df = data["capex_category"]
        fig2   = go.Figure(go.Bar(
            x=cat_df["variance_pct"],
            y=cat_df["category"],
            orientation="h",
            marker=dict(
                color=[
                    COLORS["danger"] if v > 10 else
                    COLORS["warning"] if v > 5 else
                    COLORS["success"]
                    for v in cat_df["variance_pct"]
                ],
                line=dict(color="rgba(0,0,0,0)", width=0),
            ),
            text=[f"{v:+.1f}%" for v in cat_df["variance_pct"]],
            textposition="outside",
            textfont=dict(size=11, color="#94a3b8"),
            hovertemplate="<b>%{y}</b><br>Variance: %{x:.2f}%<extra></extra>",
        ))
        layout2 = dict(**PLOTLY_LAYOUT)
        layout2.update(
            title="Category Cost Variance %",
            height=340,
            xaxis_title="Variance (%)",
            margin=dict(l=10, r=60, t=50, b=40),
        )
        fig2.update_layout(**layout2)
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.plotly_chart(fig2, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Row 2: Treasury Cash + DSCR
    section_header("Treasury Cash Position & DSCR Covenant Monitoring")
    col3, col4 = st.columns([1, 1])

    with col3:
        cash_df = data["rolling_cash"].copy()
        # Apply date filter
        cash_df = cash_df[
            (cash_df["entry_date"] >= filters["start_date"]) &
            (cash_df["entry_date"] <= filters["end_date"])
        ]

        fig3 = go.Figure()

        # Fill area under curve — colour by stress
        fig3.add_trace(go.Scatter(
            x=cash_df["entry_date"],
            y=cash_df["closing_cash_lakhs"],
            name="Daily Closing Cash",
            mode="lines",
            line=dict(color=COLORS["primary"], width=1.5),
            fill="tozeroy",
            fillcolor="rgba(56,189,248,0.08)",
            hovertemplate="<b>%{x|%d %b %Y}</b><br>Cash: ₹%{y:.2f}L<extra></extra>",
        ))

        # 30-day rolling average
        fig3.add_trace(go.Scatter(
            x=cash_df["entry_date"],
            y=cash_df["rolling_30d_avg_lakhs"],
            name="30-Day Rolling Avg",
            mode="lines",
            line=dict(color=COLORS["secondary"], width=2, dash="dash"),
            hovertemplate="<b>%{x|%d %b %Y}</b><br>30D Avg: ₹%{y:.2f}L<extra></extra>",
        ))

        # DSR Reserve threshold line
        fig3.add_hline(
            y=5.0,
            line=dict(color=COLORS["danger"], width=1.5, dash="longdash"),
            annotation_text="⚠ Min DSR Reserve (₹5L)",
            annotation_position="top right",
            annotation_font=dict(size=10, color=COLORS["danger"]),
        )

        # Anomaly shading for payment delay
        if filters["show_anomalies"]:
            from datetime import date as dt
            a3_start = pd.Timestamp("2024-05-24")
            a3_end   = pd.Timestamp("2024-06-13")
            fig3.add_vrect(
                x0=a3_start, x1=a3_end,
                fillcolor="rgba(239,68,68,0.08)",
                line=dict(color="rgba(239,68,68,0.3)", width=1),
                annotation_text="[A3] PSU Payment\nDelay",
                annotation_position="top left",
                annotation_font=dict(size=9, color=COLORS["danger"]),
            )

        layout3 = dict(**PLOTLY_LAYOUT)
        layout3.update(
            title="30-Day Rolling Treasury Cash Balance",
            yaxis_title="Cash Position (₹ Lakhs)",
            height=340,
        )
        fig3.update_layout(**layout3)
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.plotly_chart(fig3, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col4:
        dscr_df = data["dscr"].copy()
        dscr_df = dscr_df[dscr_df["dscr"].notna()]

        fig4 = go.Figure()

        # Covenant zones as filled rectangles
        if not dscr_df.empty:
            # Green zone: DSCR ≥ 1.35
            fig4.add_hrect(
                y0=1.35, y1=2.5,
                fillcolor="rgba(74,222,128,0.06)",
                line_width=0,
            )
            # Yellow zone: 1.25–1.35
            fig4.add_hrect(
                y0=1.25, y1=1.35,
                fillcolor="rgba(251,191,36,0.08)",
                line_width=0,
            )
            # Red zone: <1.25
            fig4.add_hrect(
                y0=0.0, y1=1.25,
                fillcolor="rgba(239,68,68,0.07)",
                line_width=0,
            )

        # Covenant threshold line
        fig4.add_hline(
            y=1.25,
            line=dict(color=COLORS["danger"], width=1.5, dash="longdash"),
            annotation_text="Covenant Threshold (1.25x)",
            annotation_position="bottom right",
            annotation_font=dict(size=10, color=COLORS["danger"]),
        )

        # DSCR bars coloured by status
        bar_colors = []
        for _, row in dscr_df.iterrows():
            if str(row.get("dscr_status","")) == "Healthy":
                bar_colors.append(COLORS["success"])
            elif str(row.get("dscr_status","")) == "Tight Buffer":
                bar_colors.append(COLORS["warning"])
            else:
                bar_colors.append(COLORS["danger"])

        fig4.add_trace(go.Bar(
            x=dscr_df["year_month"],
            y=dscr_df["dscr"],
            name="Monthly DSCR",
            marker=dict(color=bar_colors, opacity=0.75, line=dict(width=0)),
            hovertemplate="<b>%{x}</b><br>DSCR: %{y:.3f}x<extra></extra>",
        ))

        # Rolling DSCR trend line
        if "dscr_3m_rolling" in dscr_df.columns:
            fig4.add_trace(go.Scatter(
                x=dscr_df["year_month"],
                y=dscr_df["dscr_3m_rolling"],
                name="3M Rolling DSCR",
                mode="lines+markers",
                line=dict(color=COLORS["primary"], width=2.5),
                marker=dict(size=6),
                hovertemplate="<b>%{x}</b><br>3M DSCR: %{y:.3f}x<extra></extra>",
            ))

        layout4 = dict(**PLOTLY_LAYOUT)
        layout4.update(
            title="Monthly DSCR vs. Covenant Threshold (1.25x)",
            yaxis_title="Debt Service Coverage Ratio",
            height=340,
            yaxis=dict(range=[0, max(2.5, float(dscr_df["dscr"].max()) * 1.15 if not dscr_df.empty else 2.5)]),
        )
        fig4.update_layout(**layout4)
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.plotly_chart(fig4, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Deep Dive: Milestone Ledger + DSCR Table
    section_header("Working Capital & Milestone Ledger")
    col5, col6 = st.columns([3, 2])

    with col5:
        st.markdown(
            "<span style='font-size:0.8rem;color:#64748b;'>All CAPEX Milestones — "
            "Sorted by cost overrun severity</span>",
            unsafe_allow_html=True,
        )
        capex_ledger = data["capex_scurve"][[
            "category", "milestone_name", "vendor_name",
            "budget_lakhs", "actual_lakhs", "variance_lakhs",
            "variance_pct", "overrun_severity", "schedule_delay_days",
            "milestone_status"
        ]].copy()
        capex_ledger = capex_ledger.sort_values("variance_pct", ascending=False)

        # Apply badge styling inline
        def style_severity(row):
            sev = str(row.get("overrun_severity", ""))
            if "Critical" in sev:
                return ["background-color: rgba(239,68,68,0.12)"] * len(row)
            elif "High" in sev:
                return ["background-color: rgba(251,146,60,0.10)"] * len(row)
            elif "Moderate" in sev:
                return ["background-color: rgba(251,191,36,0.08)"] * len(row)
            return [""] * len(row)

        styled = capex_ledger.style.apply(style_severity, axis=1).format({
            "budget_lakhs":   "₹{:.2f}L",
            "actual_lakhs":   "₹{:.2f}L",
            "variance_lakhs": "₹{:+.2f}L",
            "variance_pct":   "{:+.1f}%",
        })
        st.dataframe(styled, height=320, use_container_width=True)

    with col6:
        st.markdown(
            "<span style='font-size:0.8rem;color:#64748b;'>Monthly DSCR Health — "
            "Covenant monitoring table</span>",
            unsafe_allow_html=True,
        )
        dscr_table = data["dscr"][[
            "year_month", "revenue_lakhs", "ebitda_lakhs",
            "debt_service_lakhs", "dscr", "dscr_status",
            "closing_cash_lakhs", "avg_collection_days",
        ]].copy()

        def style_dscr(row):
            status = str(row.get("dscr_status",""))
            if "Breach" in status or "Critical" in status:
                return ["background-color: rgba(239,68,68,0.12)"] * len(row)
            elif "Tight" in status:
                return ["background-color: rgba(251,191,36,0.08)"] * len(row)
            elif "Healthy" in status:
                return ["background-color: rgba(74,222,128,0.06)"] * len(row)
            return [""] * len(row)

        styled_dscr = dscr_table.style.apply(style_dscr, axis=1).format({
            "revenue_lakhs":       "₹{:.2f}L",
            "ebitda_lakhs":        "₹{:.2f}L",
            "debt_service_lakhs":  "₹{:.2f}L",
            "dscr":                "{:.3f}x",
            "closing_cash_lakhs":  "₹{:.2f}L",
            "avg_collection_days": "{:.0f}d",
        }, na_rep="N/A")
        st.dataframe(styled_dscr, height=320, use_container_width=True)


# ---------------------------------------------------------------------------
# VIEW 2: FEEDSTOCK UNIT ECONOMICS & QUALITY RCA HUB
# ---------------------------------------------------------------------------

def render_view2(data: dict, filters: dict) -> None:
    """Render Feedstock Unit Economics & RCA Hub view."""

    # ── Page Title
    st.markdown(
        '<div class="page-title">Feedstock Unit Economics & Quality RCA Hub</div>'
        '<div class="page-subtitle">Supplier dry-cost analysis • Production efficiency waterfall • '
        'Automated root cause classification — 180-Day Operations Window</div>',
        unsafe_allow_html=True,
    )

    kpis = data["kpis"]

    # ── KPI Cards Row
    cuf = kpis.get("avg_cuf_pct", 0)
    cuf_type = "positive" if cuf >= 90 else ("warning" if cuf >= 80 else "negative")

    kpi_row([
        dict(
            label="Avg Landed Cost / Dry Ton",
            value=f"₹{kpis.get('avg_landed_cost_per_dry_ton', 0):,.0f}",
            delta="Per ton dry-weight basis",
            delta_type="neutral",
            accent="#2dd4bf,#38bdf8",
            icon="⚖️",
        ),
        dict(
            label="Plant CUF %",
            value=f"{cuf:.1f}%",
            delta=f"Target: 90.0% | Avg CBG: {kpis.get('avg_cbg_kg', 0):,.0f} kg/day",
            delta_type=cuf_type,
            accent="#818cf8,#38bdf8",
            icon="⚙️",
        ),
        dict(
            label="Avg CH4 Purity",
            value=f"{kpis.get('avg_ch4_pct', 0):.2f}%",
            delta="MNGL spec: ≥92% CH4",
            delta_type="positive" if kpis.get("avg_ch4_pct", 0) >= 92 else "warning",
            accent="#c084fc,#818cf8",
            icon="🧪",
        ),
        dict(
            label="Biogas Conversion",
            value=f"{kpis.get('conversion_efficiency', 0):.1f} Nm³/T",
            delta="Specific yield per ton biomass",
            delta_type="neutral",
            accent="#4ade80,#2dd4bf",
            icon="📈",
        ),
    ])

    # ── Row 1: Bubble Chart + RCA Donut
    section_header("Supplier Cost-Quality Matrix & Root Cause Distribution")
    col1, col2 = st.columns([3, 2])

    with col1:
        rank_df = data["supplier_rank"].copy()

        # Bubble size = total tons supplied
        fig_bubble = go.Figure()

        ft_colors = {
            "Press_Mud":    COLORS["primary"],
            "Cattle_Dung":  COLORS["success"],
            "Crop_Residue": COLORS["warning"],
        }

        for ftype, grp in rank_df.groupby("feedstock_type"):
            color = ft_colors.get(ftype, COLORS["gray"])
            fig_bubble.add_trace(go.Scatter(
                x=grp["overall_avg_dry_cost"],
                y=grp["overall_avg_moisture"],
                mode="markers+text",
                name=ftype.replace("_", " "),
                marker=dict(
                    size=grp["total_gross_tons"] / grp["total_gross_tons"].max() * 55 + 15,
                    color=color,
                    opacity=0.75,
                    line=dict(color="white", width=1.5),
                    sizemode="diameter",
                ),
                text=grp["supplier_name"].str.split(":").str[0],
                textposition="top center",
                textfont=dict(size=9, color="#94a3b8"),
                hovertemplate=(
                    "<b>%{text}</b><br>"
                    "Type: " + ftype + "<br>"
                    "Landed Cost/Dry Ton: ₹%{x:,.0f}<br>"
                    "Avg Moisture: %{y:.1f}%<br>"
                    "<extra></extra>"
                ),
            ))

        # Quadrant lines
        if not rank_df.empty:
            x_mid = float(rank_df["overall_avg_dry_cost"].median())
            y_mid = float(rank_df["overall_avg_moisture"].median())
            fig_bubble.add_hline(y=y_mid, line=dict(color=COLORS["gray"], dash="dot", width=1))
            fig_bubble.add_vline(x=x_mid, line=dict(color=COLORS["gray"], dash="dot", width=1))

            # Quadrant labels
            fig_bubble.add_annotation(
                x=rank_df["overall_avg_dry_cost"].min(),
                y=rank_df["overall_avg_moisture"].min() + 2,
                text="✓ Best Value",
                font=dict(size=9, color=COLORS["success"]),
                showarrow=False,
            )
            fig_bubble.add_annotation(
                x=rank_df["overall_avg_dry_cost"].max() - 50,
                y=rank_df["overall_avg_moisture"].max() - 2,
                text="⚠ Expensive + Wet",
                font=dict(size=9, color=COLORS["danger"]),
                showarrow=False,
            )

        layout_b = dict(**PLOTLY_LAYOUT)
        layout_b.update(
            title="Supplier: Landed Cost/Dry Ton vs. Moisture % (Bubble = Volume Supplied)",
            xaxis_title="Landed Cost per Dry Ton (₹/T)",
            yaxis_title="Average Moisture Content (%)",
            height=360,
        )
        fig_bubble.update_layout(**layout_b)
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.plotly_chart(fig_bubble, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    with col2:
        rca_sum = data["rca_summary"].copy()

        DONUT_COLORS = [
            COLORS["danger"],    # Mechanical
            COLORS["secondary"], # Process Chemistry
            COLORS["warning"],   # Storage
            COLORS["orange"],    # Moisture
            COLORS["teal"],      # Volume Deficit
        ]

        fig_donut = go.Figure(go.Pie(
            labels=rca_sum["primary_rca"],
            values=rca_sum["incident_days"],
            hole=0.55,
            marker=dict(
                colors=DONUT_COLORS[:len(rca_sum)],
                line=dict(color="#0a0f1e", width=3),
            ),
            textinfo="percent+label",
            textfont=dict(size=9, color="#e2e8f0"),
            hovertemplate=(
                "<b>%{label}</b><br>"
                "Days: %{value}<br>"
                "Share: %{percent}<br>"
                "<extra></extra>"
            ),
            direction="clockwise",
            sort=True,
        ))

        total_loss = float(rca_sum["total_loss_lakhs"].sum())
        total_days = int(rca_sum["incident_days"].sum())

        fig_donut.add_annotation(
            text=f"<b>{total_days}</b><br>Under-perf<br>Days",
            x=0.5, y=0.5,
            font=dict(size=11, color="#e2e8f0", family="Space Grotesk"),
            showarrow=False,
        )

        layout_d = dict(**PLOTLY_LAYOUT)
        layout_d.update(
            title=f"RCA Distribution — ₹{total_loss:.1f}L Total Loss",
            height=360,
            margin=dict(l=10, r=10, t=50, b=20),
            showlegend=True,
            legend=dict(
                orientation="v", x=1.0, y=0.5,
                font=dict(size=9),
            ),
        )
        fig_donut.update_layout(**layout_d)
        st.markdown('<div class="chart-container">', unsafe_allow_html=True)
        st.plotly_chart(fig_donut, use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Row 2: Production Waterfall Dual-Axis
    section_header("Daily Production Efficiency — Biomass Fed vs. CBG Output")

    prod_df = data["production"].copy()
    prod_df = prod_df[
        (prod_df["production_date"] >= filters["start_date"]) &
        (prod_df["production_date"] <= filters["end_date"])
    ]

    fig_prod = make_subplots(
        specs=[[{"secondary_y": True}]],
    )

    # Biomass fed (bars, secondary axis)
    fig_prod.add_trace(
        go.Bar(
            x=prod_df["production_date"],
            y=prod_df["tons_biomass_fed"],
            name="Biomass Fed (Tons)",
            marker=dict(color=COLORS["teal"], opacity=0.5, line=dict(width=0)),
            hovertemplate="<b>%{x|%d %b}</b><br>Biomass: %{y:.2f} T<extra></extra>",
        ),
        secondary_y=True,
    )

    # CBG produced (line, primary axis)
    fig_prod.add_trace(
        go.Scatter(
            x=prod_df["production_date"],
            y=prod_df["cbg_produced_kg"],
            name="CBG Produced (kg)",
            mode="lines",
            line=dict(color=COLORS["primary"], width=2),
            hovertemplate="<b>%{x|%d %b}</b><br>CBG: %{y:,.0f} kg<extra></extra>",
        ),
        secondary_y=False,
    )

    # Target line
    fig_prod.add_hline(
        y=3000, line=dict(color=COLORS["success"], dash="dash", width=1.5),
        annotation_text="Target: 3,000 kg/day",
        annotation_position="top left",
        annotation_font=dict(size=10, color=COLORS["success"]),
    )
    fig_prod.add_hline(
        y=2550, line=dict(color=COLORS["warning"], dash="dot", width=1),
        annotation_text="Alert: 2,550 kg (85%)",
        annotation_position="bottom right",
        annotation_font=dict(size=9, color=COLORS["warning"]),
    )

    # Anomaly shading
    if filters["show_anomalies"]:
        anomalies = [
            ("2024-02-09", "2024-02-21", "rgba(251,191,36,0.08)", "[A1] High\nMoisture"),
            ("2024-04-09", "2024-04-19", "rgba(239,68,68,0.10)", "[A2] Compressor\nFailure"),
        ]
        for a_start, a_end, a_color, a_label in anomalies:
            fig_prod.add_vrect(
                x0=a_start, x1=a_end,
                fillcolor=a_color,
                line=dict(color="rgba(255,255,255,0.1)", width=1),
                annotation_text=a_label,
                annotation_position="top left",
                annotation_font=dict(size=9, color="#94a3b8"),
            )

    prod_layout = dict(**PLOTLY_LAYOUT)
    prod_layout.update(
        title="Daily CBG Production vs. Biomass Feed Rate (180-Day Window)",
        height=340,
        legend=dict(
            x=0.0, y=1.1, orientation="h",
            bgcolor="rgba(15,23,42,0.8)",
            bordercolor="rgba(56,189,248,0.2)",
            borderwidth=1,
            font=dict(size=11),
        ),
    )
    fig_prod.update_layout(**prod_layout)
    fig_prod.update_yaxes(
        title_text="CBG Produced (kg/day)", secondary_y=False,
        gridcolor="rgba(56,189,248,0.07)", zeroline=False,
        tickfont=dict(size=10),
    )
    fig_prod.update_yaxes(
        title_text="Biomass Fed (Tons/day)", secondary_y=True,
        showgrid=False, zeroline=False, tickfont=dict(size=10),
    )
    st.markdown('<div class="chart-container">', unsafe_allow_html=True)
    st.plotly_chart(fig_prod, use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # ── RCA Drill-Down Table
    section_header("Anomaly Drill-Down — Root Cause Diagnosis & Corrective Actions")

    rca_detail = data["rca_detail"].copy()

    # Filter by date
    rca_detail = rca_detail[
        (rca_detail["production_date"] >= filters["start_date"]) &
        (rca_detail["production_date"] <= filters["end_date"])
    ]

    # Severity filter
    sev_options = ["All"] + sorted(rca_detail["severity_level"].unique().tolist())
    rca_filter_col1, rca_filter_col2, rca_filter_col3 = st.columns([1, 1, 2])
    with rca_filter_col1:
        sel_severity = st.selectbox("Filter by Severity", options=sev_options, index=0)
    with rca_filter_col2:
        rca_options = ["All"] + sorted(rca_detail["primary_rca"].unique().tolist())
        sel_rca     = st.selectbox("Filter by RCA", options=rca_options, index=0)
    with rca_filter_col3:
        st.markdown("")  # spacer

    if sel_severity != "All":
        rca_detail = rca_detail[rca_detail["severity_level"] == sel_severity]
    if sel_rca != "All":
        rca_detail = rca_detail[rca_detail["primary_rca"] == sel_rca]

    # Display table with severity colour coding
    rca_display = rca_detail[[
        "production_date", "cbg_produced_kg", "cuf_pct",
        "plant_downtime_hrs", "ch4_purity_pct", "feedstock_moisture_pct",
        "vs_loss_pct", "primary_rca", "severity_level",
        "revenue_loss_inr", "corrective_action",
    ]].copy()
    rca_display["production_date"] = rca_display["production_date"].dt.strftime("%Y-%m-%d")
    rca_display = rca_display.rename(columns={
        "production_date":     "Date",
        "cbg_produced_kg":     "CBG (kg)",
        "cuf_pct":             "CUF %",
        "plant_downtime_hrs":  "Downtime (h)",
        "ch4_purity_pct":      "CH4 %",
        "feedstock_moisture_pct": "Moisture %",
        "vs_loss_pct":         "VS Loss %",
        "primary_rca":         "Root Cause",
        "severity_level":      "Severity",
        "revenue_loss_inr":    "Loss (₹)",
        "corrective_action":   "Corrective Action",
    })

    def style_rca_row(row):
        sev = str(row.get("Severity", ""))
        if sev == "CRITICAL":
            return ["background-color: rgba(239,68,68,0.15)"] * len(row)
        elif sev == "HIGH":
            return ["background-color: rgba(251,146,60,0.10)"] * len(row)
        elif sev == "MEDIUM":
            return ["background-color: rgba(251,191,36,0.07)"] * len(row)
        return [""] * len(row)

    styled_rca = rca_display.style.apply(style_rca_row, axis=1).format({
        "CBG (kg)":     "{:,.0f}",
        "CUF %":        "{:.1f}%",
        "Downtime (h)": "{:.1f}h",
        "CH4 %":        "{:.1f}%",
        "Moisture %":   "{:.1f}%",
        "VS Loss %":    "{:.1f}%",
        "Loss (₹)":     "₹{:,.0f}",
    })

    st.dataframe(styled_rca, height=380, use_container_width=True)

    # RCA loss summary chips
    st.markdown("**Loss Summary by Root Cause:**")
    rca_chips_cols = st.columns(len(data["rca_summary"]))
    for i, (_, row) in enumerate(data["rca_summary"].iterrows()):
        with rca_chips_cols[i]:
            st.markdown(
                f"""<div style='background:rgba(15,23,42,0.9);border:1px solid rgba(56,189,248,0.15);
                border-radius:12px;padding:0.75rem;text-align:center;'>
                <div style='font-size:0.65rem;color:#64748b;letter-spacing:0.06em;
                text-transform:uppercase;margin-bottom:0.3rem;'>
                {row["primary_rca"][:20]}...</div>
                <div style='font-family:"Space Grotesk";font-size:1.1rem;
                font-weight:700;color:#f87171;'>₹{row["total_loss_lakhs"]:.2f}L</div>
                <div style='font-size:0.7rem;color:#475569;'>{int(row["incident_days"])} days</div>
                </div>""",
                unsafe_allow_html=True,
            )


# ---------------------------------------------------------------------------
# MAIN APP
# ---------------------------------------------------------------------------

def main():
    """Main application entry point."""

    # Check database readiness
    if not check_database_ready():
        st.markdown("""
        <div style='text-align:center;padding:4rem 2rem;'>
            <div style='font-family:"Space Grotesk";font-size:2.2rem;font-weight:700;
                 background:linear-gradient(135deg,#38bdf8,#c084fc);
                 -webkit-background-clip:text;-webkit-text-fill-color:transparent;
                 margin-bottom:1rem;'>⚙️ CBG Operations Dashboard</div>
            <div style='color:#64748b;font-size:1rem;margin-bottom:2rem;'>
                Database not found or empty. Run the seeder to get started.
            </div>
            <div style='background:rgba(15,23,42,0.9);border:1px solid rgba(56,189,248,0.2);
                 border-radius:12px;padding:1.5rem;display:inline-block;text-align:left;'>
                <pre style='color:#38bdf8;font-size:0.9rem;margin:0;'>
# Step 1: Install dependencies
pip install -r requirements.txt

# Step 2: Seed the database
python generate_data.py

# Step 3: Launch the dashboard
streamlit run app.py
                </pre>
            </div>
        </div>
        """, unsafe_allow_html=True)
        return

    # Load data
    with st.spinner("Loading plant analytics engine..."):
        data = load_all_data()

    # Render sidebar and get filters
    filters = render_sidebar(data)

    # Route to selected view
    if filters["page"] == "🏦 Capital Planning & Solvency":
        render_view1(data, filters)
    else:
        render_view2(data, filters)


if __name__ == "__main__":
    main()
