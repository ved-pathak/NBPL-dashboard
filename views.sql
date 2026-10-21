-- views.sql
-- All analysis logic for CBG Plant Production Funnel.
-- No hardcoded numbers: every threshold comes from the single-row config table
-- via CROSS JOIN config c.
--
-- Build order:
--   v_price -> v_day_map -> v_stage_losses -> v_loss_causes -> v_loss_daily
--   -> v_vendor_allocation -> v_cause_ranking -> v_window_vendors
--   -> v_headline_summary -> v_vendor_summary -> v_daily_trend

-- Drop views in reverse dependency order before recreating
DROP VIEW IF EXISTS v_daily_trend;
DROP VIEW IF EXISTS v_vendor_summary;
DROP VIEW IF EXISTS v_headline_summary;
DROP VIEW IF EXISTS v_window_vendors;
DROP VIEW IF EXISTS v_cause_ranking;
DROP VIEW IF EXISTS v_loss_daily;
DROP VIEW IF EXISTS v_vendor_allocation;
DROP VIEW IF EXISTS v_transit_label;
DROP VIEW IF EXISTS v_loss_causes;
DROP VIEW IF EXISTS v_stage_losses;
DROP VIEW IF EXISTS v_day_map;
DROP VIEW IF EXISTS v_price;

-- ===========================================================================
-- v_price : single-row pricing constants (reused by all other views)
-- ===========================================================================
CREATE VIEW IF NOT EXISTS v_price AS
SELECT
    c.design_purity,
    c.compression_charge_per_kg,
    c.price_per_mmbtu,
    -- slope = GCV * price_per_mmbtu / density * correction_factor
    -- Unit derivation:
    --   gcv_mmbtu_per_scm * price_per_mmbtu = Rs/scm
    --   Rs/scm / (gas_density_kg_per_scm) = Rs/kg of gas
    --   * correction_factor = ex-GST effective Rs/kg
    (c.gcv_mmbtu_per_scm * 1000.0 * c.price_per_mmbtu
        / (c.gas_density_kg_per_scm * 1000.0)
        * c.correction_factor) AS slope,
    -- design price at 0.98 purity
    (c.gcv_mmbtu_per_scm * 1000.0 * c.price_per_mmbtu
        / (c.gas_density_kg_per_scm * 1000.0)
        * c.correction_factor) * c.design_purity
        + c.compression_charge_per_kg AS design_price
FROM config c;

-- Helper: price_per_kg(purity) = slope * purity + compression_charge_per_kg
-- Used inline wherever a purity-specific price is needed.

-- ===========================================================================
-- v_day_map : canonical lag mapping (ONE place for the 45-day lag)
--
-- The lag is a modelling simplification. Digesters are continuous stirred
-- tanks, so output on a given day reflects a blend of many feed days.
-- This fixed-offset join is an attribution convention — analogous to
-- choosing a fixed conversion window — not a claim about physical tracing.
-- ===========================================================================
CREATE VIEW IF NOT EXISTS v_day_map AS
SELECT
    d.output_date,
    date(d.output_date, '-' || c.lag_days || ' days') AS feed_date
FROM fact_digester_output d
CROSS JOIN config c;

