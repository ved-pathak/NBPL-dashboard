-- =============================================================================
-- BioPulse: CBG Capital Planning & Operational Unit Economics Platform
-- FILE: schema.sql
-- AUTHOR: Narmada Biofuels Pvt. Ltd. Analytics Engineering
-- PURPOSE: 3NF Relational Schema for a 3.0 TPD CBG Industrial Facility
-- DATABASE: SQLite3 / PostgreSQL compatible DDL
-- =============================================================================

PRAGMA foreign_keys = ON;  -- SQLite: enforce FK constraints

-- =============================================================================
-- TABLE 1: capex_milestones
-- Tracks capital expenditure milestones across project construction phases.
-- Categories: Civil Works, Mechanical Equipment, Electrical & Grid, Statutory Approvals
-- =============================================================================
CREATE TABLE IF NOT EXISTS capex_milestones (
    milestone_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    category            TEXT    NOT NULL CHECK (category IN (
                            'Civil Works',
                            'Mechanical Equipment',
                            'Electrical & Grid',
                            'Statutory Approvals'
                        )),
    milestone_name      TEXT    NOT NULL,
    vendor_name         TEXT    NOT NULL,
    budgeted_amount     REAL    NOT NULL CHECK (budgeted_amount > 0),
    actual_spend        REAL             CHECK (actual_spend >= 0),
    completion_pct      REAL             CHECK (completion_pct BETWEEN 0 AND 100),
    target_date         TEXT    NOT NULL,   -- ISO 8601: YYYY-MM-DD
    actual_date         TEXT,               -- NULL if milestone not yet completed
    variance_amount     REAL GENERATED ALWAYS AS (
                            CASE
                                WHEN actual_spend IS NOT NULL
                                THEN actual_spend - budgeted_amount
                                ELSE NULL
                            END
                        ) STORED,
    is_overdue          INTEGER GENERATED ALWAYS AS (
                            CASE
                                WHEN actual_date IS NULL
                                     AND date('now') > date(target_date)
                                THEN 1 ELSE 0
                            END
                        ) STORED
);

CREATE INDEX IF NOT EXISTS idx_capex_target_date ON capex_milestones(target_date);
CREATE INDEX IF NOT EXISTS idx_capex_category    ON capex_milestones(category);

-- =============================================================================
-- TABLE 2: debt_schedule
-- Amortization schedule for term-loan tranches with DSCR covenant thresholds.
-- Follows a typical Indian infrastructure project finance structure.
-- =============================================================================
CREATE TABLE IF NOT EXISTS debt_schedule (
    tranche_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    repayment_date          TEXT    NOT NULL UNIQUE,  -- Monthly repayment anchor date
    principal_due           REAL    NOT NULL CHECK (principal_due >= 0),
    interest_due            REAL    NOT NULL CHECK (interest_due >= 0),
    debt_service_total      REAL GENERATED ALWAYS AS (principal_due + interest_due) STORED,
    covenant_dscr_threshold REAL    NOT NULL DEFAULT 1.25
                                    CHECK (covenant_dscr_threshold > 0),
    tranche_label           TEXT    NOT NULL DEFAULT 'Term Loan - Tranche A'
);

CREATE INDEX IF NOT EXISTS idx_debt_repayment_date ON debt_schedule(repayment_date);

-- =============================================================================
-- TABLE 3: suppliers
-- Master table for feedstock suppliers with contract pricing and logistics.
-- =============================================================================
CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_name               TEXT    NOT NULL UNIQUE,
    feedstock_type              TEXT    NOT NULL CHECK (feedstock_type IN (
                                    'Press_Mud',
                                    'Cattle_Dung',
                                    'Crop_Residue'
                                )),
    distance_km                 REAL    NOT NULL CHECK (distance_km > 0),
    freight_rate_per_km_ton     REAL    NOT NULL CHECK (freight_rate_per_km_ton > 0),
    contracted_base_price_ton   REAL    NOT NULL CHECK (contracted_base_price_ton > 0),
    state                       TEXT    NOT NULL DEFAULT 'Madhya Pradesh',
    is_active                   INTEGER NOT NULL DEFAULT 1 CHECK (is_active IN (0, 1))
);

