-- =============================================================================
-- CBG Plant Operations & Capital Planning Dashboard Tool
-- FILE: analytics_queries.sql
-- PURPOSE: Production-grade SQL analytics engine.
--          4 modular query blocks:
--            Q1. CAPEX S-Curve & Burn Rate Variance
--            Q2. Solvency & DSCR Stress-Testing Engine
--            Q3. Feedstock Dry-Cost & Quality Ranking
--            Q4. Automated Operational RCA Engine
-- DATABASE: SQLite3 (ANSI SQL compliant; minor adaptations noted)
-- =============================================================================


-- =============================================================================
-- Q1: CAPEX S-CURVE & BURN RATE VARIANCE ANALYSIS
-- =============================================================================
-- Purpose: Compute cumulative planned vs. actual spend over the construction
--          timeline. Identifies cost overruns by category and flags overdue items.
-- Window Functions: SUM() OVER (ORDER BY target_date ROWS UNBOUNDED PRECEDING)
-- CASE Logic: Overrun severity bucketing and overdue milestone flagging
-- =============================================================================

WITH capex_enriched AS (
    -- Step 1: Enrich milestones with variance metrics
    SELECT
        milestone_id,
        category,
        milestone_name,
        vendor_name,
        target_date,
        actual_date,
        budgeted_amount,
        COALESCE(actual_spend, budgeted_amount)          AS actual_spend_safe,
        completion_pct,

        -- Variance in absolute INR
        COALESCE(actual_spend, budgeted_amount)
            - budgeted_amount                            AS variance_inr,

        -- Variance as percentage of budget
        ROUND(
            (COALESCE(actual_spend, budgeted_amount) - budgeted_amount)
            / budgeted_amount * 100.0,
        2)                                               AS variance_pct,

        -- Overrun severity classification
        CASE
            WHEN COALESCE(actual_spend, budgeted_amount) <= budgeted_amount
                THEN 'Under Budget ✓'
            WHEN (COALESCE(actual_spend, budgeted_amount) - budgeted_amount)
                 / budgeted_amount <= 0.05
                THEN 'Minor Overrun (0-5%)'
            WHEN (COALESCE(actual_spend, budgeted_amount) - budgeted_amount)
                 / budgeted_amount <= 0.10
                THEN 'Moderate Overrun (5-10%)'
            WHEN (COALESCE(actual_spend, budgeted_amount) - budgeted_amount)
                 / budgeted_amount <= 0.15
                THEN 'High Overrun (10-15%)'
            ELSE 'Critical Overrun (>15%)'
        END                                              AS overrun_severity,

        -- Delay in days (negative = ahead of schedule)
        CASE
            WHEN actual_date IS NOT NULL
            THEN CAST(julianday(actual_date) - julianday(target_date) AS INTEGER)
            ELSE NULL
        END                                              AS schedule_delay_days,

        -- Overdue flag for incomplete milestones
        CASE
            WHEN actual_date IS NULL AND date('now') > date(target_date)
                THEN 'OVERDUE'
            WHEN actual_date IS NULL
                THEN 'In-Progress'
            ELSE 'Completed'
        END                                              AS milestone_status

    FROM capex_milestones
),

capex_cumulative AS (
    -- Step 2: Running totals using window functions (S-Curve data)
    SELECT
        ce.*,

        -- Cumulative planned spend (ordered by target date)
        SUM(ce.budgeted_amount) OVER (
            ORDER BY ce.target_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )                                                AS cumulative_budget,

        -- Cumulative actual spend
        SUM(ce.actual_spend_safe) OVER (
            ORDER BY ce.target_date
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        )                                                AS cumulative_actual,

        -- Row number for milestone sequencing
        ROW_NUMBER() OVER (ORDER BY ce.target_date)      AS milestone_seq

    FROM capex_enriched ce
),

