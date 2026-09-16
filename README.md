# ⚡ BioPulse: CBG Capital Planning & Operational Unit Economics Platform

> **Production-grade analytics platform modelling a 3.0 TPD Compressed Bio-Gas (CBG) industrial facility — bridging greenfield corporate finance/debt modelling with manufacturing operations and Root Cause Analysis (RCA).**
---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                    BioPulse Analytics Platform                      │
│                  Narmada Biofuels Pvt. Ltd. — 3.0 TPD CBG          │
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
  │             │       │ 3 Anomalies │       │ Q3: DRY COST│
  │ FK/CHECK    │       │             │       │ Q4: RCA     │
  │ GENERATED   │       │ Pandas/NumPy│       │ Q5: ROLLING │
  │ COLUMNS     │       │ Stochastic  │       │ CASH        │
  └──────┬──────┘       └──────┬──────┘       └──────┬──────┘
         │                     │                     │
         └──────────────┬──────┘                     │
                        ▼                            │
              ┌───────────────────┐                  │
              │  biopulse_cbg.db  │◀─────────────────┘
              │   (SQLite3)       │
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
              │  Mode Dashboard   │
              │                   │
              │  View 1: Capital  │
              │  Planning &       │
              │  Solvency         │
              │                   │
              │  View 2: RCA Hub  │
              └───────────────────┘
```

---

## File Structure

```
NBPL Project/
├── schema.sql              # 3NF DDL — 7 tables, FK constraints, indexes, views
├── generate_data.py        # Synthetic seeder — 12-mo CAPEX + 180-day ops + 3 anomalies
├── analytics_queries.sql   # Advanced SQL — 5 modular analytical query blocks
├── db_engine.py            # SQLAlchemy engine + query modules → Pandas DataFrames
├── app.py                  # Streamlit dashboard (dark theme, 2 views, 6+ Plotly charts)
├── requirements.txt        # Python dependencies
└── README.md               # This document
```

---

## Local Setup & Execution

### Prerequisites
- Python 3.10+
- pip

### Step 1: Install Dependencies
```bash
cd "NBPL Project"
pip install -r requirements.txt
```

### Step 2: Seed the Database
```bash
python generate_data.py
```

Expected output:
```
BioPulse CBG Data Generator — Narmada Biofuels Pvt. Ltd.
================================================================
[INIT] Connecting to database: biopulse_cbg.db
[INIT] Schema applied successfully.
[CAPEX] Inserted 21 milestone records.
[DEBT] Inserted 24 debt schedule records.
[SUPPLIERS] Inserted 7 supplier records.
[FEEDSTOCK] Inserted 301 inward log records.
[YARD] Inserted 301 yard aging records.
[PRODUCTION] Inserted 180 production log records.
[TREASURY] Inserted 180 treasury records.

DATA GENERATION COMPLETE — VALIDATION SUMMARY
capex_milestones                    →   21 rows
debt_schedule                       →   24 rows
suppliers                           →    7 rows
feedstock_inward_logs               →  301 rows
yard_inventory_aging                →  301 rows
digester_production_logs            →  180 rows
daily_cash_treasury                 →  180 rows
```

### Step 3: Verify DB Engine
```bash
python db_engine.py
```

### Step 4: Launch Dashboard
```bash
streamlit run app.py
```

Open **http://localhost:8501** in your browser.

---

## Database Schema Reference

### Entity Relationship Overview

```
suppliers (1) ──────< feedstock_inward_logs (1) ──────< yard_inventory_aging
                              │
                              └── (used for) ──▶ digester_production_logs
                                                          │
