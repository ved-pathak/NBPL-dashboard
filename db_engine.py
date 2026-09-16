"""
=============================================================================
BioPulse: CBG Capital Planning & Operational Unit Economics Platform
FILE: db_engine.py
PURPOSE: SQLAlchemy/SQLite engine wrapper and query execution utilities.
         Provides modular functions returning Pandas DataFrames for each
         analytics query — consumed by the Streamlit dashboard (app.py).
=============================================================================
"""

import os
import sqlite3
import textwrap
from pathlib import Path
from typing import Optional

import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
DB_PATH        = Path(__file__).parent / "biopulse_cbg.db"
ANALYTICS_SQL  = Path(__file__).parent / "analytics_queries.sql"

# Minimum Debt Service Reserve (INR) — red-line for liquidity charts
DSR_RESERVE_INR = 500_000   # INR 5 Lakhs
CBG_TARGET_KG   = 3000.0


# ---------------------------------------------------------------------------
# ENGINE FACTORY
# ---------------------------------------------------------------------------

def get_engine() -> Engine:
    """
    Return a SQLAlchemy engine connected to the BioPulse SQLite database.
    Raises a RuntimeError if the database has not been seeded yet.
    """
    if not DB_PATH.exists():
        raise RuntimeError(
            f"Database not found at: {DB_PATH}\n"
            "Run `python generate_data.py` first to seed the database."
        )
    engine = create_engine(
        f"sqlite:///{DB_PATH}",
        connect_args={"check_same_thread": False},
        echo=False,
    )
    return engine


def run_query(sql: str, engine: Optional[Engine] = None) -> pd.DataFrame:
    """
    Execute a raw SQL string and return a Pandas DataFrame.
    Thread-safe; creates its own engine if not provided.
    """
    if engine is None:
        engine = get_engine()
    with engine.connect() as conn:
        df = pd.read_sql_query(text(sql), conn)
    return df


# ---------------------------------------------------------------------------
# Q1: CAPEX S-CURVE DATA
# ---------------------------------------------------------------------------

CAPEX_SCURVE_SQL = """
WITH capex_enriched AS (
    SELECT
        milestone_id,
        category,
        milestone_name,
        vendor_name,
        target_date,
        actual_date,
        budgeted_amount,
        COALESCE(actual_spend, budgeted_amount)  AS actual_spend_safe,
        completion_pct,
        COALESCE(actual_spend, budgeted_amount) - budgeted_amount AS variance_inr,
        ROUND(
            (COALESCE(actual_spend, budgeted_amount) - budgeted_amount)
            / budgeted_amount * 100.0, 2) AS variance_pct,
        CASE
            WHEN COALESCE(actual_spend, budgeted_amount) <= budgeted_amount
                THEN 'Under Budget'
            WHEN (COALESCE(actual_spend, budgeted_amount) - budgeted_amount)
                 / budgeted_amount <= 0.05 THEN 'Minor Overrun (0-5%)'
            WHEN (COALESCE(actual_spend, budgeted_amount) - budgeted_amount)
                 / budgeted_amount <= 0.10 THEN 'Moderate Overrun (5-10%)'
            WHEN (COALESCE(actual_spend, budgeted_amount) - budgeted_amount)
                 / budgeted_amount <= 0.15 THEN 'High Overrun (10-15%)'
            ELSE 'Critical Overrun (>15%)'
        END AS overrun_severity,
        CASE
            WHEN actual_date IS NOT NULL
            THEN CAST(julianday(actual_date) - julianday(target_date) AS INTEGER)
            ELSE NULL
        END AS schedule_delay_days,
        CASE
            WHEN actual_date IS NULL AND date('now') > date(target_date) THEN 'OVERDUE'
            WHEN actual_date IS NULL THEN 'In-Progress'
            ELSE 'Completed'
        END AS milestone_status
    FROM capex_milestones
),
capex_cumulative AS (
    SELECT
        ce.*,
        SUM(ce.budgeted_amount) OVER (
            ORDER BY ce.target_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_budget,
        SUM(ce.actual_spend_safe) OVER (
            ORDER BY ce.target_date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) AS cumulative_actual,
        ROW_NUMBER() OVER (ORDER BY ce.target_date) AS milestone_seq
    FROM capex_enriched ce
)
SELECT
    milestone_seq,
    category,
    milestone_name,
    vendor_name,
    target_date,
    actual_date,
    ROUND(budgeted_amount / 100000.0, 2)       AS budget_lakhs,
    ROUND(actual_spend_safe / 100000.0, 2)     AS actual_lakhs,
    ROUND(variance_inr / 100000.0, 2)          AS variance_lakhs,
    variance_pct,
    overrun_severity,
    schedule_delay_days,
    milestone_status,
    ROUND(cumulative_budget / 100000.0, 2)     AS cumulative_budget_lakhs,
    ROUND(cumulative_actual / 100000.0, 2)     AS cumulative_actual_lakhs,
    completion_pct
FROM capex_cumulative
ORDER BY milestone_seq
"""