-- =============================================================================
-- TABLE 4: feedstock_inward_logs
-- Daily records of raw feedstock deliveries at the plant gate.
-- Includes quality metrics critical for digester performance modeling.
-- =============================================================================
CREATE TABLE IF NOT EXISTS feedstock_inward_logs (
    receipt_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id         INTEGER NOT NULL REFERENCES suppliers(supplier_id)
                            ON DELETE RESTRICT ON UPDATE CASCADE,
    delivery_date       TEXT    NOT NULL,
    gross_weight_tons   REAL    NOT NULL CHECK (gross_weight_tons > 0),
    moisture_pct        REAL    NOT NULL CHECK (moisture_pct BETWEEN 0 AND 100),
    cn_ratio            REAL    NOT NULL CHECK (cn_ratio > 0),  -- Carbon:Nitrogen ratio (optimal: 20-30)
    volatile_solids_pct REAL    NOT NULL DEFAULT 75.0
                                CHECK (volatile_solids_pct BETWEEN 0 AND 100),
    unloading_cost      REAL    NOT NULL CHECK (unloading_cost >= 0),
    freight_cost        REAL    NOT NULL CHECK (freight_cost >= 0),
    total_landed_cost   REAL    NOT NULL CHECK (total_landed_cost >= 0),
    quality_grade       TEXT             CHECK (quality_grade IN ('A', 'B', 'C', 'Rejected'))
);

CREATE INDEX IF NOT EXISTS idx_feedstock_delivery_date ON feedstock_inward_logs(delivery_date);
CREATE INDEX IF NOT EXISTS idx_feedstock_supplier_id   ON feedstock_inward_logs(supplier_id);

-- =============================================================================
-- TABLE 5: yard_inventory_aging
-- Tracks feedstock lot aging in storage bays — critical for VS loss modeling.
-- High storage_days → elevated volatile_solids_loss_pct → lower biogas yield.
-- =============================================================================
CREATE TABLE IF NOT EXISTS yard_inventory_aging (
    lot_id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id              INTEGER NOT NULL REFERENCES feedstock_inward_logs(receipt_id)
                                ON DELETE CASCADE ON UPDATE CASCADE,
    storage_bay             TEXT    NOT NULL,   -- e.g., 'Bay-A1', 'Bay-B2'
    entry_date              TEXT    NOT NULL,
    feed_date               TEXT,               -- NULL if not yet consumed
    storage_days            INTEGER GENERATED ALWAYS AS (
                                CASE
                                    WHEN feed_date IS NOT NULL
                                    THEN CAST(julianday(feed_date) - julianday(entry_date) AS INTEGER)
                                    ELSE CAST(julianday('now') - julianday(entry_date) AS INTEGER)
                                END
                            ) STORED,
    volatile_solids_loss_pct REAL   NOT NULL DEFAULT 0.0
                                    CHECK (volatile_solids_loss_pct BETWEEN 0 AND 50)
);

CREATE INDEX IF NOT EXISTS idx_yard_entry_date ON yard_inventory_aging(entry_date);
CREATE INDEX IF NOT EXISTS idx_yard_receipt_id ON yard_inventory_aging(receipt_id);

-- =============================================================================
-- TABLE 6: digester_production_logs
-- Core operational table — daily production KPIs from the anaerobic digester.
-- Supports OPEX modeling, capacity utilization, and revenue recognition.
-- =============================================================================
CREATE TABLE IF NOT EXISTS digester_production_logs (
    production_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    production_date     TEXT    NOT NULL UNIQUE,
    tons_biomass_fed    REAL    NOT NULL CHECK (tons_biomass_fed >= 0),
    biogas_yield_nm3    REAL    NOT NULL CHECK (biogas_yield_nm3 >= 0),   -- Normal m³ raw biogas
    ch4_purity_pct      REAL    NOT NULL CHECK (ch4_purity_pct BETWEEN 0 AND 100),
    cbg_produced_kg     REAL    NOT NULL CHECK (cbg_produced_kg >= 0),    -- Post-compression CBG
    power_consumed_kwh  REAL    NOT NULL CHECK (power_consumed_kwh >= 0),
    plant_downtime_hrs  REAL    NOT NULL DEFAULT 0.0
                                CHECK (plant_downtime_hrs BETWEEN 0 AND 24),
    offtake_revenue     REAL    NOT NULL CHECK (offtake_revenue >= 0),    -- INR/day from PSU buyer
    grid_export_units   REAL             DEFAULT 0.0,                      -- kWh exported to grid
    specific_energy_kwh_per_kg REAL GENERATED ALWAYS AS (
                            CASE
                                WHEN cbg_produced_kg > 0
                                THEN power_consumed_kwh / cbg_produced_kg
                                ELSE NULL
                            END
                        ) STORED
);