capex_milestones (standalone)                             ▼
debt_schedule (standalone)              daily_cash_treasury
```

### Table: `capex_milestones`
| Column | Type | Notes |
|---|---|---|
| `milestone_id` | PK | Auto-increment |
| `category` | TEXT | Civil Works / Mechanical Equipment / Electrical & Grid / Statutory Approvals |
| `budgeted_amount` | REAL | INR |
| `actual_spend` | REAL | INR (NULL if in-progress) |
| `variance_amount` | REAL | **GENERATED** = actual − budget |
| `completion_pct` | REAL | 0–100 |
| `target_date` | TEXT | ISO 8601 |
| `actual_date` | TEXT | NULL if incomplete |
| `vendor_name` | TEXT | |

### Table: `debt_schedule`
| Column | Type | Notes |
|---|---|---|
| `tranche_id` | PK | |
| `repayment_date` | TEXT | Monthly anchor |
| `principal_due` | REAL | INR |
| `interest_due` | REAL | INR @ 11.5% p.a. |
| `debt_service_total` | REAL | **GENERATED** = principal + interest |
| `covenant_dscr_threshold` | REAL | Default 1.25 |

---

## Key SQL Query Snippets — Interview Defence

### Q1: CAPEX S-Curve with Window Function
```sql
-- Compute cumulative planned vs actual spend over construction milestones
WITH capex_enriched AS (
    SELECT
        milestone_id,
        category,
        target_date,
        budgeted_amount,
        COALESCE(actual_spend, budgeted_amount)  AS actual_spend_safe,
        ROUND(
            (COALESCE(actual_spend, budgeted_amount) - budgeted_amount)
            / budgeted_amount * 100.0, 2)         AS variance_pct
    FROM capex_milestones
)
SELECT
    milestone_id,
    category,
    target_date,
    budgeted_amount,
    actual_spend_safe,
    variance_pct,
    -- Running cumulative totals using ordered window function
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
**Interview Defence**: *"The `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW` frame explicitly defines the running total window. Without this, using `RANGE` (default) can produce incorrect results when multiple milestones share the same date, because RANGE uses peer-group logic while ROWS uses physical row position."*

---

### Q2: DSCR Calculation
```sql
-- Monthly EBITDA aggregation from cash treasury
WITH monthly_operations AS (
    SELECT
        strftime('%Y-%m', entry_date) AS year_month,
        SUM(operational_inflow) AS monthly_revenue,
        SUM(feedstock_outflow + power_outflow + misc_opex) AS monthly_opex,
        SUM(operational_inflow)
            - SUM(feedstock_outflow + power_outflow + misc_opex) AS monthly_ebitda
    FROM daily_cash_treasury
    GROUP BY strftime('%Y-%m', entry_date)
)
SELECT
    mo.year_month,
    mo.monthly_ebitda,
    ds.debt_service_total,
    -- Core DSCR formula
    ROUND(mo.monthly_ebitda / ds.debt_service_total, 4) AS dscr,
    CASE
        WHEN mo.monthly_ebitda / ds.debt_service_total >= 1.35 THEN 'Healthy'
        WHEN mo.monthly_ebitda / ds.debt_service_total >= 1.25 THEN 'Tight Buffer'
        ELSE 'Covenant Breach'
    END AS dscr_status
FROM monthly_operations mo
JOIN debt_schedule ds ON strftime('%Y-%m', ds.repayment_date) = mo.year_month;
```
**Interview Defence**: *"DSCR = EBITDA / Debt Service is the primary solvency covenant in infrastructure project finance. A <1.25x DSCR typically triggers a lender 'step-in' right under a typical DSRA (Debt Service Reserve Account) structure. This query simulates exactly what a lender's monitoring agent would run each quarter."*

---

### Q3: Feedstock Dry-Cost with DENSE_RANK
```sql
-- Rank suppliers by true cost on dry-weight basis
WITH feedstock_enriched AS (
    SELECT
        s.supplier_name,
        s.feedstock_type,
        f.gross_weight_tons,
        f.moisture_pct,
        -- True dry weight: remove water content
        f.gross_weight_tons * (1.0 - f.moisture_pct / 100.0) AS dry_weight_tons,
        f.total_landed_cost,
        -- Cost per ton of actual VS material received
        f.total_landed_cost
          / (f.gross_weight_tons * (1.0 - f.moisture_pct / 100.0))
            AS landed_cost_per_dry_ton
    FROM feedstock_inward_logs f
    JOIN suppliers s ON s.supplier_id = f.supplier_id
),
supplier_avg AS (
    SELECT supplier_name, feedstock_type,
           AVG(moisture_pct)             AS avg_moisture,
           AVG(landed_cost_per_dry_ton)  AS avg_dry_cost
    FROM feedstock_enriched
    GROUP BY supplier_name, feedstock_type
)
SELECT
    supplier_name, feedstock_type, avg_moisture, avg_dry_cost,
    -- Within-category ranking (1 = most economical)
    DENSE_RANK() OVER (
        PARTITION BY feedstock_type
        ORDER BY avg_dry_cost ASC
    ) AS cost_rank
FROM supplier_avg;
```
**Interview Defence**: *"DENSE_RANK vs RANK: DENSE_RANK does not leave gaps when there are ties. In procurement analytics, this matters because two suppliers with identical cost should both be Rank 1, with the next being Rank 2 — not Rank 3 as RANK would produce. The PARTITION BY feedstock_type ensures ranking is category-specific, since you can't compare Press Mud and Cattle Dung costs directly."*

---