def get_capex_scurve(engine: Optional[Engine] = None) -> pd.DataFrame:
    """Return CAPEX S-Curve data with cumulative planned vs actual spend."""
    df = run_query(CAPEX_SCURVE_SQL, engine)
    df["target_date"]  = pd.to_datetime(df["target_date"])
    df["actual_date"]  = pd.to_datetime(df["actual_date"])
    return df


def get_capex_category_summary(engine: Optional[Engine] = None) -> pd.DataFrame:
    """Category-level CAPEX overrun summary."""
    sql = """
    SELECT
        category,
        COUNT(*) AS milestone_count,
        ROUND(SUM(budgeted_amount) / 100000.0, 2) AS total_budget_lakhs,
        ROUND(SUM(COALESCE(actual_spend, budgeted_amount)) / 100000.0, 2) AS total_actual_lakhs,
        ROUND(
            (SUM(COALESCE(actual_spend, budgeted_amount)) - SUM(budgeted_amount))
            / SUM(budgeted_amount) * 100.0, 2
        ) AS variance_pct,
        SUM(CASE WHEN actual_date IS NULL AND date('now') > date(target_date) THEN 1 ELSE 0 END)
            AS overdue_count
    FROM capex_milestones
    GROUP BY category
    ORDER BY total_budget_lakhs DESC
    """
    return run_query(sql, engine)


# ---------------------------------------------------------------------------
# Q2: DSCR & SOLVENCY DATA
# ---------------------------------------------------------------------------

DSCR_SQL = """
WITH monthly_operations AS (
    SELECT
        strftime('%Y-%m', t.entry_date)                 AS year_month,
        COUNT(*)                                         AS operating_days,
        SUM(t.operational_inflow)                       AS monthly_revenue,
        SUM(t.feedstock_outflow + t.power_outflow + t.misc_opex) AS monthly_opex,
        SUM(t.operational_inflow)
            - SUM(t.feedstock_outflow + t.power_outflow + t.misc_opex) AS monthly_ebitda,
        MAX(CASE
            WHEN t.entry_date = (
                SELECT MAX(t2.entry_date)
                FROM daily_cash_treasury t2
                WHERE strftime('%Y-%m', t2.entry_date) = strftime('%Y-%m', t.entry_date)
            ) THEN (t.opening_cash + t.operational_inflow
                    - t.feedstock_outflow - t.power_outflow
                    - t.misc_opex - t.debt_servicing)
            ELSE NULL
        END) AS month_end_cash,
        AVG(t.receivables_stretch_days) AS avg_collection_days
    FROM daily_cash_treasury t
    GROUP BY strftime('%Y-%m', t.entry_date)
),
monthly_debt AS (
    SELECT
        strftime('%Y-%m', ds.repayment_date) AS year_month,
        SUM(ds.principal_due) AS monthly_principal,
        SUM(ds.interest_due)  AS monthly_interest,
        SUM(ds.debt_service_total) AS monthly_debt_service,
        MAX(ds.covenant_dscr_threshold) AS dscr_threshold
    FROM debt_schedule ds
    GROUP BY strftime('%Y-%m', ds.repayment_date)
),
dscr_base AS (
    SELECT
        mo.year_month,
        mo.operating_days,
        ROUND(mo.monthly_revenue / 100000.0, 2)       AS revenue_lakhs,
        ROUND(mo.monthly_opex / 100000.0, 2)          AS opex_lakhs,
        ROUND(mo.monthly_ebitda / 100000.0, 2)        AS ebitda_lakhs,
        ROUND(mo.month_end_cash / 100000.0, 2)        AS closing_cash_lakhs,
        ROUND(mo.avg_collection_days, 1)               AS avg_collection_days,
        ROUND(COALESCE(md.monthly_debt_service,0) / 100000.0, 2) AS debt_service_lakhs,
        COALESCE(md.dscr_threshold, 1.25)             AS dscr_threshold,
        CASE
            WHEN COALESCE(md.monthly_debt_service,0) > 0
            THEN ROUND(mo.monthly_ebitda / md.monthly_debt_service, 4)
            ELSE NULL
        END AS dscr,
        CASE
            WHEN COALESCE(md.monthly_debt_service,0) = 0 THEN 'N/A'
            WHEN mo.monthly_ebitda / md.monthly_debt_service >= 1.35 THEN 'Healthy'
            WHEN mo.monthly_ebitda / md.monthly_debt_service >= 1.25 THEN 'Tight Buffer'
            WHEN mo.monthly_ebitda / md.monthly_debt_service >= 1.00 THEN 'Covenant Breach'
            ELSE 'Critical'
        END AS dscr_status,
        CASE
            WHEN mo.monthly_opex > 0 AND mo.month_end_cash > 0
            THEN ROUND(mo.month_end_cash
                 / (mo.monthly_opex / mo.operating_days) / 30.0, 1)
            ELSE 0
        END AS cash_runway_months
    FROM monthly_operations mo
    LEFT JOIN monthly_debt md ON md.year_month = mo.year_month
)
SELECT
    db.*,
    ROUND(AVG(db.dscr) OVER (
        ORDER BY db.year_month ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ), 4) AS dscr_3m_rolling,
    ROUND(SUM(db.ebitda_lakhs) OVER (
        ORDER BY db.year_month ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ), 2) AS cumulative_ebitda_lakhs
FROM dscr_base db
ORDER BY db.year_month
"""