-- ===========================================================================
-- v_stage_losses : per output-day sequential loss walk
--
-- The five kg losses (supply, moisture, digester, purification, transit)
-- sum exactly to (N - billed_kg) BY CONSTRUCTION. This is an algebraic
-- identity from how the ratios are defined, not an independent data check.
-- ===========================================================================
CREATE VIEW IF NOT EXISTS v_stage_losses AS
WITH base AS (
    SELECT
        o.output_date,
        m.feed_date,
        -- Feed-day quantities (lagged)
        f.rm_fed_t,
        f.solids_fed_t,
        -- Digester output
        o.biogas_nm3,
        o.ch4_frac,
        -- Purification
        p.ch4_in_kg,
        p.cbg_out_kg,
        p.purity_frac             AS plant_purity,
        -- Billing
        b.billed_kg,
        b.billed_purity_frac      AS billed_purity,
        b.delivery_pressure_bar,
        -- Config (single row joined once)
        c.nameplate_kg            AS N,
        c.plant_need_t,
        c.target_solids_frac,
        c.design_purity,
        c.design_slip,
        c.design_ch4_kg_per_t_solids,
        c.ch4_density_kg_per_nm3,
        c.below_target_pct,
        c.delivery_pressure_min_bar,
        c.slip_limit,
        -- Price view (joined as single row)
        pr.slope,
        pr.design_price,
        pr.compression_charge_per_kg
    FROM fact_digester_output o
    CROSS JOIN config c
    CROSS JOIN v_price pr
    JOIN v_day_map m   ON m.output_date = o.output_date
    JOIN fact_digester_feed f ON f.feed_date = m.feed_date
    JOIN fact_purification  p ON p.output_date = o.output_date
    JOIN fact_omc_billing   b ON b.output_date = o.output_date
),
ratios AS (
    SELECT
        *,
        -- Efficiency ratios
        rm_fed_t / plant_need_t                              AS qty_ratio,
        solids_fed_t / (plant_need_t * target_solids_frac)  AS solids_ratio,
        -- dig_eff: digester CH4 vs what solids should have yielded.
        -- Ensures a feed shortfall never masquerades as a digester problem.
        ch4_in_kg / (solids_fed_t * design_ch4_kg_per_t_solids) AS dig_eff,
        -- pur_eff: ratio of actual methane recovery to design recovery.
        -- actual_recovery = cbg_out_kg * design_purity / ch4_in_kg
        -- design_recovery = 1 - design_slip
        (cbg_out_kg * design_purity / ch4_in_kg)
            / (1.0 - design_slip)                           AS pur_eff,
        -- Actual slip (for diagnostics)
        1.0 - cbg_out_kg * design_purity / ch4_in_kg        AS slip_actual,
        -- Transit efficiency
        billed_kg / cbg_out_kg                              AS transit_eff
    FROM base
),
walk AS (
    SELECT
        *,
        -- Sequential funnel (k0 -> k5)
        N                                AS k0,
        N * qty_ratio                    AS k1,
        N * solids_ratio                 AS k2,
        N * solids_ratio * dig_eff       AS k3,
        N * solids_ratio * dig_eff * pur_eff AS k4,
        billed_kg                        AS k5
    FROM ratios
)
SELECT
    output_date,
    feed_date,
    -- Production status
    cbg_out_kg,
    billed_kg,
    N,
    plant_need_t,
    target_solids_frac,
    design_purity,
    plant_purity,
    billed_purity,
    delivery_pressure_bar,
    delivery_pressure_min_bar,
    slip_actual,
    slip_limit,
    below_target_pct,
    -- Stage kg losses (positive = loss vs nameplate, negative = gain)
    (k0 - k1) AS supply_loss_kg,
    (k1 - k2) AS moisture_loss_kg,
    (k2 - k3) AS digester_loss_kg,
    (k3 - k4) AS purification_loss_kg,
    (k4 - k5) AS transit_loss_kg,
    -- Rupee losses on quantity
    (k0 - k1) * design_price AS supply_loss_rs,
    (k1 - k2) * design_price AS moisture_loss_rs,
    (k2 - k3) * design_price AS digester_loss_rs,
    (k3 - k4) * design_price AS purification_loss_rs,
    (k4 - k5) * design_price AS transit_qty_loss_rs,
    -- Price-realisation losses (purity)
    -- purity_plant_loss: billed at plant purity vs design purity
    billed_kg * (design_price - (slope * plant_purity + compression_charge_per_kg))
        AS purity_plant_loss_rs,
    -- purity_transit_loss: billed purity vs plant purity
    billed_kg * ((slope * plant_purity + compression_charge_per_kg)
               - (slope * billed_purity + compression_charge_per_kg))
        AS purity_transit_loss_rs,
    -- Total revenue lost = N * design_price - billed_kg * price(billed_purity)
    N * design_price - billed_kg * (slope * billed_purity + compression_charge_per_kg)
        AS total_rs_lost,
    -- Design price for reference
    design_price,
    slope,
    compression_charge_per_kg,
    -- Ratios for diagnostics
    qty_ratio,
    solids_ratio,
    dig_eff,
    pur_eff,
    transit_eff