category_summary AS (
    -- Step 3: Category-level rollup for waterfall analysis
    SELECT
        category,
        COUNT(*)                                         AS milestone_count,
        SUM(budgeted_amount)                             AS total_budget,
        SUM(actual_spend_safe)                           AS total_actual,
        SUM(actual_spend_safe) - SUM(budgeted_amount)   AS total_variance,
        ROUND(
            (SUM(actual_spend_safe) - SUM(budgeted_amount))
            / SUM(budgeted_amount) * 100.0,
        2)                                               AS category_variance_pct,
        SUM(CASE WHEN milestone_status = 'OVERDUE' THEN 1 ELSE 0 END)
                                                         AS overdue_count,
        MAX(schedule_delay_days)                         AS max_delay_days
    FROM capex_enriched
    GROUP BY category
)

-- Final Output: S-Curve data with category context
SELECT
    cc.milestone_seq,
    cc.category,
    cc.milestone_name,
    cc.vendor_name,
    cc.target_date,
    cc.actual_date,
    ROUND(cc.budgeted_amount / 100000.0, 2)             AS budget_lakhs,
    ROUND(cc.actual_spend_safe / 100000.0, 2)           AS actual_lakhs,
    ROUND(cc.variance_inr / 100000.0, 2)                AS variance_lakhs,
    cc.variance_pct,
    cc.overrun_severity,
    cc.schedule_delay_days,
    cc.milestone_status,
    ROUND(cc.cumulative_budget / 100000.0, 2)           AS cumulative_budget_lakhs,
    ROUND(cc.cumulative_actual / 100000.0, 2)           AS cumulative_actual_lakhs,
    ROUND(cc.completion_pct, 1)                         AS completion_pct,
    cs.category_variance_pct                            AS category_total_variance_pct
FROM capex_cumulative cc
JOIN category_summary cs ON cs.category = cc.category
ORDER BY cc.milestone_seq;


-- =============================================================================
-- Q2: SOLVENCY & DSCR STRESS-TESTING ENGINE
-- =============================================================================
-- Purpose: Compute monthly EBITDA, join with debt schedule, and classify
--          each period by DSCR covenant health.
-- Window Functions: SUM() OVER (PARTITION BY month) for monthly aggregation
-- CASE Logic: Covenant breach triage (Healthy / Tight / Breach)
-- =============================================================================

WITH monthly_operations AS (
    -- Step 1: Aggregate daily treasury flows to monthly EBITDA proxy
    SELECT
        strftime('%Y-%m', t.entry_date)                 AS year_month,
        DATE(strftime('%Y-%m', t.entry_date) || '-01')  AS month_start,
        COUNT(*)                                         AS operating_days,

        -- Revenue (operational inflow proxy for EBITDA — pre-debt)
        SUM(t.operational_inflow)                       AS monthly_revenue,

        -- Total cash OPEX (feedstock + power + misc)
        SUM(t.feedstock_outflow + t.power_outflow + t.misc_opex)
                                                         AS monthly_opex,

        -- EBITDA approximation (excludes depreciation — cash-basis)
        SUM(t.operational_inflow)
            - SUM(t.feedstock_outflow + t.power_outflow + t.misc_opex)
                                                         AS monthly_ebitda,

        -- Closing cash at month end (last day of month)
        MAX(CASE
            WHEN t.entry_date = (
                SELECT MAX(t2.entry_date)
                FROM daily_cash_treasury t2
                WHERE strftime('%Y-%m', t2.entry_date) = strftime('%Y-%m', t.entry_date)
            ) THEN (t.opening_cash + t.operational_inflow
                    - t.feedstock_outflow - t.power_outflow
                    - t.misc_opex - t.debt_servicing)
            ELSE NULL
        END)                                             AS month_end_cash,

        -- Average receivables stretch for the month
        AVG(t.receivables_stretch_days)                  AS avg_collection_days

    FROM daily_cash_treasury t
    GROUP BY strftime('%Y-%m', t.entry_date)
),

monthly_debt AS (
    -- Step 2: Monthly debt service obligations
    SELECT
        strftime('%Y-%m', ds.repayment_date)            AS year_month,
        SUM(ds.principal_due)                            AS monthly_principal,
        SUM(ds.interest_due)                             AS monthly_interest,
        SUM(ds.debt_service_total)                       AS monthly_debt_service,
        MAX(ds.covenant_dscr_threshold)                  AS dscr_threshold
    FROM debt_schedule ds
    GROUP BY strftime('%Y-%m', ds.repayment_date)
),