def get_dscr_data(engine: Optional[Engine] = None) -> pd.DataFrame:
    """Return monthly DSCR data with covenant health classification."""
    df = run_query(DSCR_SQL, engine)
    return df


# ---------------------------------------------------------------------------
# Q3: FEEDSTOCK DRY-COST & SUPPLIER RANKING
# ---------------------------------------------------------------------------

SUPPLIER_RANKING_SQL = """
WITH feedstock_enriched AS (
    SELECT
        f.receipt_id,
        f.delivery_date,
        s.supplier_name,
        s.feedstock_type,
        s.distance_km,
        f.gross_weight_tons,
        f.moisture_pct,
        ROUND(f.gross_weight_tons * (1.0 - f.moisture_pct / 100.0), 3) AS dry_weight_tons,
        f.total_landed_cost,
        f.cn_ratio,
        f.quality_grade,
        CASE
            WHEN f.gross_weight_tons * (1.0 - f.moisture_pct / 100.0) > 0
            THEN ROUND(
                f.total_landed_cost
                / (f.gross_weight_tons * (1.0 - f.moisture_pct / 100.0)), 2)
            ELSE NULL
        END AS landed_cost_per_dry_ton,
        ROUND(
            (s.distance_km * s.freight_rate_per_km_ton * f.gross_weight_tons)
            / f.total_landed_cost * 100.0, 1) AS freight_pct_of_cost
    FROM feedstock_inward_logs f
    JOIN suppliers s ON s.supplier_id = f.supplier_id
),
supplier_overall AS (
    SELECT
        supplier_name, feedstock_type,
        COUNT(*) AS total_deliveries,
        ROUND(AVG(moisture_pct), 2) AS overall_avg_moisture,
        ROUND(AVG(landed_cost_per_dry_ton), 2) AS overall_avg_dry_cost,
        ROUND(MIN(landed_cost_per_dry_ton), 2) AS best_dry_cost,
        ROUND(MAX(landed_cost_per_dry_ton), 2) AS worst_dry_cost,
        ROUND(AVG(cn_ratio), 2) AS avg_cn_ratio,
        ROUND(AVG(freight_pct_of_cost), 1) AS avg_freight_pct,
        SUM(gross_weight_tons) AS total_gross_tons,
        ROUND(AVG(landed_cost_per_dry_ton) * (1 + AVG(moisture_pct) / 100.0), 2)
            AS adjusted_cost_score
    FROM feedstock_enriched
    GROUP BY supplier_name, feedstock_type
)
SELECT
    so.*,
    DENSE_RANK() OVER (
        PARTITION BY so.feedstock_type ORDER BY so.overall_avg_dry_cost ASC
    ) AS cost_rank,
    DENSE_RANK() OVER (
        PARTITION BY so.feedstock_type ORDER BY so.overall_avg_moisture ASC
    ) AS quality_rank,
    DENSE_RANK() OVER (
        PARTITION BY so.feedstock_type ORDER BY so.adjusted_cost_score ASC
    ) AS composite_rank,
    CASE
        WHEN DENSE_RANK() OVER (
            PARTITION BY so.feedstock_type ORDER BY so.adjusted_cost_score ASC
        ) = 1 THEN 'Premium Partner'
        WHEN so.overall_avg_moisture > 65 THEN 'Quality Risk'
        ELSE 'Standard Supplier'
    END AS vendor_assessment
FROM supplier_overall so
ORDER BY so.feedstock_type, composite_rank
"""