CREATE INDEX IF NOT EXISTS idx_production_date ON digester_production_logs(production_date);

-- =============================================================================
-- TABLE 7: daily_cash_treasury
-- Working capital ledger — daily opening/closing cash position.
-- Foundation for DSCR computation, runway analysis, and covenant monitoring.
-- =============================================================================
CREATE TABLE IF NOT EXISTS daily_cash_treasury (
    entry_date          TEXT    PRIMARY KEY,
    opening_cash        REAL    NOT NULL,
    operational_inflow  REAL    NOT NULL DEFAULT 0.0 CHECK (operational_inflow >= 0),
    feedstock_outflow   REAL    NOT NULL DEFAULT 0.0 CHECK (feedstock_outflow >= 0),
    power_outflow       REAL    NOT NULL DEFAULT 0.0 CHECK (power_outflow >= 0),
    misc_opex           REAL    NOT NULL DEFAULT 0.0 CHECK (misc_opex >= 0),
    debt_servicing      REAL    NOT NULL DEFAULT 0.0 CHECK (debt_servicing >= 0),
    receivables_stretch_days INTEGER DEFAULT 30,        -- Actual debtor collection days
    closing_cash        REAL GENERATED ALWAYS AS (
                            opening_cash
                            + operational_inflow
                            - feedstock_outflow
                            - power_outflow
                            - misc_opex
                            - debt_servicing
                        ) STORED
);

CREATE INDEX IF NOT EXISTS idx_treasury_entry_date ON daily_cash_treasury(entry_date);

-- =============================================================================
-- VIEWS: Pre-computed analytical views for dashboard consumption
-- =============================================================================

-- View: Supplier dry-cost ranking
CREATE VIEW IF NOT EXISTS vw_supplier_dry_cost AS
SELECT
    f.receipt_id,
    f.delivery_date,
    s.supplier_name,
    s.feedstock_type,
    f.gross_weight_tons,
    f.moisture_pct,
    ROUND(f.gross_weight_tons * (1.0 - f.moisture_pct / 100.0), 3)  AS dry_weight_tons,
    f.total_landed_cost,
    CASE
        WHEN f.gross_weight_tons * (1.0 - f.moisture_pct / 100.0) > 0
        THEN ROUND(
            f.total_landed_cost / (f.gross_weight_tons * (1.0 - f.moisture_pct / 100.0)),
            2)
        ELSE NULL
    END                                                               AS landed_cost_per_dry_ton
FROM feedstock_inward_logs f
JOIN suppliers s ON s.supplier_id = f.supplier_id;

-- View: Daily production efficiency
CREATE VIEW IF NOT EXISTS vw_daily_efficiency AS
SELECT
    d.production_date,
    d.tons_biomass_fed,
    d.biogas_yield_nm3,
    d.ch4_purity_pct,
    d.cbg_produced_kg,
    d.plant_downtime_hrs,
    d.offtake_revenue,
    ROUND(d.cbg_produced_kg / 3000.0 * 100.0, 2)  AS capacity_utilization_pct,
    CASE
        WHEN d.tons_biomass_fed > 0
        THEN ROUND(d.biogas_yield_nm3 / d.tons_biomass_fed, 2)
        ELSE 0
    END                                             AS specific_biogas_yield,
    CASE WHEN d.cbg_produced_kg < 2550 THEN 1 ELSE 0 END AS is_underperformance_day
FROM digester_production_logs d;

-- =============================================================================
-- END OF SCHEMA
-- =============================================================================
