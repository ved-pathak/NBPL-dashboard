"""
app.py
Streamlit dashboard for CBG Plant Production Funnel.
Reads only from SQL views via sqlite3 + pandas. Renders with Plotly.

Pages (sidebar radio):
  1. Overview     - KPI cards, daily production chart, Rs loss waterfall
  2. Daily Detail - per-day table with cause tracing and diagnostics
  3. Aggregate & Vendors - Cause ranking, vendor contribution, vendor summary
"""

import os
import sqlite3
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import streamlit as st

DB_PATH = os.path.join(os.path.dirname(__file__), "cbg.db")

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="CBG Plant — Production Funnel",
    page_icon="⚙️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', sans-serif;
}

/* Dark background */
.stApp {
    background-color: #0f1117;
    color: #e4e4e7;
}

/* Sidebar */
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #1a1d2e 0%, #16192a 100%);
    border-right: 1px solid rgba(99,102,241,0.2);
}

[data-testid="stSidebar"] .stRadio label {
    color: #a1a1aa !important;
    font-size: 0.9rem;
}

/* KPI cards */
.kpi-card {
    background: linear-gradient(135deg, #1e2235 0%, #252840 100%);
    border: 1px solid rgba(99,102,241,0.25);
    border-radius: 12px;
    padding: 20px 24px;
    margin-bottom: 0;
    position: relative;
    overflow: hidden;
}
.kpi-card::before {
    content: '';
    position: absolute;
    top: 0; left: 0; right: 0;
    height: 3px;
    background: linear-gradient(90deg, #6366f1, #8b5cf6);
}
.kpi-label {
    font-size: 0.72rem;
    font-weight: 600;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    color: #71717a;
    margin-bottom: 6px;
}
.kpi-value {
    font-size: 1.9rem;
    font-weight: 700;
    color: #f4f4f5;
    line-height: 1.1;
}
.kpi-sub {
    font-size: 0.78rem;
    color: #71717a;
    margin-top: 4px;
}
.kpi-good  { color: #34d399 !important; }
.kpi-warn  { color: #fbbf24 !important; }
.kpi-bad   { color: #f87171 !important; }

/* Section headers */
.section-header {
    font-size: 1rem;
    font-weight: 600;
    color: #a5b4fc;
    letter-spacing: 0.04em;
    text-transform: uppercase;
    margin: 24px 0 12px;
    padding-bottom: 6px;
    border-bottom: 1px solid rgba(99,102,241,0.2);
}

/* Dataframe tweaks */
[data-testid="stDataFrame"] {
    border-radius: 10px;
    overflow: hidden;
}

/* Config expander */
.streamlit-expanderHeader {
    font-size: 0.85rem !important;
    color: #a1a1aa !important;
}

/* Page title */
.page-title {
    font-size: 1.6rem;
    font-weight: 700;
    background: linear-gradient(90deg, #818cf8, #c084fc);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    margin-bottom: 2px;
}
.page-subtitle {
    font-size: 0.85rem;
    color: #52525b;
    margin-bottom: 20px;
}
</style>
""", unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# DB helper
# ---------------------------------------------------------------------------
def query(sql: str) -> pd.DataFrame:
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query(sql, conn)
    conn.close()
    return df


# ---------------------------------------------------------------------------
# Load data (cached)
# ---------------------------------------------------------------------------
def load_all():
    headline  = query("SELECT * FROM v_headline_summary")
    trend     = query("SELECT * FROM v_daily_trend ORDER BY output_date")
    loss_daily = query("SELECT * FROM v_loss_daily ORDER BY output_date")
    cause_rank = query("SELECT * FROM v_cause_ranking ORDER BY total_rs_loss DESC")
    vendors   = query("SELECT * FROM v_window_vendors")
    v_summary = query("SELECT * FROM v_vendor_summary")
    losses    = query("SELECT * FROM v_stage_losses ORDER BY output_date")
    config    = query("SELECT * FROM config")
    price     = query("SELECT * FROM v_price")
    return headline, trend, loss_daily, cause_rank, vendors, v_summary, losses, config, price


headline, trend, loss_daily, cause_rank, vendors, v_summary, losses, config, price = load_all()

cfg = config.iloc[0]
pr  = price.iloc[0]
hl  = headline.iloc[0]

n_output_days = int(hl.output_day_count)

# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### ⚙️ CBG Analytics")
    st.markdown("---")
    page = st.radio(
        "Navigate",
        ["📊 Overview", "🔍 Daily Detail", "📦 Aggregate & Vendors"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    with st.expander("Config Parameters", expanded=False):
        st.markdown(f"""
| Parameter | Value |
|---|---|
| Nameplate | {cfg.nameplate_kg:,.0f} kg/day |
| Plant need | {cfg.plant_need_t} t/day |
| Design purity | {cfg.design_purity*100:.0f}% |
| Design slip | {cfg.design_slip*100:.0f}% |
| Lag days | {cfg.lag_days} |
| Price/MMBTU | ₹{cfg.price_per_mmbtu:,.0f} |
| Design price | ₹{pr.design_price:.2f}/kg |
| Significance | {cfg.materiality_pct*100:.0f}% of N×P |
| Reliability threshold | {cfg.reliability_threshold*100:.0f}% |
| Output days | {n_output_days} |
""")


# ---------------------------------------------------------------------------
# Colour palette
# ---------------------------------------------------------------------------
INDIGO   = "#6366f1"
VIOLET   = "#8b5cf6"
EMERALD  = "#10b981"
AMBER    = "#f59e0b"
ROSE     = "#f43f5e"
CYAN     = "#06b6d4"
SLATE    = "#64748b"
CAUSE_COLORS = {
    "Supply shortfall":                     AMBER,
    "Moisture / low solids":                CYAN,
    "Digester underperformance":            ROSE,
    "Purification methane slip":            VIOLET,
    "Low purity at plant gate":             "#e879f9",
    "Purity drop in transit":               "#f97316",
    "Transit loss":                         SLATE,
    "Transit pressure loss":                SLATE,
    "Short billing (plant issue also present)": "#6b7280",
}


# ===========================================================================
# PAGE 1 — OVERVIEW
# ===========================================================================
if page == "📊 Overview":
    st.markdown('<div class="page-title">Production Loss Overview</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-subtitle">{n_output_days}-day output window · Nameplate {cfg.nameplate_kg:,.0f} kg/day · {cfg.design_purity*100:.0f}% purity CBG</div>', unsafe_allow_html=True)

    # ---- KPI cards ----
    c1, c2, c3, c4, c5 = st.columns(5)
    pct_class = "kpi-good" if hl.avg_pct_nameplate >= 95 else "kpi-warn" if hl.avg_pct_nameplate >= 90 else "kpi-bad"
    days_class = "kpi-good" if hl.days_below_90 == 0 else "kpi-warn" if hl.days_below_90 <= 3 else "kpi-bad"

    def kpi_html(label, value, sub="", val_class=""):
        return f"""<div class="kpi-card">
<div class="kpi-label">{label}</div>
<div class="kpi-value {val_class}">{value}</div>
<div class="kpi-sub">{sub}</div>
</div>"""

    c1.markdown(kpi_html("Avg Production", f"{hl.avg_cbg_kg:,.0f} kg", "per day"), unsafe_allow_html=True)
    c2.markdown(kpi_html("Avg % Nameplate", f"{hl.avg_pct_nameplate:.1f}%", f"vs {cfg.nameplate_kg:,.0f} kg", pct_class), unsafe_allow_html=True)
    c3.markdown(kpi_html("Days Below 90%", str(int(hl.days_below_90)), f"of {n_output_days} output days", days_class), unsafe_allow_html=True)
    c4.markdown(kpi_html("Total Rs Lost", f"₹{hl.total_rs_lost/1e5:.2f}L", f"over {n_output_days} days"), unsafe_allow_html=True)
    c5.markdown(kpi_html("Qty / Purity Split",
        f"₹{hl.qty_loss_rs/1e5:.2f}L / ₹{hl.price_loss_rs/1e5:.2f}L",
        "Quantity loss / Price-realisation loss"), unsafe_allow_html=True)

    st.markdown('<div class="section-header">Daily Production</div>', unsafe_allow_html=True)

    # Convert to explicit Python lists
    x_dates = trend["output_date"].astype(str).tolist()
    cbg_vals = [float(v) for v in trend["cbg_out_kg"]]
    billed_vals = [float(v) for v in trend["billed_kg"]]
    rolling_vals = [float(v) for v in trend["rolling_7d_avg_kg"]]

    threshold_90 = cfg.nameplate_kg * 0.9

    fig_trend = go.Figure()
    fig_trend.add_trace(go.Scatter(
        x=x_dates, y=cbg_vals,
        name="CBG Production", mode="lines+markers",
        line=dict(color=INDIGO, width=2.5),
        marker=dict(size=7, color=[ROSE if v < threshold_90 else INDIGO for v in cbg_vals]),
        hovertemplate="<b>Date:</b> %{x}<br><b>CBG Prod:</b> %{y:,.1f} kg<extra></extra>",
    ))
    fig_trend.add_trace(go.Scatter(
        x=x_dates, y=billed_vals,
        name="Billed kg", mode="lines+markers",
        line=dict(color=EMERALD, width=2, dash="dot"),
        marker=dict(size=5, color=EMERALD),
        hovertemplate="<b>Date:</b> %{x}<br><b>Billed:</b> %{y:,.1f} kg<extra></extra>",
    ))
    fig_trend.add_trace(go.Scatter(
        x=x_dates, y=rolling_vals,
        name="7-Day Rolling Avg", mode="lines",
        line=dict(color=AMBER, width=2.5, dash="dash"),
        hovertemplate="<b>Date:</b> %{x}<br><b>7d Rolling Avg:</b> %{y:,.1f} kg<extra></extra>",
    ))
    fig_trend.add_hline(y=cfg.nameplate_kg, line_dash="solid", line_color="#e4e4e7",
                        line_width=1.2, annotation_text=f"Nameplate {cfg.nameplate_kg:,.0f} kg",
                        annotation_position="top right",
                        annotation_font_color="#e4e4e7")
    fig_trend.add_hline(y=threshold_90, line_dash="dash", line_color=ROSE,
                        line_width=1.2, annotation_text=f"90% threshold ({threshold_90:,.0f} kg)",
                        annotation_position="bottom right",
                        annotation_font_color=ROSE)
    fig_trend.update_layout(
        template="plotly_dark", paper_bgcolor="#0f1117", plot_bgcolor="#1a1d2e",
        height=360, margin=dict(l=10, r=10, t=10, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        xaxis=dict(type="category", title="Output Date", showgrid=False,
                   tickmode="array",
                   tickvals=x_dates[::max(1, len(x_dates)//15)],
                   tickangle=-45),
        yaxis=dict(range=[min(cbg_vals)*0.9, cfg.nameplate_kg*1.08],
                   title="CBG (kg/day)", showgrid=True, gridcolor="#2d2d3a"),
    )
    st.plotly_chart(fig_trend, use_container_width=True, config={"displayModeBar": True, "scrollZoom": False})

    st.markdown('<div class="section-header">Rs Loss Waterfall (All Output Days)</div>', unsafe_allow_html=True)

    # Pull total_rs_lost directly from database views — no duplicate revenue math in app
    diff_loss = float(hl.total_rs_lost)

    cause_labels = [
        "Moisture / low solids", "Digester underperform.",
        "Supply shortfall", "Transit quantity",
        "Purification slip", "Low purity (plant)",
        "Purity drop (transit)",
    ]
    cause_vals = [
        float(losses["moisture_loss_rs"].sum()),
        float(losses["digester_loss_rs"].sum()),
        float(losses["supply_loss_rs"].sum()),
        float(losses["transit_qty_loss_rs"].sum()),
        float(losses["purification_loss_rs"].sum()),
        float(losses["purity_plant_loss_rs"].sum()),
        float(losses["purity_transit_loss_rs"].sum()),
    ]

    wf_x = ["Total Loss\n(Difference)"] + cause_labels
    wf_measures = ["absolute"] + ["relative"] * len(cause_labels)
    wf_y = [diff_loss] + [-v for v in cause_vals]
    wf_text = [f"₹{diff_loss/1e5:.2f}L"] + [f"-₹{v/1000:.1f}K" for v in cause_vals]

    fig_wf = go.Figure(go.Waterfall(
        orientation="v", measure=wf_measures,
        x=wf_x, y=wf_y,
        text=wf_text, textposition="outside",
        connector=dict(line=dict(color="#52525b", width=1)),
        increasing=dict(marker_color=ROSE),
        decreasing=dict(marker_color="#38bdf8"),
        totals=dict(marker_color=ROSE),
        hovertemplate="<b>%{x}</b><br>Amount: %{text}<extra></extra>",
    ))
    fig_wf.update_layout(
        template="plotly_dark", paper_bgcolor="#0f1117", plot_bgcolor="#1a1d2e",
        height=420, margin=dict(l=10, r=10, t=30, b=10),
        xaxis=dict(showgrid=False),
        yaxis=dict(title="₹ Lost", range=[0, max(diff_loss, 600000) * 1.15], showgrid=True, gridcolor="#2d2d3a"),
        showlegend=False,
    )
    st.plotly_chart(fig_wf, use_container_width=True)


# ===========================================================================
# PAGE 2 — DAILY DETAIL
# ===========================================================================
elif page == "🔍 Daily Detail":
    st.markdown('<div class="page-title">Daily Loss Attribution</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-subtitle">{n_output_days} output days · Sequential loss decomposition · Lag = {int(cfg.lag_days)} days</div>', unsafe_allow_html=True)

    # Prepare display table
    df = loss_daily.copy()
    df["Production kg"]     = df["cbg_out_kg"].round(0).astype(int)
    df["% of Nameplate"]    = df["pct_of_nameplate"].apply(lambda x: f"{x:.1f}%")
    df["Gap kg"]            = df["gap_kg"].round(0).astype(int)
    df["Rs Lost"]           = df["total_rs_lost"].apply(lambda x: f"₹{x/1000:.1f}K")
    df["Primary Rs"]        = df["primary_rs_loss"].apply(lambda x: f"₹{x/1000:.1f}K" if x else "")
    df["Date"]              = df["output_date"]
    df["Status"]            = df["status"]
    df["Primary Cause"]     = df["primary_cause"]
    df["Secondary Cause"]   = df["secondary_cause"].fillna("—")
    df["Feed Date"]         = df["traced_feed_date"].fillna("—")
    df["Vendor"]            = df["traced_vendor"].fillna("—")
    df["Diagnostic"]        = df["diagnostic_note"]

    display_cols = ["Date", "Status", "Production kg", "% of Nameplate", "Gap kg",
                    "Rs Lost", "Primary Cause", "Secondary Cause",
                    "Feed Date", "Vendor", "Diagnostic"]

    def row_style(row):
        if row["Status"] == "Below 90%":
            return ["background-color: rgba(244,63,94,0.12); color: #fca5a5"] * len(row)
        return [""] * len(row)

    styled = df[display_cols].style.apply(row_style, axis=1)

    st.markdown(f'<div class="section-header">All {n_output_days} Output Days</div>', unsafe_allow_html=True)
    st.dataframe(styled, use_container_width=True, hide_index=True, height=570)

    # Summary pills
    below90 = df[df["Status"] == "Below 90%"]
    normal_var = df[df["Primary Cause"].str.contains("normal", case=False, na=False)]
    st.markdown(f"""
    <div style='margin-top:12px; font-size:0.82rem; color:#71717a;'>
    🔴 <b style='color:#f87171'>{len(below90)} days below 90%</b> &nbsp;|&nbsp;
    🟡 <b style='color:#fbbf24'>{len(normal_var)} days within normal variation</b> &nbsp;|&nbsp;
    Total Rs lost: <b style='color:#e4e4e7'>₹{hl.total_rs_lost/1e5:.2f}L</b>
    </div>
    """, unsafe_allow_html=True)

    # Day-level detail drilldown
    st.markdown('<div class="section-header">Day-Level Loss Breakdown</div>', unsafe_allow_html=True)
    selected_date = st.selectbox("Select output date", loss_daily["output_date"].tolist())
    day_row = losses[losses["output_date"] == selected_date].iloc[0]

    cols = st.columns(7)
    stage_data = [
        ("Supply",       day_row["supply_loss_kg"],       day_row["supply_loss_rs"],       AMBER),
        ("Moisture",     day_row["moisture_loss_kg"],     day_row["moisture_loss_rs"],     CYAN),
        ("Digester",     day_row["digester_loss_kg"],     day_row["digester_loss_rs"],     ROSE),
        ("Purification", day_row["purification_loss_kg"], day_row["purification_loss_rs"], VIOLET),
        ("Purity Plant", 0,                               day_row["purity_plant_loss_rs"], "#e879f9"),
        ("Purity Transit",0,                              day_row["purity_transit_loss_rs"],"#f97316"),
        ("Transit Qty",  day_row["transit_loss_kg"],      day_row["transit_qty_loss_rs"],  SLATE),
    ]
    for col, (lbl, kg, rs, clr) in zip(cols, stage_data):
        sign = "+" if rs < 0 else ""
        clr_str = "#34d399" if rs < 0 else clr
        col.markdown(f"""<div class="kpi-card" style="border-color:{clr_str}40">
<div class="kpi-label" style="color:{clr_str}80">{lbl}</div>
<div class="kpi-value" style="font-size:1.1rem; color:{clr_str}">{sign}₹{abs(rs)/1000:.1f}K</div>
<div class="kpi-sub">{f'{kg:+.0f} kg' if kg != 0 else 'price only'}</div>
</div>""", unsafe_allow_html=True)


# ===========================================================================
# PAGE 3 — AGGREGATE & VENDORS
# ===========================================================================
elif page == "📦 Aggregate & Vendors":
    st.markdown('<div class="page-title">Aggregate & Vendor Analysis</div>', unsafe_allow_html=True)
    st.markdown(f'<div class="page-subtitle">Cause ranking · Vendor contribution · Vendor summary ({int(cfg.lag_days) + n_output_days}-day feed window)</div>', unsafe_allow_html=True)

    col_left, col_right = st.columns([3, 2])

    # ---- Cause ranking chart ----
    with col_left:
        st.markdown('<div class="section-header">Rs Loss by Cause (Ranked)</div>', unsafe_allow_html=True)

        pbar = cause_rank[cause_rank["total_rs_loss"] > 0].sort_values("total_rs_loss", ascending=False).copy()
        p_causes = pbar["cause"].astype(str).tolist()
        p_losses = [float(v) for v in pbar["total_rs_loss"]]
        p_cum = [float(v) for v in pbar["cumulative_pct"]]
        bar_colors = [CAUSE_COLORS.get(c, INDIGO) for c in p_causes]

        fig_rank = go.Figure()
        fig_rank.add_trace(go.Bar(
            name="Rs Lost", x=p_causes, y=p_losses,
            marker_color=bar_colors,
            text=[f"₹{v/1000:.1f}K" for v in p_losses],
            textposition="outside", yaxis="y",
            hovertemplate="<b>%{x}</b><br>Loss: ₹%{y:,.0f}<extra></extra>",
        ))
        fig_rank.add_trace(go.Scatter(
            name="Cumulative %", x=p_causes, y=p_cum,
            mode="lines+markers", line=dict(color="#f59e0b", width=2),
            marker=dict(size=6), yaxis="y2",
            hovertemplate="<b>Cumulative:</b> %{y:.1f}%<extra></extra>",
        ))
        fig_rank.add_shape(type="line", x0=-0.5, x1=len(pbar)-0.5,
                             y0=80, y1=80, yref="y2",
                             line=dict(color=AMBER, width=1, dash="dot"))
        fig_rank.update_layout(
            template="plotly_dark", paper_bgcolor="#0f1117", plot_bgcolor="#1a1d2e",
            height=380, margin=dict(l=10, r=60, t=30, b=120),
            xaxis=dict(tickangle=-35, showgrid=False),
            yaxis=dict(title="₹ Lost", range=[0, max(p_losses) * 1.15], showgrid=True, gridcolor="#2d2d3a"),
            yaxis2=dict(title="Cumulative %", overlaying="y", side="right",
                        range=[0, 110], showgrid=False),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            barmode="group",
        )
        st.plotly_chart(fig_rank, use_container_width=True)

        # Cause summary table
        st.markdown('<div class="section-header">Cause Summary</div>', unsafe_allow_html=True)
        cr_display = cause_rank[["cause","total_rs_loss","pct_of_total","cumulative_pct","days_as_primary"]].copy()
        cr_display.columns = ["Cause", "Total Rs Lost", "% of Total", "Cumulative %", "Days as Primary"]
        cr_display["Total Rs Lost"] = cr_display["Total Rs Lost"].apply(lambda x: f"₹{x/1000:.1f}K")
        cr_display["% of Total"] = cr_display["% of Total"].apply(lambda x: f"{x:.1f}%")
        cr_display["Cumulative %"] = cr_display["Cumulative %"].apply(lambda x: f"{x:.1f}%")
        st.dataframe(cr_display, use_container_width=True, hide_index=True)

    # ---- Vendor contribution ----
    with col_right:
        st.markdown(f'<div class="section-header">Vendor Loss Contribution ({n_output_days} days)</div>', unsafe_allow_html=True)

        v_sorted = vendors.sort_values("total_loss_rs", ascending=False).copy()
        v_names = v_sorted["vendor"].astype(str).tolist()
        v_supply = [float(v) for v in v_sorted["supply_loss_rs"]]
        v_moisture = [float(v) for v in v_sorted["moisture_loss_rs"]]
        v_total = [float(v) for v in v_sorted["total_loss_rs"]]

        fig_vend = go.Figure()
        fig_vend.add_trace(go.Bar(
            name="Supply Loss", x=v_names, y=v_supply,
            marker_color=AMBER,
            text=[f"₹{v/1000:.1f}K" if v > 10000 else "" for v in v_supply],
            textposition="inside",
            insidetextanchor="middle",
            hovertemplate="<b>Vendor %{x}</b><br>Supply Loss: ₹%{y:,.0f}<extra></extra>",
        ))
        fig_vend.add_trace(go.Bar(
            name="Moisture Loss", x=v_names, y=v_moisture,
            marker_color=CYAN,
            text=[f"₹{v/1000:.1f}K" if v > 10000 else "" for v in v_moisture],
            textposition="inside",
            insidetextanchor="middle",
            hovertemplate="<b>Vendor %{x}</b><br>Moisture Loss: ₹%{y:,.0f}<extra></extra>",
        ))
        fig_vend.add_trace(go.Scatter(
            x=v_names, y=v_total,
            mode="text",
            text=[f"₹{v/1000:.1f}K" for v in v_total],
            textposition="top center",
            showlegend=False,
            hoverinfo="skip",
        ))
        fig_vend.update_layout(
            barmode="stack",
            template="plotly_dark", paper_bgcolor="#0f1117", plot_bgcolor="#1a1d2e",
            height=380, margin=dict(l=10, r=10, t=30, b=40),
            xaxis=dict(title="Vendor", showgrid=False),
            yaxis=dict(title="₹ Lost", range=[0, max(v_total) * 1.15], showgrid=True, gridcolor="#2d2d3a"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_vend, use_container_width=True)

    # ---- Vendor summary ----
    st.markdown(f'<div class="section-header">Vendor Summary ({int(cfg.lag_days) + n_output_days} Feed Days)</div>', unsafe_allow_html=True)
    st.markdown("""<div style='font-size:0.78rem; color:#52525b; margin-bottom:8px;'>
    Landed dry cost = (price + freight) / dry tonne. Best = lowest landed cost with reliability ≥ 95%. Worst = highest landed cost.
    </div>""", unsafe_allow_html=True)

    sc = v_summary.copy()
    sc["Flag"] = sc.apply(lambda r: "⭐ Best" if r["is_best"] else ("⚠️ Worst" if r["is_worst"] else ""), axis=1)
    sc["Avg Landed ₹/dry t"] = sc["avg_landed_cost_per_dry_t"].apply(lambda x: f"₹{x:,.0f}")
    sc["Reliability"] = sc["reliability_score"].apply(lambda x: f"{x*100:.1f}%")
    sc["Days < 90% DCQ"] = sc["days_below_90pct_dcq"]
    sc["Avg Moisture"] = sc["avg_moisture"].apply(lambda x: f"{x*100:.1f}%")
    sc["Rank Overall"] = sc["rank_overall"]
    sc["Rank / Material"] = sc["rank_within_material"]

    display_sc = sc[["vendor","material","dcq_t","Avg Landed ₹/dry t","Reliability",
                      "Days < 90% DCQ","Avg Moisture","Rank Overall","Rank / Material","Flag"]]
    display_sc.columns = ["Vendor","Material","DCQ t","Landed ₹/dry t","Reliability",
                           "Days < 90% DCQ","Avg Moisture","Rank","Rank/Material","Flag"]

    def scorecard_style(row):
        if row["Flag"] == "⭐ Best":
            return ["background-color: rgba(16,185,129,0.1)"] * len(row)
        elif row["Flag"] == "⚠️ Worst":
            return ["background-color: rgba(239,68,68,0.1)"] * len(row)
        return [""] * len(row)

    styled_sc = display_sc.style.apply(scorecard_style, axis=1)
    st.dataframe(styled_sc, use_container_width=True, hide_index=True)
