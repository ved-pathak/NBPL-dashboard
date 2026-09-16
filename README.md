# CBG Plant Operations & Capital Planning Dashboard Tool

> **A production-grade operational intelligence and quantitative financial modeling dashboard tool for a 3.0 TPD Compressed Bio-Gas (CBG) industrial facility — integrating capital expenditure (CAPEX) tracking, debt service solvency monitoring (DSCR), supply-chain unit economics, and automated operational Root Cause Analysis (RCA).**

---

## 📌 Executive Overview

This platform is an industrial analytics dashboard tool designed to bridge the gap between corporate infrastructure finance and daily chemical process operations. 

Modern bio-energy projects often face a disconnect between:
1. **Capital Solvency & Debt Covenants**: Lenders require rigid Debt Service Coverage Ratios (DSCR $\ge$ 1.25x) and liquidity buffers.
2. **Manufacturing & Feedstock Dynamics**: Agricultural feedstock pricing, moisture dilution, storage aging, and mechanical compressor downtime directly drive daily operational cash flows.

The dashboard tool provides an interactive, executive-facing intelligence suite that unifies relational transactional data, physical mass-balance stoichiometry, and cash-basis treasury modeling into an actionable dark-mode interface.

---

## 🏗️ Architecture & Data Pipeline

```
┌─────────────────────────────────────────────────────────────────────┐
│          CBG Plant Operations & Capital Planning Dashboard          │
│            Commercial 3.0 TPD Compressed Bio-Gas Facility           │
└─────────────────────────────────────────────────────────────────────┘
                                │
         ┌──────────────────────┼──────────────────────┐
         ▼                      ▼                      ▼
  ┌─────────────┐       ┌─────────────┐       ┌─────────────┐
  │ schema.sql  │       │generate_data│       │analytics_   │
  │             │       │   .py       │       │queries.sql  │
  │ 7-Table 3NF │       │             │       │             │
  │ Relational  │──────▶│ 12-mo CAPEX │       │ Q1: S-Curve │
  │ Schema      │       │ 180-day Ops │       │ Q2: DSCR    │
  │ FK/CHECK    │       │ Inventory   │       │ Q3: DRY COST│
  │ GENERATED   │       │ Lag & Vol.  │       │ Q4: RCA     │
  │ COLUMNS     │       │ Pricing     │       │ Q5: ROLLING │
  └──────┬──────┘       └──────┬──────┘       └──────┬──────┘
         │                     │                     │
         └──────────────┬──────┘                     │
                        ▼                            │
              ┌───────────────────┐                  │
              │   cbg_plant.db    │◀─────────────────┘
              │   (SQLite3 Engine)│
              └────────┬──────────┘
                       │
                       ▼
              ┌───────────────────┐
              │   db_engine.py    │
              │                   │
              │ SQLAlchemy Engine │
              │ Pandas DataFrames │
              │ KPI Aggregation   │
              └────────┬──────────┘
                       │
                       ▼
              ┌───────────────────┐
              │     app.py        │
              │                   │
              │  Streamlit Dark   │
              │  Dashboard Tool   │
              │                   │
              │  View 1: Capital  │
              │  Planning &       │
              │  Solvency         │
              │                   │
              │  View 2: Feedstock│
              │  & RCA Hub        │
              └───────────────────┘
```

---

## 📂 Project Structure

```
NBPL-dashboard/
├── schema.sql              # 3NF DDL — 7 relational tables, FK constraints, generated columns, indexes
├── generate_data.py        # Calibrated data generator — 12-mo CAPEX + 180-day ops with inventory lag
├── analytics_queries.sql   # Analytical SQL suite — CTEs, window functions, and RCA priority waterfall
├── db_engine.py            # SQLAlchemy query execution and business logic layer
├── app.py                  # Interactive Streamlit dashboard (dark theme, 2 views, 6+ Plotly charts)
├── cbg_plant.db            # Pre-seeded SQLite database ready for immediate deployment
├── requirements.txt        # Python package dependencies
├── .gitignore              # Repository hygiene configuration
└── README.md               # System documentation and architectural specifications
```

---

## 🚀 Quickstart & Local Setup

### Prerequisites
- Python 3.10+
- pip

### Step 1: Clone the Repository
```bash
git clone https://github.com/ved-pathak/NBPL-dashboard.git
cd NBPL-dashboard
```

### Step 2: Install Dependencies
```bash
pip install -r requirements.txt
```

### Step 3: Run Database Health Check
```bash
python db_engine.py
```