dscr_computation AS (
    -- Step 3: Compute DSCR and flag covenant status
    SELECT
        mo.year_month,
        mo.month_start,
        mo.operating_days,
        ROUND(mo.monthly_revenue / 100000.0, 2)         AS revenue_lakhs,
        ROUND(mo.monthly_opex / 100000.0, 2)            AS opex_lakhs,
        ROUND(mo.monthly_ebitda / 100000.0, 2)          AS ebitda_lakhs,
        ROUND(mo.month_end_cash / 100000.0, 2)          AS closing_cash_lakhs,
        ROUND(mo.avg_collection_days, 1)                 AS avg_collection_days,
        ROUND(md.monthly_principal / 100000.0, 2)       AS principal_lakhs,
        ROUND(md.monthly_interest / 100000.0, 2)        AS interest_lakhs,
        ROUND(md.monthly_debt_service / 100000.0, 2)    AS debt_service_lakhs,
        md.dscr_threshold,

        -- Core DSCR calculation: EBITDA / Debt Service
        CASE
            WHEN md.monthly_debt_service > 0
            THEN ROUND(mo.monthly_ebitda / md.monthly_debt_service, 4)
            ELSE NULL
        END                                              AS dscr,

        -- Covenant health classification
        CASE
            WHEN md.monthly_debt_service IS NULL OR md.monthly_debt_service = 0
                THEN 'N/A — No Debt Service'
            WHEN (mo.monthly_ebitda / md.monthly_debt_service) >= 1.35
                THEN 'Healthy (≥1.35x) ✓'
            WHEN (mo.monthly_ebitda / md.monthly_debt_service) >= 1.25
                THEN 'Tight Buffer (1.25x–1.35x) ⚠'
            WHEN (mo.monthly_ebitda / md.monthly_debt_service) >= 1.00
                THEN 'Covenant Breach (<1.25x) 🔴'
            ELSE 'Critical — DSCR <1.0x ⛔'
        END                                              AS dscr_status,

        -- Cash runway: months of OPEX coverage from closing cash
        CASE
            WHEN mo.monthly_opex > 0 AND mo.month_end_cash > 0
            THEN ROUND(mo.month_end_cash / (mo.monthly_opex / mo.operating_days) / 30.0, 1)
            ELSE 0
        END                                              AS cash_runway_months

    FROM monthly_operations mo
    LEFT JOIN monthly_debt md ON md.year_month = mo.year_month
)

-- Final Output: DSCR trendline data
SELECT
    dc.*,

    -- 3-month rolling DSCR for smoothing
    ROUND(
        AVG(dc.dscr) OVER (
            ORDER BY dc.year_month
            ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
        ),
    4)                                                   AS dscr_3m_rolling,

    -- Cumulative EBITDA for trend analysis
    ROUND(
        SUM(dc.ebitda_lakhs) OVER (
            ORDER BY dc.year_month
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ),
    2)                                                   AS cumulative_ebitda_lakhs

FROM dscr_computation dc
ORDER BY dc.year_month;


-- =============================================================================
-- Q3: FEEDSTOCK DRY-COST ANALYSIS & SUPPLIER QUALITY RANKING
-- =============================================================================
-- Purpose: Compute true landed cost per dry ton by adjusting for moisture loss.
--          Rank suppliers within each feedstock category using DENSE_RANK().
-- Window Functions: DENSE_RANK() OVER (PARTITION BY feedstock_type ORDER BY cost)
--                   AVG() OVER (PARTITION BY supplier for trend)
-- =============================================================================