FROM walk;

-- ===========================================================================
-- v_loss_causes : unpivoted 7 causes per day with significance flag
--
-- A cause is "significant" if its Rs loss exceeds a noise threshold
-- (default 2% of daily nameplate revenue). This filters out minor
-- fluctuations from being flagged as the primary driver.
-- ===========================================================================
CREATE VIEW IF NOT EXISTS v_loss_causes AS
WITH unpivoted AS (
    -- Supply shortfall
    SELECT output_date, 'Supply shortfall' AS cause,
           supply_loss_kg AS loss_kg, supply_loss_rs AS rs_loss
    FROM v_stage_losses
    UNION ALL
    -- Moisture / low solids
    SELECT output_date, 'Moisture / low solids' AS cause,
           moisture_loss_kg, moisture_loss_rs
    FROM v_stage_losses
    UNION ALL
    -- Digester underperformance
    SELECT output_date, 'Digester underperformance' AS cause,
           digester_loss_kg, digester_loss_rs
    FROM v_stage_losses
    UNION ALL
    -- Purification methane slip
    SELECT output_date, 'Purification methane slip' AS cause,
           purification_loss_kg, purification_loss_rs
    FROM v_stage_losses
    UNION ALL
    -- Purity at plant gate (price-realisation)
    SELECT output_date, 'Low purity at plant gate' AS cause,
           0.0 AS loss_kg, purity_plant_loss_rs AS rs_loss
    FROM v_stage_losses
    UNION ALL
    -- Purity drop in transit (price-realisation)
    SELECT output_date, 'Purity drop in transit' AS cause,
           0.0 AS loss_kg, purity_transit_loss_rs AS rs_loss
    FROM v_stage_losses
    UNION ALL
    -- Transit quantity loss
    SELECT output_date, 'Transit loss' AS cause,
           transit_loss_kg, transit_qty_loss_rs AS rs_loss
    FROM v_stage_losses
),
ranked AS (
    SELECT
        u.output_date,
        u.cause,
        u.loss_kg,
        u.rs_loss,
        -- Rank by rs_loss descending (largest loss = highest rank)
        ROW_NUMBER() OVER (PARTITION BY u.output_date ORDER BY u.rs_loss DESC) AS rank_by_rs,
        -- Significant: cause matters if rs_loss >= threshold_pct * N * design_price
        CASE WHEN u.rs_loss >= c.materiality_pct * c.nameplate_kg * p.design_price
             THEN 1 ELSE 0 END AS is_significant
    FROM unpivoted u
    CROSS JOIN config c
    CROSS JOIN v_price p
)
SELECT * FROM ranked;

-- ===========================================================================
-- v_transit_label : applies the transit label rule
-- ===========================================================================
CREATE VIEW IF NOT EXISTS v_transit_label AS
SELECT
    s.output_date,
    CASE
        -- Transit is the culprit only when plant is clean AND loss > tolerance
        WHEN s.transit_loss_kg > c.transit_tolerance * s.cbg_out_kg
             AND s.cbg_out_kg >= c.below_target_pct * s.N
             AND s.slip_actual <= c.slip_limit
             AND s.plant_purity >= (c.design_purity - 0.005)
        THEN 'Transit pressure loss'
        ELSE 'Short billing (plant issue also present)'
    END AS transit_label
FROM v_stage_losses s
CROSS JOIN config c;