### Step 4: Launch the Dashboard Tool
```bash
streamlit run app.py
```
Access the dashboard in your browser at **`http://localhost:8501`**.

*(Optional)* To re-seed or regenerate the operational database from scratch:
```bash
python generate_data.py
```

---

## 📊 Dashboard Modules & Key Views

### View 1: Capital Planning & Debt Solvency
- **Headline Financial KPIs**: Total CAPEX deployed vs. budget variance, Peak and Current DSCR, daily cash burn rate, and available liquidity runway.
- **CAPEX S-Curve & Category Overrun Analysis**: Cumulative planned vs. actual investment tracking across Civil Works, Mechanical Equipment, Electrical & Grid, and Statutory Approvals.
- **Monthly DSCR Monitoring**: Tracks debt servicing against EBITDA with color-coded covenant zones (Healthy $\ge 1.35x$, Warning $1.25x-1.35x$, Breach $< 1.25x$).
- **30-Day Rolling Treasury Cash Position**: Cash liquidity balance overlaid with the mandatory Debt Service Reserve Account (DSRA) reserve threshold.

### View 2: Feedstock Unit Economics & Operational RCA Hub
- **Operational KPIs**: Average landed cost per dry ton, plant Capacity Utilization Factor (CUF%), methane purity ($\text{CH}_4\%$), and specific biogas yield.
- **Supplier Dry-Cost Matrix**: Interactive bubble chart ranking suppliers by moisture-adjusted landed cost per dry ton vs. delivered volume.
- **Daily Production Efficiency**: Dual-axis operational timeline tracking daily wet biomass feed rate against post-compression CBG output (kg/day) with alert thresholds.
- **Priority-Waterfall RCA Diagnosis**: Multi-stage classification isolating the primary root causes of underperformance (Mechanical Downtime, Process Chemistry, Storage Degradation, Feedstock Moisture Dilution, or Feedstock Volume Deficit) with recommended corrective action SOPs.

---

## 🗄️ Relational Data Model (3NF)

```
suppliers (1) ──────< feedstock_inward_logs (1) ──────< yard_inventory_aging
                               │
                               └── (consumed by) ──▶ digester_production_logs
                                                             │
capex_milestones (standalone)                                ▼
debt_schedule (standalone)                 daily_cash_treasury
```

### Table Dictionary
- **`capex_milestones`**: 21 milestone records across 4 construction phases. Includes stored generated columns for budget variance and overdue status.
- **`debt_schedule`**: Monthly amortization tranches for term debt with stored generated columns for total debt service (`principal + interest`).
- **`suppliers`**: Sourcing dimensions with contracted base rates, transportation distances, and freight matrices.
- **`feedstock_inward_logs`**: Gate delivery receipts recording gross tonnage, moisture percentage, C:N ratio, and volatile solids content.
- **`yard_inventory_aging`**: FIFO yard bay tracking recording arrival, storage duration, feed date, and volatile solids degradation.
- **`digester_production_logs`**: Daily anaerobic digestion metrics (feed rate, raw biogas volume, methane purity, compressed CBG output, parasitic power, and plant downtime).
- **`daily_cash_treasury`**: Daily liquidity ledger modeling operational revenue collections, operational expenditures, power tariffs, and debt service outflows.

---

## 🧠 Core Analytical SQL Modules

### 1. CAPEX Cumulative S-Curve (Window Functions)
Tracks cumulative planned vs. actual project deployment across the 12-month construction phase.
```sql
WITH capex_enriched AS (
    SELECT
        milestone_id,
        category,
        target_date,
        budgeted_amount,
        COALESCE(actual_spend, budgeted_amount) AS actual_spend_safe,
        ROUND((COALESCE(actual_spend, budgeted_amount) - budgeted_amount)
              / budgeted_amount * 100.0, 2) AS variance_pct
    FROM capex_milestones
)
SELECT
    milestone_id,
    category,
    target_date,
    budgeted_amount,
    actual_spend_safe,
    variance_pct,
    SUM(budgeted_amount) OVER (
        ORDER BY target_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_budget,
    SUM(actual_spend_safe) OVER (
        ORDER BY target_date
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_actual
FROM capex_enriched
ORDER BY target_date;
```
*Technical Note*: Using explicit `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` frame definitions ensures running cumulative totals evaluate consistently even when multiple construction milestones share the same target date.

---