WITH feedstock_enriched AS (
    -- Step 1: Compute dry weight and landed cost per dry ton
    SELECT
        f.receipt_id,
        f.delivery_date,
        s.supplier_name,
        s.feedstock_type,
        s.distance_km,
        f.gross_weight_tons,
        f.moisture_pct,

        -- Dry weight adjustment (industry standard: dry basis costing)
        ROUND(
            f.gross_weight_tons * (1.0 - f.moisture_pct / 100.0),
        3)                                               AS dry_weight_tons,

        f.total_landed_cost,
        f.cn_ratio,
        f.quality_grade,

        -- True landed cost on dry-weight basis
        CASE
            WHEN f.gross_weight_tons * (1.0 - f.moisture_pct / 100.0) > 0
            THEN ROUND(
                f.total_landed_cost
                / (f.gross_weight_tons * (1.0 - f.moisture_pct / 100.0)),
            2)
            ELSE NULL
        END                                              AS landed_cost_per_dry_ton,

        -- Freight component as % of total landed cost
        ROUND(
            (s.distance_km * s.freight_rate_per_km_ton * f.gross_weight_tons)
            / f.total_landed_cost * 100.0,
        1)                                               AS freight_pct_of_cost

    FROM feedstock_inward_logs f
    JOIN suppliers s ON s.supplier_id = f.supplier_id
),

supplier_monthly_avg AS (
    -- Step 2: Monthly average cost per supplier (rolling quality trend)
    SELECT
        supplier_name,
        feedstock_type,
        strftime('%Y-%m', delivery_date)                AS year_month,
        ROUND(AVG(moisture_pct), 2)                      AS avg_moisture_pct,
        ROUND(AVG(landed_cost_per_dry_ton), 2)           AS avg_dry_cost,
        ROUND(AVG(cn_ratio), 2)                          AS avg_cn_ratio,
        COUNT(*)                                          AS delivery_count,
        SUM(gross_weight_tons)                           AS total_gross_tons,
        SUM(dry_weight_tons)                             AS total_dry_tons
    FROM feedstock_enriched
    GROUP BY supplier_name, feedstock_type, strftime('%Y-%m', delivery_date)
),

supplier_overall AS (
    -- Step 3: Overall supplier performance metrics
    SELECT
        supplier_name,
        feedstock_type,
        COUNT(*)                                          AS total_deliveries,
        ROUND(AVG(moisture_pct), 2)                      AS overall_avg_moisture,
        ROUND(AVG(landed_cost_per_dry_ton), 2)           AS overall_avg_dry_cost,
        ROUND(MIN(landed_cost_per_dry_ton), 2)           AS best_dry_cost,
        ROUND(MAX(landed_cost_per_dry_ton), 2)           AS worst_dry_cost,
        ROUND(AVG(cn_ratio), 2)                          AS avg_cn_ratio,
        ROUND(AVG(freight_pct_of_cost), 1)               AS avg_freight_pct,
        SUM(gross_weight_tons)                           AS total_gross_tons_supplied,

        -- Cost-adjusted yield score (lower moisture → higher effective value)
        ROUND(
            AVG(landed_cost_per_dry_ton) * (1 + AVG(moisture_pct) / 100.0),
        2)                                               AS adjusted_cost_score

    FROM feedstock_enriched
    GROUP BY supplier_name, feedstock_type
),

ranked_suppliers AS (
    -- Step 4: Rank suppliers within feedstock category using DENSE_RANK
    SELECT
        so.*,

        -- Within-category cost ranking (1 = most cost-efficient)
        DENSE_RANK() OVER (
            PARTITION BY so.feedstock_type
            ORDER BY so.overall_avg_dry_cost ASC
        )                                                AS cost_rank,

        -- Quality ranking (1 = best quality, lowest moisture)
        DENSE_RANK() OVER (
            PARTITION BY so.feedstock_type
            ORDER BY so.overall_avg_moisture ASC
        )                                                AS quality_rank,

        -- Composite rank (lower = better overall)
        DENSE_RANK() OVER (
            PARTITION BY so.feedstock_type
            ORDER BY so.adjusted_cost_score ASC
        )                                                AS composite_rank

    FROM supplier_overall so
)