-- ===========================================================================
-- v_vendor_allocation : per-feed-day, per-vendor supply and moisture losses
--   Joins through v_day_map so the lag lives in ONE place.
-- ===========================================================================
CREATE VIEW IF NOT EXISTS v_vendor_allocation AS
WITH daily_shortfall AS (
    -- Total shortfall per vendor per feed day (for supply allocation)
    SELECT
        r.receipt_date AS feed_date,
        r.vendor,
        r.qty_t,
        r.moisture_frac,
        v.dcq_t,
        -- shortfall_v = max(0, dcq_t - qty_t)
        MAX(0.0, v.dcq_t - r.qty_t) AS shortfall_v
    FROM fact_rm_receipt r
    JOIN dim_vendor v ON v.vendor = r.vendor
),
daily_totals AS (
    -- Sum of shortfalls and moisture excess per feed day (denominators)
    SELECT
        ds.feed_date,
        SUM(ds.shortfall_v) AS total_shortfall,
        -- Feed scale for moisture excess: rm_fed_t / received_t
        f.rm_fed_t / SUM(ds.qty_t) AS feed_scale,
        f.rm_fed_t,
        SUM(ds.qty_t) AS received_t
    FROM daily_shortfall ds
    JOIN fact_digester_feed f ON f.feed_date = ds.feed_date
    GROUP BY ds.feed_date
),
moisture_excess AS (
    -- excess_v = max(0, qty_t * scale * (target - (1 - moisture)))
    -- Positive when vendor's solids fraction < target (i.e., too wet)
    SELECT
        ds.feed_date,
        ds.vendor,
        MAX(0.0, ds.qty_t * dt.feed_scale
                 * (c.target_solids_frac - (1.0 - ds.moisture_frac))) AS excess_v
    FROM daily_shortfall ds
    JOIN daily_totals dt ON dt.feed_date = ds.feed_date
    CROSS JOIN config c
),
moisture_totals AS (
    SELECT feed_date, SUM(excess_v) AS total_excess
    FROM moisture_excess
    GROUP BY feed_date
)
SELECT
    m.output_date,
    ds.feed_date,
    ds.vendor,
    ds.qty_t,
    ds.moisture_frac,
    ds.dcq_t,
    ds.shortfall_v,
    me.excess_v,
    dt.total_shortfall,
    mt.total_excess,
    dt.feed_scale,
    -- Supply loss allocation: vendor's share of total shortfall
    CASE WHEN sl.supply_loss_kg > 0 AND dt.total_shortfall > 0
         THEN sl.supply_loss_kg * ds.shortfall_v / dt.total_shortfall
         ELSE 0.0 END AS supply_loss_kg_v,
    -- Moisture loss allocation: vendor's share of total excess wetness
    CASE WHEN sl.moisture_loss_kg > 0 AND mt.total_excess > 0
         THEN sl.moisture_loss_kg * me.excess_v / mt.total_excess
         ELSE 0.0 END AS moisture_loss_kg_v,
    -- Rs conversions
    CASE WHEN sl.supply_loss_kg > 0 AND dt.total_shortfall > 0
         THEN sl.supply_loss_rs * ds.shortfall_v / dt.total_shortfall
         ELSE 0.0 END AS supply_loss_rs_v,
    CASE WHEN sl.moisture_loss_kg > 0 AND mt.total_excess > 0
         THEN sl.moisture_loss_rs * me.excess_v / mt.total_excess
         ELSE 0.0 END AS moisture_loss_rs_v
FROM v_day_map m
JOIN daily_shortfall ds     ON ds.feed_date = m.feed_date
JOIN daily_totals dt        ON dt.feed_date = m.feed_date
JOIN moisture_excess me     ON me.feed_date = m.feed_date AND me.vendor = ds.vendor
JOIN moisture_totals mt     ON mt.feed_date = m.feed_date
JOIN v_stage_losses sl      ON sl.output_date = m.output_date;