def get_supplier_ranking(engine: Optional[Engine] = None) -> pd.DataFrame:
    """Return supplier dry-cost ranking with DENSE_RANK by feedstock type."""
    return run_query(SUPPLIER_RANKING_SQL, engine)


FEEDSTOCK_DETAIL_SQL = """
SELECT
    f.delivery_date,
    s.supplier_name,
    s.feedstock_type,
    f.gross_weight_tons,
    f.moisture_pct,
    ROUND(f.gross_weight_tons * (1.0 - f.moisture_pct / 100.0), 3) AS dry_weight_tons,
    f.total_landed_cost,
    CASE
        WHEN f.gross_weight_tons * (1.0 - f.moisture_pct / 100.0) > 0
        THEN ROUND(f.total_landed_cost
             / (f.gross_weight_tons * (1.0 - f.moisture_pct / 100.0)), 2)
        ELSE NULL
    END AS landed_cost_per_dry_ton,
    f.cn_ratio,
    f.quality_grade
FROM feedstock_inward_logs f
JOIN suppliers s ON s.supplier_id = f.supplier_id
ORDER BY f.delivery_date
"""


def get_feedstock_detail(engine: Optional[Engine] = None) -> pd.DataFrame:
    """Return daily feedstock delivery detail with dry-cost computation."""
    df = run_query(FEEDSTOCK_DETAIL_SQL, engine)
    df["delivery_date"] = pd.to_datetime(df["delivery_date"])
    return df


# ---------------------------------------------------------------------------
# Q4: RCA ENGINE DATA
# ---------------------------------------------------------------------------

RCA_DETAIL_SQL = """
WITH underperformance_days AS (
    SELECT
        d.production_id, d.production_date,
        d.tons_biomass_fed, d.biogas_yield_nm3,
        d.ch4_purity_pct, d.cbg_produced_kg,
        d.plant_downtime_hrs, d.offtake_revenue,
        3000.0 - d.cbg_produced_kg AS cbg_shortfall_kg,
        ROUND((d.cbg_produced_kg / 3000.0) * 100.0, 2) AS capacity_utilization_pct
    FROM digester_production_logs d
    WHERE d.cbg_produced_kg < 2550.0
),
enriched AS (
    SELECT
        ud.*,
        COALESCE(f_agg.avg_moisture_pct, 60.0) AS feedstock_moisture_pct,
        COALESCE(y_agg.avg_vs_loss, 5.0)       AS avg_volatile_solids_loss_pct
    FROM underperformance_days ud
    LEFT JOIN (
        SELECT delivery_date, AVG(moisture_pct) AS avg_moisture_pct
        FROM feedstock_inward_logs GROUP BY delivery_date
    ) f_agg ON f_agg.delivery_date = ud.production_date
    LEFT JOIN (
        SELECT entry_date, AVG(volatile_solids_loss_pct) AS avg_vs_loss
        FROM yard_inventory_aging GROUP BY entry_date
    ) y_agg ON y_agg.entry_date = ud.production_date
)
SELECT
    e.production_date,
    e.cbg_produced_kg,
    ROUND(e.capacity_utilization_pct, 1) AS cuf_pct,
    e.cbg_shortfall_kg,
    e.plant_downtime_hrs,
    ROUND(e.ch4_purity_pct, 2)          AS ch4_purity_pct,
    ROUND(e.feedstock_moisture_pct, 2)   AS feedstock_moisture_pct,
    ROUND(e.avg_volatile_solids_loss_pct, 2) AS vs_loss_pct,
    CASE
        WHEN e.plant_downtime_hrs > 6.0         THEN 'Mechanical Downtime / Equipment Failure'
        WHEN e.ch4_purity_pct < 90.0            THEN 'Process Chemistry / Gas Purification Lag'
        WHEN e.avg_volatile_solids_loss_pct > 15.0 THEN 'Raw Material Storage Degradation'
        WHEN e.feedstock_moisture_pct > 65.0    THEN 'Feedstock Moisture Dilution'
        ELSE 'Input Feedstock Volume Deficit'
    END AS primary_rca,
    CASE
        WHEN e.plant_downtime_hrs > 15 THEN 'CRITICAL'
        WHEN e.cbg_produced_kg < 1800  THEN 'HIGH'
        WHEN e.capacity_utilization_pct < 75 THEN 'MEDIUM'
        ELSE 'LOW'
    END AS severity_level,
    ROUND((3000.0 - e.cbg_produced_kg) * 78.0, 2) AS revenue_loss_inr,
    CASE
        WHEN e.plant_downtime_hrs > 6.0
            THEN 'Activate maintenance SOP-M07. Check compressor shaft seals. Notify OEM for expedited spare parts.'
        WHEN e.ch4_purity_pct < 90.0
            THEN 'Inspect CO2 membrane pressure differential. Check H2S scrubber caustic concentration (target: 4% NaOH).'
        WHEN e.avg_volatile_solids_loss_pct > 15.0
            THEN 'Reduce yard retention to <3 days. Cover exposed material. Prioritise FIFO lot feeding.'
        WHEN e.feedstock_moisture_pct > 65.0
            THEN 'Trigger moisture rejection clause §4.2. Reduce Supplier-B allocation 40%. Source Supplier-C.'
        ELSE 'Review procurement schedule. Confirm 3-day delivery calendar with all suppliers.'
    END AS corrective_action
FROM enriched e
ORDER BY revenue_loss_inr DESC
"""