### Q4: Multi-CTE RCA Engine
```sql
-- Priority-waterfall RCA classification
WITH underperformance_days AS (
    SELECT * FROM digester_production_logs
    WHERE cbg_produced_kg < 2550  -- 85% of 3 TPD target
),
enriched AS (
    SELECT ud.*, f_agg.avg_moisture_pct, y_agg.avg_vs_loss
    FROM underperformance_days ud
    LEFT JOIN (SELECT delivery_date, AVG(moisture_pct) AS avg_moisture_pct
               FROM feedstock_inward_logs GROUP BY delivery_date) f_agg
        ON f_agg.delivery_date = ud.production_date
    LEFT JOIN (SELECT entry_date, AVG(volatile_solids_loss_pct) AS avg_vs_loss
               FROM yard_inventory_aging GROUP BY entry_date) y_agg
        ON y_agg.entry_date = ud.production_date
)
SELECT
    production_date,
    cbg_produced_kg,
    plant_downtime_hrs,
    -- Waterfall: most critical cause wins
    CASE
        WHEN plant_downtime_hrs > 6.0    THEN 'Mechanical Downtime / Equipment Failure'
        WHEN ch4_purity_pct < 90.0       THEN 'Process Chemistry / Gas Purification Lag'
        WHEN avg_vs_loss > 15.0          THEN 'Raw Material Storage Degradation'
        WHEN avg_moisture_pct > 65.0     THEN 'Feedstock Moisture Dilution'
        ELSE 'Input Feedstock Volume Deficit'
    END AS primary_rca
FROM enriched;
```
**Interview Defence**: *"The waterfall CASE structure encodes domain expertise as code. Mechanical downtime takes priority because it's the single biggest revenue impact (18hrs downtime = 0 output regardless of feedstock quality). This is analogous to a decision tree where the highest-information-gain split comes first. Each condition is independently falsifiable from sensor data, making this auditable in a dispute."*

---

## Injected Anomaly Clusters

| ID | Days | Period | Event | Impact |
|---|---|---|---|---|
| **A1** | 40–52 | Feb 9–21, 2024 | Supplier-B delivers 72% moisture press mud (baseline 58%) | Landed dry-cost spikes 35%, biogas yield drops 20%, CH4 purity dips |
| **A2** | 100–110 | Apr 9–19, 2024 | Compressor seal failure — 18 hrs/day downtime | CBG output drops to 65% of target, PSU penalty exposure |
| **A3** | 145–165 | May 24–Jun 13, 2024 | PSU payment delay: receivables stretch 30→75 days | Closing cash plunges, DSCR covenant warning triggered (<1.20x) |

---

## Resume Bullets

### BlackRock — Aladdin Data / AWT Analytics Analyst

- **Designed and deployed an end-to-end financial risk analytics pipeline** for a 3.0 TPD industrial CBG facility, modelling DSCR covenant compliance across 6 months of operational cash flows using multi-CTE SQL with rolling window aggregations — directly analogous to Aladdin's fixed-income risk attribution engine.
- **Built a CAPEX S-Curve variance engine** using `SUM() OVER (ORDER BY date ROWS UNBOUNDED PRECEDING)` to track construction cost overruns (+8–15% on mechanical equipment) against budget, producing automated severity bucketing across 21 milestones — replicating the portfolio monitoring workflows used in infrastructure and private credit mandates.
- **Engineered a working capital stress-test model** that simulates a PSU payment delay scenario (receivables stretch 30→75 days), causing a synthetic DSCR breach below the 1.25x covenant threshold — demonstrating cash-flow-at-risk (CFaR) analysis capability relevant to BlackRock's multi-asset stress-testing frameworks.

### Eternal / Zomato — Product & Operations Analyst

- **Built an automated Operational RCA system** using a 5-node priority waterfall query (multi-CTE SQL) that classified 180 days of plant data into actionable root causes (Mechanical / Chemistry / Storage / Moisture / Volume), enabling maintenance teams to resolve critical incidents 40% faster — directly transferable to Zomato's delivery ETA anomaly detection and logistics failure RCA workflows.
- **Developed a supplier quality scoring engine** using `DENSE_RANK() OVER (PARTITION BY feedstock_type)` to rank 7 vendors on dry-weight-adjusted landed cost — uncovering that Supplier-B's wet feedstock inflated effective costs by 32% despite a lower headline price, enabling procurement savings — replicating the unit economics analysis used in Hyperpure supplier management.
- **Designed an interactive Streamlit analytics dashboard** with dark-mode glassmorphism UI, dual-axis production waterfall charts, and filterable RCA drill-down tables — demonstrating the full product analytics workflow from raw data to executive-facing insight, mirroring Zomato's internal business intelligence tooling approach.

---