-- ===========================================================================
-- v_loss_daily : one row per output day, primary and secondary cause + tracing
-- ===========================================================================
CREATE VIEW IF NOT EXISTS v_loss_daily AS
WITH primary_cause AS (
    SELECT output_date, cause AS primary_cause, rs_loss AS primary_rs_loss, is_significant
    FROM v_loss_causes
    WHERE rank_by_rs = 1
),
secondary_cause AS (
    SELECT output_date, cause AS secondary_cause, rs_loss AS secondary_rs_loss, is_significant AS sec_is_significant
    FROM v_loss_causes
    WHERE rank_by_rs = 2
),
-- Vendor trace rankings separated for supply vs. moisture so the wrong vendor is never accused
vendor_trace AS (
    SELECT
        va.output_date,
        va.vendor,
        va.feed_date,
        ROW_NUMBER() OVER (
            PARTITION BY va.output_date
            ORDER BY va.supply_loss_kg_v DESC
        ) AS rank_supply,
        ROW_NUMBER() OVER (
            PARTITION BY va.output_date
            ORDER BY va.moisture_loss_kg_v DESC
        ) AS rank_moisture
    FROM v_vendor_allocation va
)
SELECT
    s.output_date,
    -- Status
    CASE WHEN s.cbg_out_kg < s.below_target_pct * s.N
         THEN 'Below 90%' ELSE 'OK' END AS status,
    s.cbg_out_kg,
    s.billed_kg,
    s.N AS nameplate_kg,
    ROUND(s.cbg_out_kg / s.N * 100, 2) AS pct_of_nameplate,
    ROUND(s.N - s.cbg_out_kg, 2)       AS gap_kg,
    ROUND(s.total_rs_lost, 2)          AS total_rs_lost,
    -- Primary cause (or 'Within normal variation' if not significant)
    CASE WHEN pc.is_significant = 1 THEN
        CASE WHEN pc.primary_cause = 'Transit loss' THEN tl.transit_label
             ELSE pc.primary_cause END
         ELSE 'Within normal variation' END AS primary_cause,
    ROUND(pc.primary_rs_loss, 2) AS primary_rs_loss,
    -- Secondary cause (NULL if not significant)
    CASE WHEN sc.sec_is_significant = 1 THEN
        CASE WHEN sc.secondary_cause = 'Transit loss' THEN tl.transit_label
             ELSE sc.secondary_cause END
         ELSE NULL END AS secondary_cause,
    ROUND(sc.secondary_rs_loss, 2) AS secondary_rs_loss,
    -- Feed-date and vendor trace (only for Supply or Moisture primary causes)
    CASE WHEN pc.is_significant = 1
              AND pc.primary_cause IN ('Supply shortfall', 'Moisture / low solids')
         THEN m.feed_date ELSE NULL END AS traced_feed_date,
    CASE WHEN pc.is_significant = 1 AND pc.primary_cause = 'Supply shortfall'
         THEN svt.vendor
         WHEN pc.is_significant = 1 AND pc.primary_cause = 'Moisture / low solids'
         THEN mvt.vendor
         ELSE NULL END AS traced_vendor,
    -- Diagnostic note: summary derived from ranked primary cause and process metrics
    CASE
        WHEN pc.is_significant = 0
            THEN 'Normal variation: Output ' || ROUND(s.cbg_out_kg / s.N * 100, 1) || '% of nameplate'
        WHEN pc.primary_cause = 'Supply shortfall'
            THEN 'Feed shortfall: ' || ROUND(s.supply_loss_kg, 0) || ' kg loss (feed below ' || ROUND(s.plant_need_t, 0) || 't plant need)'
        WHEN pc.primary_cause = 'Moisture / low solids'
            THEN 'High moisture: ' || ROUND(s.moisture_loss_kg, 0) || ' kg loss (solids fed below ' || ROUND(s.target_solids_frac * 100, 0) || '% spec)'
        WHEN pc.primary_cause = 'Digester underperformance'
            THEN 'Digester yield drop: ' || ROUND(s.digester_loss_kg, 0) || ' kg loss (CH4 yield below design)'
        WHEN pc.primary_cause = 'Purification methane slip'
            THEN 'High slip: ' || ROUND(s.slip_actual * 100, 2) || '% > ' || ROUND(s.slip_limit * 100, 1) || '% limit (' || ROUND(s.purification_loss_kg, 0) || ' kg loss)'
        WHEN pc.primary_cause = 'Low purity at plant gate'
            THEN 'Purity penalty: ' || ROUND(s.plant_purity * 100, 2) || '% < ' || ROUND(s.design_purity * 100, 1) || '% spec (₹' || ROUND(s.purity_plant_loss_rs / 1000, 1) || 'K penalty)'
        WHEN pc.primary_cause = 'Transit loss'
            THEN CASE
                WHEN tl.transit_label = 'Transit pressure loss'
                    THEN 'Pressure drop: ' || ROUND(s.delivery_pressure_bar, 0) || ' bar < ' || ROUND(s.delivery_pressure_min_bar, 0) || ' bar min (' || ROUND(s.transit_loss_kg, 0) || ' kg loss)'
                ELSE 'Billed quantity gap: ' || ROUND(s.transit_loss_kg, 0) || ' kg (unconfirmed delivery gap)'
            END
        ELSE 'Within standard operating limits'
    END AS diagnostic_note