-- Final Output: Supplier ranking table
SELECT
    rs.supplier_name,
    rs.feedstock_type,
    rs.total_deliveries,
    rs.total_gross_tons_supplied,
    rs.overall_avg_moisture              AS avg_moisture_pct,
    rs.overall_avg_dry_cost              AS avg_landed_cost_per_dry_ton_inr,
    rs.best_dry_cost                     AS best_landed_cost_inr,
    rs.worst_dry_cost                    AS worst_landed_cost_inr,
    rs.avg_cn_ratio,
    rs.avg_freight_pct,
    rs.cost_rank,
    rs.quality_rank,
    rs.composite_rank,

    -- Vendor assessment badge
    CASE
        WHEN rs.composite_rank = 1 THEN 'Premium Partner ⭐'
        WHEN rs.composite_rank = 2 THEN 'Standard Supplier'
        WHEN rs.overall_avg_moisture > 65 THEN 'Quality Risk — Review Contract 🔴'
        ELSE 'Monitor'
    END                                                  AS vendor_assessment

FROM ranked_suppliers rs
ORDER BY rs.feedstock_type, rs.composite_rank;


-- =============================================================================
-- Q4: AUTOMATED OPERATIONAL RCA ENGINE
-- =============================================================================
-- Purpose: Identify every under-performance day (CBG < 85% of 3 TPD target)
--          and assign a primary root cause using a waterfall priority CASE logic.
--          Quantifies financial loss and recommends corrective action.
-- Technique: Multi-CTE with lateral-style enrichment + prioritized CASE
-- =============================================================================

WITH underperformance_days AS (
    -- Step 1: Flag days where CBG production < 2,550 kg (85% of 3,000 kg target)
    SELECT
        d.production_id,
        d.production_date,
        d.tons_biomass_fed,
        d.biogas_yield_nm3,
        d.ch4_purity_pct,
        d.cbg_produced_kg,
        d.plant_downtime_hrs,
        d.offtake_revenue,
        3000.0 - d.cbg_produced_kg                      AS cbg_shortfall_kg,
        ROUND((d.cbg_produced_kg / 3000.0) * 100.0, 2) AS capacity_utilization_pct
    FROM digester_production_logs d
    WHERE d.cbg_produced_kg < 2550.0
),

enriched_with_feedstock AS (
    -- Step 2: Join with best-available feedstock quality for that production date
    --         Using date-range join to get same-day or prior-day feedstock
    SELECT
        ud.*,

        -- Feedstock quality from same-day inward logs (aggregated)
        COALESCE(f_agg.avg_moisture_pct, 60.0)           AS feedstock_moisture_pct,
        COALESCE(f_agg.avg_cn_ratio, 25.0)               AS feedstock_cn_ratio

    FROM underperformance_days ud
    LEFT JOIN (
        SELECT
            delivery_date,
            AVG(moisture_pct)                            AS avg_moisture_pct,
            AVG(cn_ratio)                                AS avg_cn_ratio
        FROM feedstock_inward_logs
        GROUP BY delivery_date
    ) f_agg ON f_agg.delivery_date = ud.production_date
),

enriched_with_yard AS (
    -- Step 3: Join yard aging data for the same date
    SELECT
        ewf.*,
        COALESCE(y_agg.avg_vs_loss, 5.0)                AS avg_volatile_solids_loss_pct

    FROM enriched_with_feedstock ewf
    LEFT JOIN (
        SELECT
            entry_date,
            AVG(volatile_solids_loss_pct)               AS avg_vs_loss
        FROM yard_inventory_aging
        GROUP BY entry_date
    ) y_agg ON y_agg.entry_date = ewf.production_date
),