### 2. Debt Service Coverage Ratio (DSCR) Covenant Monitoring
Evaluates monthly cash-basis EBITDA against senior debt obligations.
```sql
WITH monthly_operations AS (
    SELECT
        strftime('%Y-%m', entry_date) AS year_month,
        SUM(operational_inflow) AS monthly_revenue,
        SUM(feedstock_outflow + power_outflow + misc_opex) AS monthly_opex,
        SUM(operational_inflow) - SUM(feedstock_outflow + power_outflow + misc_opex) AS monthly_ebitda
    FROM daily_cash_treasury
    GROUP BY strftime('%Y-%m', entry_date)
)
SELECT
    mo.year_month,
    mo.monthly_ebitda,
    ds.debt_service_total,
    ROUND(mo.monthly_ebitda / ds.debt_service_total, 4) AS dscr,
    CASE
        WHEN mo.monthly_ebitda / ds.debt_service_total >= 1.35 THEN 'Healthy'
        WHEN mo.monthly_ebitda / ds.debt_service_total >= 1.25 THEN 'Tight Buffer'
        ELSE 'Covenant Breach'
    END AS dscr_status
FROM monthly_operations mo
JOIN debt_schedule ds ON strftime('%Y-%m', ds.repayment_date) = mo.year_month;
```
*Technical Note*: Infrastructure debt term sheets mandate maintaining a minimum DSCR of $1.25\times$. The query flags covenant breaches to alert treasury before lender reserve step-in clauses are triggered.

---

### 3. Supplier Dry-Weight Unit Cost Ranking (Conditional Partitions)
Uncovers true supplier economics by standardizing raw wet feedstock to a bone-dry solids basis.
```sql
WITH feedstock_enriched AS (
    SELECT
        s.supplier_name,
        s.feedstock_type,
        f.gross_weight_tons,
        f.moisture_pct,
        f.gross_weight_tons * (1.0 - f.moisture_pct / 100.0) AS dry_weight_tons,
        f.total_landed_cost,
        f.total_landed_cost / (f.gross_weight_tons * (1.0 - f.moisture_pct / 100.0)) AS landed_cost_per_dry_ton
    FROM feedstock_inward_logs f
    JOIN suppliers s ON s.supplier_id = f.supplier_id
),
supplier_avg AS (
    SELECT
        supplier_name,
        feedstock_type,
        AVG(moisture_pct) AS avg_moisture,
        AVG(landed_cost_per_dry_ton) AS avg_dry_cost
    FROM feedstock_enriched
    GROUP BY supplier_name, feedstock_type
)
SELECT
    supplier_name,
    feedstock_type,
    avg_moisture,
    avg_dry_cost,
    DENSE_RANK() OVER (
        PARTITION BY feedstock_type
        ORDER BY avg_dry_cost ASC
    ) AS cost_rank
FROM supplier_avg;
```
*Technical Note*: `DENSE_RANK()` partitioned by `feedstock_type` prevents rank gaps and avoids false comparisons across disparate commodity types (e.g. Press Mud vs. Cattle Dung).

---

### 4. Priority-Waterfall Root Cause Analysis (RCA Engine)
Isolates operational underperformance days (< 2,550 kg CBG) into mutually exclusive diagnostic categories.
```sql
WITH underperformance_days AS (
    SELECT d.*, 3000.0 - d.cbg_produced_kg AS cbg_shortfall_kg
    FROM digester_production_logs d
    WHERE d.cbg_produced_kg < 2550.0
),
enriched AS (
    SELECT
        ud.*,
        COALESCE(f_agg.avg_moisture_pct, 64.0) AS feedstock_moisture_pct,
        COALESCE(y_agg.avg_vs_loss, 4.0) AS avg_vs_loss
    FROM underperformance_days ud
    LEFT JOIN (
        SELECT y.feed_date, AVG(f.moisture_pct) AS avg_moisture_pct
        FROM yard_inventory_aging y
        JOIN feedstock_inward_logs f ON y.receipt_id = f.receipt_id
        GROUP BY y.feed_date
    ) f_agg ON f_agg.feed_date = ud.production_date
    LEFT JOIN (
        SELECT feed_date, AVG(volatile_solids_loss_pct) AS avg_vs_loss
        FROM yard_inventory_aging GROUP BY feed_date
    ) y_agg ON y_agg.feed_date = ud.production_date
)
SELECT
    production_date,
    cbg_produced_kg,
    plant_downtime_hrs,
    feedstock_moisture_pct,
    avg_vs_loss,
    CASE
        WHEN plant_downtime_hrs > 6.0      THEN 'Mechanical Downtime / Equipment Failure'
        WHEN ch4_purity_pct < 90.0         THEN 'Process Chemistry / Gas Purification Lag'
        WHEN avg_vs_loss > 15.0            THEN 'Raw Material Storage Degradation'
        WHEN feedstock_moisture_pct > 68.0 THEN 'Feedstock Moisture Dilution'
        ELSE 'Input Feedstock Volume Deficit'
    END AS primary_rca,
    ROUND((3000.0 - cbg_produced_kg) * 78.0, 2) AS revenue_loss_inr
FROM enriched
ORDER BY revenue_loss_inr DESC;
```
*Technical Note*: The waterfall prioritizes mechanical failure because downtime causes an absolute output halt regardless of feedstock chemistry. Joins are keyed on `feed_date` to preserve inventory retention lag.