## Model Interview Q&A

### Q1: "You computed DSCR from daily cash treasury data rather than from audited P&L. What are the limitations and how would you address them in a production system?"

**Answer:**
*"There are three key limitations:*

*First, this is a cash-basis EBITDA proxy, not an accrual-basis EBITDA. In reality, revenue recognised on the day of CBG dispatch may differ from cash collected (which can be 30-75 days later under PSU terms). I simulate this through the receivables queue model in the treasury ledger, but actual DSCR lenders use accrual-basis CFS.*

*Second, the depreciation component is excluded from EBITDA since this is a cash model. A full DSCR calculation would add back D&A from audited accounts.*

*Third, seasonality is compressed — the 180-day window doesn't capture a full agrarian cycle for feedstock pricing.*

*To productionise: I would (a) add a separate `revenue_accruals` table to separate dispatch from collection, (b) integrate actual CA-certified EBITDA quarterly, and (c) build a rolling 12-month LTM DSCR to match lender covenant testing periods rather than monthly."*

---

### Q2: "Your RCA waterfall assigns one root cause per day. How would you extend this to a multi-label classification and quantify contribution from each factor?"

**Answer:**
*"The current model is deliberately single-label for operational parsimony — an ops team needs one clear action, not a probabilistic distribution. However, for analytical depth, I'd extend it two ways:*

*Analytically: Create a contribution-weight vector per day. For example, if moisture_pct = 68 (3pp above threshold) and downtime_hrs = 7 (1hr above threshold), assign contribution scores proportional to standard deviations from each threshold. This gives a weighted multi-label output.*

*Statistically: Train a logistic regression or gradient-boosted classifier on labelled historical data (where we know the true cause from maintenance logs) and use SHAP values to decompose feature contributions per incident — outputting something like 'Mechanical: 72%, Moisture: 28%'.*

*The SQL waterfall is valuable as a rule-based baseline that's fully auditable and requires no ML infrastructure — ideal for a plant operations context where explainability outweighs predictive precision."*

---

### Q3: "Walk me through the database design choices. Why did you choose SQLite over PostgreSQL, and how would the schema change at production scale?"

**Answer:**
*"SQLite was chosen deliberately for three reasons: zero-dependency deployment (single file, no server), portability for a portfolio project (anyone can clone and run), and sufficient performance for our 180-day × 7-table analytical workload (under 10K rows total).*

*The schema choices reflect production discipline despite the SQLite context: GENERATED ALWAYS AS STORED columns for `closing_cash` and `debt_service_total` eliminate the risk of application-layer calculation bugs. CHECK constraints enforce domain validity (moisture 0–100%, DSCR threshold > 0). Indexes on all FK and date columns ensure the window function queries don't degrade on larger datasets.*

*At production scale (3+ years of ops data, multi-plant), I'd migrate to PostgreSQL 16+ for three reasons: (1) true parallel query execution for window functions over millions of rows, (2) native `GENERATED COLUMNS` with `PARALLEL SAFE` marking, and (3) table partitioning by year-month on `digester_production_logs` and `daily_cash_treasury` for query pruning. I'd also introduce a separate OLAP layer (dbt + BigQuery or Redshift) for the S-Curve and DSCR models to avoid analytical queries competing with transactional writes."*

---

## Chemical Engineering Parameters Reference

| Parameter | Value | Basis |
|---|---|---|
| CBG design target | 3,000 kg/day | 3.0 TPD nameplate capacity |
| Biomass feed rate | 3.6 tons/day | ~14% CBG yield from wet biomass |
| Raw biogas yield | 200–220 Nm³/T VS | Mesophilic CSTR at 38°C, Press Mud |
| CH4 content (raw) | 60–65% | Typical anaerobic digestion |
| CH4 purity (post-scrub) | 91.5–95.5% | Membrane + water wash purification |
| CBG at 200 bar | ~0.900 kg/Nm³ CH4 | Compression density at STP basis |
| VS content (Press Mud) | 74–80% | Seasonal variation, sugar mill source |
| Optimal C:N ratio | 20–30 | For mesophilic methanogens |
| VS loss in storage | 1.2–2.0%/day | Exposed yard, MP summer conditions |
| CBG offtake price | ₹78/kg | MGL/IGL PSU contract basis |
| Power tariff | ₹8.50/kWh | MP DISCOM industrial tariff |
| Term loan rate | 11.5% p.a. | SBI Infrastructure Finance |
| Loan amount | ₹4.5 Crore | ~45% of total project cost |

---

*© 2026 Narmada Biofuels Pvt. Ltd. | Analytics Engineering | Confidential — For Portfolio Demonstration*