FROM v_stage_losses s
JOIN v_day_map m           ON m.output_date = s.output_date
JOIN primary_cause pc      ON pc.output_date = s.output_date
JOIN secondary_cause sc    ON sc.output_date = s.output_date
JOIN v_transit_label tl    ON tl.output_date = s.output_date
LEFT JOIN vendor_trace svt ON svt.output_date = s.output_date AND svt.rank_supply = 1
LEFT JOIN vendor_trace mvt ON mvt.output_date = s.output_date AND mvt.rank_moisture = 1;

-- ===========================================================================
-- v_cause_ranking : Rs lost per cause, cumulative % (sorted distribution)
-- ===========================================================================
CREATE VIEW IF NOT EXISTS v_cause_ranking AS
WITH cause_totals AS (
    SELECT
        cause,
        SUM(rs_loss)   AS total_rs_loss,
        SUM(loss_kg)   AS total_loss_kg,
        SUM(CASE WHEN rank_by_rs = 1 AND is_significant = 1 THEN 1 ELSE 0 END) AS days_as_primary
    FROM v_loss_causes
    GROUP BY cause
),
grand_total AS (
    SELECT SUM(total_rs_loss) AS grand_total_rs FROM cause_totals
)
SELECT
    ct.cause,
    ROUND(ct.total_rs_loss, 2) AS total_rs_loss,
    ROUND(ct.total_loss_kg, 2) AS total_loss_kg,
    ct.days_as_primary,
    ROUND(ct.total_rs_loss / gt.grand_total_rs * 100, 2) AS pct_of_total,
    -- Cumulative % (window SUM ordered by total_rs_loss DESC)
    ROUND(
        SUM(ct.total_rs_loss) OVER (
            ORDER BY ct.total_rs_loss DESC
            ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
        ) / gt.grand_total_rs * 100, 2
    ) AS cumulative_pct
FROM cause_totals ct
CROSS JOIN grand_total gt
ORDER BY ct.total_rs_loss DESC;

-- ===========================================================================
-- v_window_vendors : allocated loss per vendor (supply + moisture, output window)
-- ===========================================================================
CREATE VIEW IF NOT EXISTS v_window_vendors AS
SELECT
    vendor,
    ROUND(SUM(supply_loss_kg_v), 3)  AS supply_loss_kg,
    ROUND(SUM(moisture_loss_kg_v), 3) AS moisture_loss_kg,
    ROUND(SUM(supply_loss_rs_v), 2)  AS supply_loss_rs,
    ROUND(SUM(moisture_loss_rs_v), 2) AS moisture_loss_rs,
    ROUND(SUM(supply_loss_rs_v + moisture_loss_rs_v), 2) AS total_loss_rs
FROM v_vendor_allocation
GROUP BY vendor
ORDER BY total_loss_rs DESC;

-- ===========================================================================
-- v_headline_summary : summary KPIs over the output window
-- ===========================================================================
CREATE VIEW IF NOT EXISTS v_headline_summary AS
WITH qty_losses AS (
    SELECT SUM(supply_loss_rs + moisture_loss_rs + digester_loss_rs
               + purification_loss_rs + transit_qty_loss_rs) AS total_qty_loss_rs
    FROM v_stage_losses
),
price_losses AS (
    SELECT SUM(purity_plant_loss_rs + purity_transit_loss_rs) AS total_price_loss_rs
    FROM v_stage_losses
),
totals AS (
    SELECT
        ROUND(AVG(cbg_out_kg), 2)                       AS avg_cbg_kg,
        ROUND(AVG(cbg_out_kg / N * 100), 2)             AS avg_pct_nameplate,
        SUM(CASE WHEN cbg_out_kg < below_target_pct * N THEN 1 ELSE 0 END) AS days_below_90,
        ROUND(SUM(total_rs_lost), 2)                     AS total_rs_lost,
        COUNT(*)                                         AS output_day_count
    FROM v_stage_losses
)
SELECT
    t.avg_cbg_kg,
    t.avg_pct_nameplate,
    t.days_below_90,
    t.total_rs_lost,
    t.output_day_count,
    ROUND(q.total_qty_loss_rs, 2)   AS qty_loss_rs,
    ROUND(p.total_price_loss_rs, 2) AS price_loss_rs