rca_classified AS (
    -- Step 4: Primary Root Cause Assignment — PRIORITY WATERFALL
    -- Priority order: Mechanical > Chemistry > Storage > Moisture > Volume
    SELECT
        ewy.*,

        -- PRIMARY ROOT CAUSE (mutually exclusive, priority-ordered)
        CASE
            WHEN ewy.plant_downtime_hrs > 6.0
                THEN 'Mechanical Downtime / Equipment Failure'
            WHEN ewy.ch4_purity_pct < 90.0
                THEN 'Process Chemistry / Gas Purification Lag'
            WHEN ewy.avg_volatile_solids_loss_pct > 15.0
                THEN 'Raw Material Storage Degradation'
            WHEN ewy.feedstock_moisture_pct > 65.0
                THEN 'Feedstock Moisture Dilution'
            ELSE
                'Input Feedstock Volume Deficit'
        END                                              AS primary_rca,

        -- SECONDARY ROOT CAUSE (contributing factors)
        CASE
            WHEN ewy.plant_downtime_hrs > 6.0
                 AND ewy.feedstock_moisture_pct > 65.0
                THEN 'Compounded: Moisture + Mechanical'
            WHEN ewy.ch4_purity_pct < 90.0
                 AND ewy.avg_volatile_solids_loss_pct > 12.0
                THEN 'Compounded: Storage Degradation reducing CH4%'
            WHEN ewy.feedstock_moisture_pct > 65.0
                 AND ewy.cbg_produced_kg < 1800
                THEN 'Severe Moisture Dilution (>70%)'
            ELSE 'Single-Factor Cause'
        END                                              AS secondary_rca,

        -- Financial loss quantification (INR)
        ROUND(
            (3000.0 - ewy.cbg_produced_kg) * 78.0,     -- Lost revenue at INR 78/kg
        2)                                               AS revenue_loss_inr,

        -- Corrective action recommendation
        CASE
            WHEN ewy.plant_downtime_hrs > 6.0
                THEN 'Immediate Action: Activate maintenance SOP-M07. '
                     || 'Check compressor shaft seals and inter-stage valves. '
                     || 'Notify OEM (Bauer) for expedited spare parts. '
                     || 'Escalate to Plant Head if downtime > 12 hrs.'
            WHEN ewy.ch4_purity_pct < 90.0
                THEN 'Process Action: Inspect CO2 membrane module pressure differential. '
                     || 'Check H2S scrubber caustic concentration (target: 4% NaOH). '
                     || 'Verify water wash tower flow rate. Increase scrubbing cycles.'
            WHEN ewy.avg_volatile_solids_loss_pct > 15.0
                THEN 'Storage Action: Reduce yard retention time to <3 days. '
                     || 'Cover exposed material in Bay-B2. '
                     || 'Prioritise FIFO lot feeding sequence. '
                     || 'Negotiate shorter lead times with Supplier-A.'
            WHEN ewy.feedstock_moisture_pct > 65.0
                THEN 'Procurement Action: Trigger moisture rejection clause (Contract §4.2). '
                     || 'Reduce Supplier-B allocation by 40%. '
                     || 'Source emergency dry-press-mud from Supplier-C. '
                     || 'Issue quality deduction note to Supplier-B.'
            ELSE 'Logistics Action: Review feedstock procurement schedule. '
                 || 'Confirm next 3-day delivery calendar with all suppliers. '
                 || 'Check if agri-season gap is causing volume shortfall. '
                 || 'Evaluate Crop Residue as bridge feedstock.'
        END                                              AS corrective_action,

        -- Severity level
        CASE
            WHEN ewy.plant_downtime_hrs > 15 THEN 'CRITICAL'
            WHEN ewy.cbg_produced_kg < 1800   THEN 'HIGH'
            WHEN ewy.capacity_utilization_pct < 75 THEN 'MEDIUM'
            ELSE 'LOW'
        END                                              AS severity_level

    FROM enriched_with_yard ewy
),

rca_summary AS (
    -- Step 5: Aggregate RCA distribution for reporting
    SELECT
        primary_rca,
        COUNT(*)                                          AS incident_days,
        ROUND(AVG(cbg_shortfall_kg), 1)                  AS avg_shortfall_kg,
        ROUND(SUM(revenue_loss_inr) / 100000.0, 2)       AS total_loss_lakhs,
        ROUND(AVG(plant_downtime_hrs), 2)                 AS avg_downtime_hrs,
        ROUND(AVG(feedstock_moisture_pct), 2)             AS avg_moisture_pct,
        COUNT(CASE WHEN severity_level = 'CRITICAL' THEN 1 END)
                                                          AS critical_incidents,
        COUNT(CASE WHEN severity_level = 'HIGH' THEN 1 END)
                                                          AS high_incidents
    FROM rca_classified
    GROUP BY primary_rca
    ORDER BY total_loss_lakhs DESC
)