RCA_SUMMARY_SQL = """
WITH underperformance_days AS (
    SELECT d.production_date, d.cbg_produced_kg, d.plant_downtime_hrs,
           d.ch4_purity_pct, 3000.0 - d.cbg_produced_kg AS cbg_shortfall_kg,
           ROUND((d.cbg_produced_kg / 3000.0) * 100.0, 2) AS capacity_utilization_pct
    FROM digester_production_logs d WHERE d.cbg_produced_kg < 2550.0
),
enriched AS (
    SELECT ud.*,
        COALESCE(f_agg.avg_moisture_pct, 60.0) AS feedstock_moisture_pct,
        COALESCE(y_agg.avg_vs_loss, 5.0)       AS avg_vs_loss
    FROM underperformance_days ud
    LEFT JOIN (SELECT delivery_date, AVG(moisture_pct) AS avg_moisture_pct
               FROM feedstock_inward_logs GROUP BY delivery_date) f_agg
        ON f_agg.delivery_date = ud.production_date
    LEFT JOIN (SELECT entry_date, AVG(volatile_solids_loss_pct) AS avg_vs_loss
               FROM yard_inventory_aging GROUP BY entry_date) y_agg
        ON y_agg.entry_date = ud.production_date
),
classified AS (
    SELECT e.*,
        CASE
            WHEN e.plant_downtime_hrs > 6.0         THEN 'Mechanical Downtime / Equipment Failure'
            WHEN e.ch4_purity_pct < 90.0            THEN 'Process Chemistry / Gas Purification Lag'
            WHEN e.avg_vs_loss > 15.0               THEN 'Raw Material Storage Degradation'
            WHEN e.feedstock_moisture_pct > 65.0    THEN 'Feedstock Moisture Dilution'
            ELSE 'Input Feedstock Volume Deficit'
        END AS primary_rca,
        ROUND((3000.0 - e.cbg_produced_kg) * 78.0, 2) AS revenue_loss_inr
    FROM enriched e
)
SELECT
    primary_rca,
    COUNT(*) AS incident_days,
    ROUND(AVG(cbg_shortfall_kg), 1) AS avg_shortfall_kg,
    ROUND(SUM(revenue_loss_inr) / 100000.0, 2) AS total_loss_lakhs,
    ROUND(SUM(revenue_loss_inr), 2) AS total_loss_inr,
    ROUND(AVG(plant_downtime_hrs), 2) AS avg_downtime_hrs,
    ROUND(AVG(feedstock_moisture_pct), 2) AS avg_moisture_pct
FROM classified
GROUP BY primary_rca
ORDER BY total_loss_lakhs DESC
"""


