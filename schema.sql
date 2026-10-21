-- CBG Plant Production Funnel
-- schema.sql: tables + single-row config

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------------
-- CONFIG (single row; all thresholds and parameters live here)
-- design_ch4_kg_per_t_solids is written by generate_data.py after computing
-- the calibrated yield so that perfect feed => exactly 3,000 kg output.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS config (
    start_date               TEXT    DEFAULT '2026-08-23',
    lag_days                 INTEGER DEFAULT 45,
    nameplate_kg             REAL    DEFAULT 3000,
    below_target_pct         REAL    DEFAULT 0.90,
    plant_need_t             REAL    DEFAULT 65,
    target_solids_frac       REAL    DEFAULT 0.15,
    design_purity            REAL    DEFAULT 0.98,
    design_slip              REAL    DEFAULT 0.01,
    slip_limit               REAL    DEFAULT 0.03,
    price_per_mmbtu          REAL    DEFAULT 2110,
    gcv_mmbtu_per_scm        REAL    DEFAULT 0.0376,
    gas_density_kg_per_scm   REAL    DEFAULT 0.717,
    correction_factor        REAL    DEFAULT 0.95,
    compression_charge_per_kg REAL   DEFAULT 8,
    transit_tolerance        REAL    DEFAULT 0.005,
    materiality_pct          REAL    DEFAULT 0.02,
    delivery_pressure_min_bar REAL   DEFAULT 200,
    reliability_threshold    REAL    DEFAULT 0.95,
    ch4_density_kg_per_nm3   REAL    DEFAULT 0.717,
    design_ch4_frac          REAL    DEFAULT 0.55,
    -- calibrated by generate_data.py; placeholder 0 avoids schema errors
    design_ch4_kg_per_t_solids REAL  DEFAULT 0
);

-- ---------------------------------------------------------------------------
-- DIM_VENDOR
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS dim_vendor (
    vendor   TEXT PRIMARY KEY,
    material TEXT NOT NULL CHECK (material IN ('dung', 'agri')),
    dcq_t    REAL NOT NULL,         -- daily contracted quantity, tonnes
    price_per_t   REAL NOT NULL,
    freight_per_t REAL NOT NULL
);

-- ---------------------------------------------------------------------------
-- FACT_RM_RECEIPT  (60 days x 5 vendors = 300 rows)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_rm_receipt (
    receipt_date TEXT NOT NULL,
    vendor       TEXT NOT NULL REFERENCES dim_vendor(vendor),
    qty_t        REAL NOT NULL,
    moisture_frac REAL NOT NULL CHECK (moisture_frac BETWEEN 0 AND 1),
    PRIMARY KEY (receipt_date, vendor)
);

-- ---------------------------------------------------------------------------
-- FACT_DIGESTER_FEED  (60 rows, one per feed day)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_digester_feed (
    feed_date   TEXT PRIMARY KEY,
    rm_fed_t    REAL NOT NULL,
    solids_fed_t REAL NOT NULL
);

-- ---------------------------------------------------------------------------
-- FACT_DIGESTER_OUTPUT  (days 46-60 = 15 rows; output_date is the calendar date)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_digester_output (
    output_date  TEXT PRIMARY KEY,
    biogas_nm3   REAL NOT NULL,
    ch4_frac     REAL NOT NULL CHECK (ch4_frac BETWEEN 0 AND 1)
);

-- ---------------------------------------------------------------------------
-- FACT_PURIFICATION  (days 46-60 = 15 rows)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_purification (
    output_date  TEXT PRIMARY KEY,
    ch4_in_kg    REAL NOT NULL,
    cbg_out_kg   REAL NOT NULL,
    purity_frac  REAL NOT NULL CHECK (purity_frac BETWEEN 0 AND 1)
);

-- ---------------------------------------------------------------------------
-- FACT_OMC_BILLING  (days 46-60 = 15 rows)
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fact_omc_billing (
    output_date           TEXT PRIMARY KEY,
    billed_kg             REAL NOT NULL,
    billed_purity_frac    REAL NOT NULL CHECK (billed_purity_frac BETWEEN 0 AND 1),
    delivery_pressure_bar REAL NOT NULL
);