-- Final Output A: Detailed RCA drill-down ledger
SELECT
    rc.production_date,
    rc.cbg_produced_kg,
    ROUND(rc.capacity_utilization_pct, 1)               AS cuf_pct,
    rc.cbg_shortfall_kg,
    rc.plant_downtime_hrs,
    ROUND(rc.ch4_purity_pct, 2)                         AS ch4_purity_pct,
    ROUND(rc.feedstock_moisture_pct, 2)                  AS feedstock_moisture_pct,
    ROUND(rc.avg_volatile_solids_loss_pct, 2)            AS vs_loss_pct,
    rc.primary_rca,
    rc.secondary_rca,
    rc.severity_level,
    rc.revenue_loss_inr,
    rc.corrective_action
FROM rca_classified rc
ORDER BY rc.revenue_loss_inr DESC;

-- Final Output B: RCA Summary Distribution (for pie chart)
-- (Uncomment to run separately)
-- SELECT * FROM rca_summary;


-- =============================================================================
-- BONUS Q5: ROLLING 30-DAY CASH POSITION WITH LIQUIDITY STRESS INDICATOR
-- =============================================================================
-- Window Function: AVG() OVER (ROWS BETWEEN 29 PRECEDING AND CURRENT ROW)
-- Purpose: Detect periods where rolling cash falls below debt service reserve (INR 5L)
-- =============================================================================

WITH cash_with_rolling AS (
    SELECT
        t.entry_date,
        t.opening_cash,
        t.operational_inflow,
        t.feedstock_outflow + t.power_outflow + t.misc_opex   AS total_opex,
        t.debt_servicing,
        (t.opening_cash + t.operational_inflow
         - t.feedstock_outflow - t.power_outflow
         - t.misc_opex - t.debt_servicing)                    AS closing_cash,
        t.receivables_stretch_days,

        -- 30-day rolling average closing cash
        AVG(
            t.opening_cash + t.operational_inflow
            - t.feedstock_outflow - t.power_outflow
            - t.misc_opex - t.debt_servicing
        ) OVER (
            ORDER BY t.entry_date
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        )                                                       AS rolling_30d_avg_cash,

        -- Minimum cash in rolling 30-day window
        MIN(
            t.opening_cash + t.operational_inflow
            - t.feedstock_outflow - t.power_outflow
            - t.misc_opex - t.debt_servicing
        ) OVER (
            ORDER BY t.entry_date
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        )                                                       AS rolling_30d_min_cash,

        -- Cash burn rate (daily average OPEX in rolling window)
        AVG(t.feedstock_outflow + t.power_outflow + t.misc_opex) OVER (
            ORDER BY t.entry_date
            ROWS BETWEEN 29 PRECEDING AND CURRENT ROW
        )                                                       AS rolling_30d_burn_rate

    FROM daily_cash_treasury t
)

SELECT
    cwr.entry_date,
    ROUND(cwr.closing_cash / 100000.0, 2)              AS closing_cash_lakhs,
    ROUND(cwr.rolling_30d_avg_cash / 100000.0, 2)      AS rolling_30d_avg_lakhs,
    ROUND(cwr.rolling_30d_min_cash / 100000.0, 2)      AS rolling_30d_min_lakhs,
    ROUND(cwr.rolling_30d_burn_rate, 2)                 AS daily_burn_rate_inr,
    cwr.receivables_stretch_days,

    -- Liquidity stress flag
    CASE
        WHEN cwr.rolling_30d_min_cash < 500000   -- Below INR 5 Lakhs minimum reserve
            THEN 'LIQUIDITY STRESS — Reserve Breach 🔴'
        WHEN cwr.rolling_30d_avg_cash < 1000000  -- Below INR 10 Lakhs comfort level
            THEN 'Tight Liquidity ⚠'
        ELSE 'Adequate Liquidity ✓'
    END                                                  AS liquidity_status,

    -- Days of runway at current burn rate
    CASE
        WHEN cwr.rolling_30d_burn_rate > 0
        THEN ROUND(
            GREATEST(cwr.closing_cash, 0) / cwr.rolling_30d_burn_rate,
        1)
        ELSE NULL
    END                                                  AS runway_days_at_burn_rate

FROM cash_with_rolling cwr
ORDER BY cwr.entry_date;

-- =============================================================================
-- END OF ANALYTICS QUERIES
-- =============================================================================