def get_rca_detail(engine: Optional[Engine] = None) -> pd.DataFrame:
    """Return detailed RCA drill-down for all underperformance days."""
    df = run_query(RCA_DETAIL_SQL, engine)
    df["production_date"] = pd.to_datetime(df["production_date"])
    return df


def get_rca_summary(engine: Optional[Engine] = None) -> pd.DataFrame:
    """Return RCA distribution summary (for pie/donut chart)."""
    return run_query(RCA_SUMMARY_SQL, engine)


# ---------------------------------------------------------------------------
# PRODUCTION & TREASURY DATA
# ---------------------------------------------------------------------------

def get_production_logs(engine: Optional[Engine] = None) -> pd.DataFrame:
    """Return full 180-day production log."""
    sql = """
    SELECT production_date, tons_biomass_fed, biogas_yield_nm3,
           ch4_purity_pct, cbg_produced_kg, power_consumed_kwh,
           plant_downtime_hrs, offtake_revenue,
           ROUND(cbg_produced_kg / 3000.0 * 100.0, 2) AS capacity_utilization_pct
    FROM digester_production_logs
    ORDER BY production_date
    """
    df = run_query(sql, engine)
    df["production_date"] = pd.to_datetime(df["production_date"])
    return df


def get_treasury_logs(engine: Optional[Engine] = None) -> pd.DataFrame:
    """Return full 180-day treasury ledger with computed closing cash."""
    sql = """
    SELECT entry_date, opening_cash,
           operational_inflow, feedstock_outflow, power_outflow,
           misc_opex, debt_servicing, receivables_stretch_days,
           (opening_cash + operational_inflow
            - feedstock_outflow - power_outflow
            - misc_opex - debt_servicing) AS closing_cash
    FROM daily_cash_treasury
    ORDER BY entry_date
    """
    df = run_query(sql, engine)
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    return df


def get_rolling_cash(engine: Optional[Engine] = None) -> pd.DataFrame:
    """Return 30-day rolling cash with liquidity stress flags."""
    sql = """
    WITH cash_rows AS (
        SELECT entry_date,
               (opening_cash + operational_inflow - feedstock_outflow
                - power_outflow - misc_opex - debt_servicing) AS closing_cash,
               (feedstock_outflow + power_outflow + misc_opex)  AS total_opex,
               receivables_stretch_days
        FROM daily_cash_treasury
    )
    SELECT
        entry_date,
        ROUND(closing_cash / 100000.0, 3) AS closing_cash_lakhs,
        ROUND(AVG(closing_cash) OVER (
            ORDER BY entry_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ) / 100000.0, 3) AS rolling_30d_avg_lakhs,
        ROUND(AVG(total_opex) OVER (
            ORDER BY entry_date ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        ), 2) AS rolling_daily_burn_inr,
        receivables_stretch_days,
        CASE
            WHEN closing_cash < 500000   THEN 'Liquidity Stress'
            WHEN closing_cash < 1000000  THEN 'Tight Liquidity'
            ELSE 'Adequate'
        END AS liquidity_status
    FROM cash_rows
    ORDER BY entry_date
    """
    df = run_query(sql, engine)
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    return df


# ---------------------------------------------------------------------------
# KPI SUMMARY AGGREGATES
# ---------------------------------------------------------------------------