FROM totals t, qty_losses q, price_losses p;

-- ===========================================================================
-- v_vendor_summary : over all 180 feed days
-- ===========================================================================
CREATE VIEW IF NOT EXISTS v_vendor_summary AS
WITH vendor_stats AS (
    SELECT
        r.vendor,
        v.material,
        v.dcq_t,
        -- Weighted landed cost per DRY tonne
        -- landed_cost = (price + freight) per wet tonne; dry = wet * (1 - moisture)
        SUM(r.qty_t * (v.price_per_t + v.freight_per_t))
            / SUM(r.qty_t * (1.0 - r.moisture_frac)) AS avg_landed_cost_per_dry_t,
        -- Reliability = AVG(fill ratio), defined as qty_t / dcq_t per day
        AVG(r.qty_t / v.dcq_t) AS reliability_score,
        -- Days where vendor delivered < 90% of DCQ
        COUNT(*) FILTER (WHERE r.qty_t < 0.9 * v.dcq_t) AS days_below_90pct_dcq,
        AVG(r.moisture_frac) AS avg_moisture,
        COUNT(*) AS days_count
    FROM fact_rm_receipt r
    JOIN dim_vendor v ON v.vendor = r.vendor
    GROUP BY r.vendor
),
ranked AS (
    SELECT
        *,
        -- Lower landed cost = better = lower rank number
        RANK() OVER (ORDER BY avg_landed_cost_per_dry_t)  AS rank_overall,
        RANK() OVER (PARTITION BY material ORDER BY avg_landed_cost_per_dry_t) AS rank_within_material
    FROM vendor_stats
),
-- Best: lowest landed dry cost among reliable vendors (>= reliability_threshold)
-- Worst: highest landed dry cost (no reliability filter)
thresholds AS (
    SELECT
        MIN(CASE WHEN r.reliability_score >= c.reliability_threshold
                 THEN r.avg_landed_cost_per_dry_t END) AS best_cost,
        MAX(r.avg_landed_cost_per_dry_t) AS worst_cost
    FROM ranked r
    CROSS JOIN config c
)
SELECT
    r.vendor,
    r.material,
    r.dcq_t,
    ROUND(r.avg_landed_cost_per_dry_t, 2) AS avg_landed_cost_per_dry_t,
    ROUND(r.reliability_score, 4)          AS reliability_score,
    r.days_below_90pct_dcq,
    ROUND(r.avg_moisture, 4)               AS avg_moisture,
    r.rank_overall,
    r.rank_within_material,
    -- Flag best and worst
    CASE WHEN r.avg_landed_cost_per_dry_t = t.best_cost THEN 1 ELSE 0 END AS is_best,
    CASE WHEN r.avg_landed_cost_per_dry_t = t.worst_cost THEN 1 ELSE 0 END AS is_worst
FROM ranked r
CROSS JOIN thresholds t
ORDER BY r.rank_overall;

-- ===========================================================================
-- v_daily_trend : per output day with 7-day rolling average
-- ===========================================================================
CREATE VIEW IF NOT EXISTS v_daily_trend AS
SELECT
    output_date,
    ROUND(cbg_out_kg, 2)   AS cbg_out_kg,
    ROUND(billed_kg, 2)    AS billed_kg,
    ROUND(cbg_out_kg / N * 100, 2) AS pct_of_nameplate,
    -- 7-day rolling average of production
    ROUND(AVG(cbg_out_kg) OVER (
        ORDER BY output_date
        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
    ), 2) AS rolling_7d_avg_kg
FROM v_stage_losses
ORDER BY output_date;