---

## ⚡ Operational Stress Scenarios (Simulated Anomalies)

The dataset incorporates three realistic operational anomaly clusters to stress-test financial resilience and automated diagnosis:

| Scenario | Window | Root Event | Operational & Financial Impact |
|---|---|---|---|
| **A1: Feedstock Quality Shock** | Days 40–52 (delivered) <br> Days 42–54 (digested) | Compromised press mud delivered at ~72% moisture (vs. 58% baseline) | Landed dry cost surges +32%; organic digester gas yield drops by ~28%; methane purity drops below 92% MNGL specification. |
| **A2: Mechanical Compressor Failure** | Days 100–110 | Raw gas compressor seal failure causing 18 hours/day plant downtime | Daily fulfillment falls to 65% of target; triggers ₹2.5L in penalty deductions under PSU offtake agreement. |
| **A3: Working Capital Liquidity Freeze** | Days 145–165 | Offtaker payment cycle stretches from standard 30 days to 75 days | Cash collections freeze; closing treasury balances plunge to negative values; monthly DSCR covenants are breached (< 1.0x). |

---

## 🧪 Process Engineering & Mass Balance Parameters

| Parameter | Design Specification | Scientific Basis |
|---|---|---|
| Nameplate CBG Capacity | 3,000 kg/day (3.0 TPD) | Commercial medium-scale bio-refinery |
| Wet Biomass Feed Rate | ~18.0 tons/day | Sized for ~16.5% CBG yield on wet blend basis |
| Sourcing Recipe | ~65% Press Mud, ~30% Cattle Dung, ~5% Residue | Optimal mesophilic C:N balancing (22–28) |
| Baseline Raw Biogas Yield | 200–220 $\text{Nm}^3/\text{ton}$ wet biomass | Mesophilic CSTR anaerobic digestion at 38°C |
| Raw Biogas Composition | ~63% $\text{CH}_4$, ~35% $\text{CO}_2$, balance $\text{H}_2\text{S}$ | Agricultural organic residue digestion |
| Scrubbed Bio-Methane Purity | 92.5% – 95.5% $\text{CH}_4$ | Water-wash + polymeric membrane separation |
| CBG Delivery Pressure | 200 bar | Standard cascade dispensing pressure |
| Offtake Revenue Baseline | ₹78.0 / kg | Public sector oil marketing company (OMC) off-take index |
| Senior Debt Financing | ₹4.50 Crore (11.5% p.a., 2-year amort.) | Commercial project term loan tranche |

---

## 📜 Architectural Decisions & Scalability Roadmap

1. **Inventory Lag vs. Gate Delivery Coupling**:
   - In industrial manufacturing, material delivered at the plant gate sits in raw material storage bays prior to feeding. Mapping quality metrics to `feed_date = delivery_date + storage_lag` preserves supply-chain physical causality, ensuring root cause analyses reflect true operational consumption.
2. **Stochastic Pricing Multipliers**:
   - Agricultural commodity procurement contracts incorporate market price drift. Integrating daily stochastic multipliers (-1.5% to +2.5%) ensures landed cost variance models realistic procurement conditions.
3. **Database Architecture & Enterprise Migration**:
   - SQLite was selected for portability, zero-configuration local execution, and embedded deployment. Domain constraints are strictly enforced via `CHECK` and `GENERATED ALWAYS AS STORED` columns.
   - *Enterprise Path*: For multi-facility enterprise deployments (>1M daily sensor readings), the architecture transitions smoothly to PostgreSQL / TimescaleDB with dbt for modular data transformation and Snowflake/BigQuery for analytical warehousing.

---

*CBG Operations & Capital Planning Dashboard Tool — Industrial Analytics & Data Engineering Reference Architecture.*