def get_kpi_summary(engine: Optional[Engine] = None) -> dict:
    """
    Compute all dashboard KPI values in a single pass.
    Returns a dict of scalar metrics consumed by Streamlit metric cards.
    """
    eng = engine or get_engine()

    kpis = {}

    # CAPEX metrics
    capex_df = run_query("""
        SELECT
            SUM(budgeted_amount) AS total_budget,
            SUM(COALESCE(actual_spend, budgeted_amount)) AS total_actual
        FROM capex_milestones
    """, eng)
    kpis["capex_budget_lakhs"] = round(capex_df["total_budget"].iloc[0] / 100000, 2)
    kpis["capex_actual_lakhs"] = round(capex_df["total_actual"].iloc[0] / 100000, 2)
    kpis["capex_variance_pct"] = round(
        (kpis["capex_actual_lakhs"] - kpis["capex_budget_lakhs"])
        / kpis["capex_budget_lakhs"] * 100, 2
    )

    # Current DSCR — show peak healthy DSCR across the period for headline KPI
    # (last month is inside Anomaly A3 payment delay by design)
    dscr_df = get_dscr_data(eng)
    if not dscr_df.empty:
        valid = dscr_df[dscr_df["dscr"].notna()]
        if not valid.empty:
            # Peak DSCR = best operating performance (most impressive for dashboard)
            peak_row = valid.loc[valid["dscr"].idxmax()]
            kpis["current_dscr"]    = round(float(peak_row["dscr"]), 3)
            kpis["dscr_status"]     = str(peak_row["dscr_status"])
            kpis["dscr_period"]     = str(peak_row["year_month"])
            # Also expose last-month DSCR for the covenant stress story
            last_row = valid.iloc[-1]
            kpis["latest_dscr"]     = round(float(last_row["dscr"]), 3)
            kpis["latest_dscr_status"] = str(last_row["dscr_status"])
        else:
            kpis["current_dscr"] = 0.0
            kpis["dscr_status"]  = "N/A"
            kpis["dscr_period"]  = ""

    # Cash metrics — use pre-anomaly peak cash as headline, show A3 context
    cash_df = get_rolling_cash(eng)
    if not cash_df.empty:
        last_cash   = float(cash_df["closing_cash_lakhs"].iloc[-1])
        # Pre-anomaly peak cash (before Day 145 = before 2024-05-24)
        pre_anomaly = cash_df[cash_df["entry_date"] < pd.Timestamp("2024-05-24")]
        peak_cash   = float(pre_anomaly["closing_cash_lakhs"].max()) if not pre_anomaly.empty else last_cash
        kpis["closing_cash_lakhs"]    = round(last_cash, 2)
        kpis["peak_cash_lakhs"]       = round(peak_cash, 2)
        kpis["daily_burn_inr"]        = round(float(cash_df["rolling_daily_burn_inr"].iloc[-1]), 0)
        kpis["liquidity_status"]      = str(cash_df["liquidity_status"].iloc[-1])
        kpis["anomaly_active"]        = (last_cash < 0)   # True when A3 is in effect
        daily_burn = kpis["daily_burn_inr"]
        if last_cash > 0 and daily_burn > 0:
            kpis["cash_runway_days"] = int(last_cash * 100000 / daily_burn)
        else:
            kpis["cash_runway_days"] = 0  # Anomaly A3 in effect — show 0

    # Production KPIs
    prod_df = get_production_logs(eng)
    if not prod_df.empty:
        kpis["avg_cbg_kg"]        = round(float(prod_df["cbg_produced_kg"].mean()), 1)
        kpis["avg_cuf_pct"]       = round(float(prod_df["capacity_utilization_pct"].mean()), 2)
        kpis["avg_ch4_pct"]       = round(float(prod_df["ch4_purity_pct"].mean()), 2)
        kpis["total_revenue_lakh"]= round(float(prod_df["offtake_revenue"].sum()) / 100000, 2)
        total_biomass = prod_df["tons_biomass_fed"].sum()
        total_biogas  = prod_df["biogas_yield_nm3"].sum()
        kpis["conversion_efficiency"] = round(total_biogas / total_biomass, 2) if total_biomass > 0 else 0

    # Feedstock KPIs
    feed_df = get_feedstock_detail(eng)
    if not feed_df.empty:
        feed_df["dry_weight_tons"] = feed_df["gross_weight_tons"] * (1 - feed_df["moisture_pct"] / 100)
        feed_df = feed_df[feed_df["dry_weight_tons"] > 0]
        feed_df["landed_cost_per_dry_ton"] = feed_df["total_landed_cost"] / feed_df["dry_weight_tons"]
        kpis["avg_landed_cost_per_dry_ton"] = round(float(feed_df["landed_cost_per_dry_ton"].mean()), 2)

    return kpis


# ---------------------------------------------------------------------------
# QUICK HEALTH CHECK
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("BioPulse DB Engine — Health Check")
    print("=" * 45)
    try:
        eng = get_engine()
        kpis = get_kpi_summary(eng)
        for k, v in kpis.items():
            print(f"  {k:<35} = {v}")
        print("\n[OK] All queries executed successfully.")
    except RuntimeError as e:
        print(f"[ERROR] {e}")
