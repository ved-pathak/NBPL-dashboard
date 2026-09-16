"""
=============================================================================
BioPulse: CBG Capital Planning & Operational Unit Economics Platform
FILE: generate_data.py
AUTHOR: Analytics Engineering — Narmada Biofuels Pvt. Ltd.
PURPOSE: Synthetic data seeder for a 3.0 TPD CBG industrial facility.
         Generates 12-month CAPEX construction data + 180-day operations data
         with 3 injected anomaly clusters for RCA modeling.

ANOMALY CLUSTERS:
  [A1] Days 40-52  : Supplier B delivers high-moisture press mud (72% vs 58% baseline)
                     → Landed dry-cost spikes, digester gas yield dips 20%
  [A2] Days 100-110: Unscheduled compressor seal failure, 18 hrs/day downtime
                     → Daily CBG fulfillment drops to 65%, PSU penalty exposure
  [A3] Days 145-165: PSU payment delay (receivables stretch 30→75 days)
                     → Closing cash plunges, DSCR covenant warning triggered (<1.20x)

USAGE:
  python generate_data.py
=============================================================================
"""

import sqlite3
import os
import random
import math
from datetime import date, timedelta, datetime
from collections import defaultdict

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# CONFIGURATION
# ---------------------------------------------------------------------------
DB_PATH          = "biopulse_cbg.db"
SCHEMA_PATH      = "schema.sql"
RANDOM_SEED      = 42
OPS_START_DATE   = date(2024, 1, 1)   # Day 1 of operations (after construction)
CAPEX_START_DATE = date(2023, 1, 1)   # Construction kickoff
CBG_TARGET_KG    = 3000.0             # 3 TPD target
CBG_PRICE_PER_KG = 78.0              # INR/kg — MNGL/IGL type PSU offtake price
POWER_RATE_UNIT  = 8.50              # INR/kWh (industrial tariff, MP Discoms)

np.random.seed(RANDOM_SEED)
random.seed(RANDOM_SEED)

# ---------------------------------------------------------------------------
# DATABASE INITIALISATION
# ---------------------------------------------------------------------------

def init_database(db_path: str, schema_path: str) -> sqlite3.Connection:
    """
    Drop all existing tables (clean slate) and re-apply the DDL schema.
    Returns an active SQLite connection with FK enforcement enabled.
    """
    print(f"[INIT] Connecting to database: {db_path}")
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = OFF")   # Disable FK for clean drop

    # Drop all user tables in dependency order (children first)
    drop_order = [
        "yard_inventory_aging",
        "feedstock_inward_logs",
        "digester_production_logs",
        "daily_cash_treasury",
        "debt_schedule",
        "capex_milestones",
        "suppliers",
    ]
    for table in drop_order:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.execute("DROP VIEW IF EXISTS vw_supplier_dry_cost")
    conn.execute("DROP VIEW IF EXISTS vw_daily_efficiency")
    conn.commit()

    # Re-apply schema
    print(f"[INIT] Applying schema from: {schema_path}")
    with open(schema_path, "r") as f:
        schema_sql = f.read()

    # Execute schema statement by statement (sqlite3 doesn't support executescript well with GENERATED cols)
    conn.executescript(schema_sql)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    print("[INIT] Schema applied successfully.\n")
    return conn


# ---------------------------------------------------------------------------
# STEP 1: CAPEX MILESTONES — 12-month construction phase
# ---------------------------------------------------------------------------

CAPEX_MILESTONES_DEFINITION = [
    # (category, milestone_name, vendor, budget_INR_lakhs, months_from_start, overrun_factor)
    # Civil Works — ~25% of project cost
    ("Civil Works", "Site Levelling & Boundary Wall",    "Shree Ram Constructions",    28.00,  1, 1.04),
    ("Civil Works", "Digester Civil Foundation",         "Shree Ram Constructions",    55.00,  3, 1.06),
    ("Civil Works", "Control Room & Admin Building",     "Shree Ram Constructions",    18.00,  4, 1.03),
    ("Civil Works", "Internal Roads & Drainage",         "MP State PWD",               12.00,  5, 1.05),
    ("Civil Works", "Effluent Treatment Pond Lining",    "Shree Ram Constructions",    20.00,  6, 1.07),

    # Mechanical Equipment — ~45% of project cost (scrubbers & compressors overrun 8-15%)
    ("Mechanical Equipment", "CSTR Digester Vessel (2×750m³)", "Greenfield Biotech Pvt Ltd",  185.00, 4, 1.06),
    ("Mechanical Equipment", "H2S Scrubber (Water Wash)",       "Paharpur Cooling Systems",     42.00,  5, 1.12),  # 12% overrun
    ("Mechanical Equipment", "CO2 Membrane Scrubber Unit",      "Paharpur Cooling Systems",     65.00,  6, 1.14),  # 14% overrun
    ("Mechanical Equipment", "CNG Compressor (3-stage)",        "Bauer Compressors India",      78.00,  7, 1.15),  # 15% overrun
    ("Mechanical Equipment", "Slurry Agitators & Pumps",        "Roto Pumps Ltd",               22.00,  6, 1.04),
    ("Mechanical Equipment", "Biogas Storage Balloon (500m³)",  "Greenfield Biotech Pvt Ltd",   18.00,  7, 1.08),
    ("Mechanical Equipment", "Desulphurisation Unit",           "Paharpur Cooling Systems",     24.00,  8, 1.10),  # 10% overrun

    # Electrical & Grid — ~20% of project cost
    ("Electrical & Grid", "HT Power Connection (33kV)",         "MP TRANSCO",                   35.00,  3, 1.03),
    ("Electrical & Grid", "Transformer & Switchgear",           "Schneider Electric India",     28.00,  5, 1.05),
    ("Electrical & Grid", "SCADA / DCS Instrumentation",        "Honeywell India Pvt Ltd",      32.00,  8, 1.09),
    ("Electrical & Grid", "Internal Electrical Cabling",        "L&T Electrical",               15.00,  6, 1.04),

    # Statutory Approvals — ~10% of project cost (government fees + legal)
    ("Statutory Approvals", "MoEF Environmental Clearance",     "Green Consultants India",       8.00,  2, 1.00),
    ("Statutory Approvals", "Petroleum & Explosives Safety Org (PESO) License", "Safety & Standards India", 5.00, 4, 1.00),
    ("Statutory Approvals", "CPCB Consent to Establish",        "Green Consultants India",       4.00,  3, 1.00),
    ("Statutory Approvals", "CPCB Consent to Operate",          "Green Consultants India",       4.00,  9, 1.00),
    ("Statutory Approvals", "Factory Licence & Fire NOC",       "Legal Advisors LLP",            3.00,  8, 1.00),
]


def generate_capex_milestones(conn: sqlite3.Connection) -> None:
    """Generate 12-month CAPEX milestone data with realistic cost overruns."""
    print("[CAPEX] Generating capex_milestones ...")
    records = []
    for (category, name, vendor, budget_lakh, months_offset, overrun_factor) in CAPEX_MILESTONES_DEFINITION:
        budget_inr     = budget_lakh * 100_000   # Convert lakhs to INR

        # Add stochastic noise ±2% around the overrun factor
        noise          = np.random.uniform(-0.02, 0.02)
        actual_factor  = overrun_factor + noise
        actual_spend   = round(budget_inr * actual_factor, 2)

        # Target date: nth month from construction start
        target_dt      = CAPEX_START_DATE + timedelta(days=months_offset * 30)
        # Actual date: a few days before/after target (construction rarely perfect)
        delay_days     = int(np.random.randint(-5, 21))
        actual_dt      = target_dt + timedelta(days=delay_days)

        # Completion percentage — assume all milestones complete by end of construction
        completion_pct = 100.0

        records.append((
            category,
            name,
            vendor,
            round(budget_inr, 2),
            actual_spend,
            completion_pct,
            target_dt.isoformat(),
            actual_dt.isoformat(),
        ))

    conn.executemany("""
        INSERT INTO capex_milestones
            (category, milestone_name, vendor_name, budgeted_amount, actual_spend,
             completion_pct, target_date, actual_date)
        VALUES (?,?,?,?,?,?,?,?)
    """, records)
    conn.commit()
    print(f"[CAPEX] Inserted {len(records)} milestone records.\n")


# ---------------------------------------------------------------------------
# STEP 2: DEBT SCHEDULE — 7-year term loan amortisation
# ---------------------------------------------------------------------------

def generate_debt_schedule(conn: sqlite3.Connection) -> None:
    """
    Generate a 24-month rolling debt schedule for the operations window.
    Loan: INR 4.5 Crore term loan at 11.5% p.a. (typical Indian NBFC/SBI rate).
    Structure: 7-year tenor, 6-month moratorium, equal principal + declining interest.
    """
    print("[DEBT] Generating debt_schedule ...")
    LOAN_PRINCIPAL    = 45_000_000   # INR 4.5 Cr
    ANNUAL_RATE       = 0.115        # 11.5% per annum
    MONTHLY_RATE      = ANNUAL_RATE / 12
    TOTAL_EMI_MONTHS  = 78           # 84 months tenure - 6 months moratorium

    # Monthly principal repayment (equal principal method)
    monthly_principal = LOAN_PRINCIPAL / TOTAL_EMI_MONTHS

    records = []
    outstanding = LOAN_PRINCIPAL
    # Start repayment from Month 7 of operations (post-moratorium)
    start_date = date(2024, 1, 1)  # Align with ops start

    for i in range(24):  # Generate 24 monthly entries covering our analysis window
        repayment_date = start_date + timedelta(days=i * 30)
        interest       = round(outstanding * MONTHLY_RATE, 2)
        principal      = round(monthly_principal, 2)
        outstanding   -= principal

        # DSCR threshold: slightly tighter in early years (lender covenant)
        dscr_threshold = 1.25 if i < 12 else 1.20

        records.append((
            repayment_date.isoformat(),
            principal,
            interest,
            dscr_threshold,
            "Term Loan - Tranche A (SBI Infrastructure Finance)",
        ))

    conn.executemany("""
        INSERT INTO debt_schedule
            (repayment_date, principal_due, interest_due, covenant_dscr_threshold, tranche_label)
        VALUES (?,?,?,?,?)
    """, records)
    conn.commit()
    print(f"[DEBT] Inserted {len(records)} debt schedule records.\n")


# ---------------------------------------------------------------------------
# STEP 3: SUPPLIERS — Master data
# ---------------------------------------------------------------------------

SUPPLIERS_DATA = [
    # (name, feedstock_type, distance_km, freight_rate_inr_per_km_ton, base_price_inr_per_ton)
    # Press Mud suppliers (sugar mill byproduct — high VS, preferred feedstock)
    ("Supplier-A: Hiranya Sugar Mills",    "Press_Mud",    18.0, 4.20, 320.0),
    ("Supplier-B: Rajgad Khand Udyog",    "Press_Mud",    42.0, 4.80, 290.0),  # Far, anomaly source
    ("Supplier-C: Om Shakti Agro",        "Press_Mud",    11.0, 4.00, 340.0),

    # Cattle Dung suppliers (local dairy farms — stable but lower yield)
    ("Supplier-D: Nandanvan Dairy Farm",  "Cattle_Dung",   6.0, 3.50, 210.0),
    ("Supplier-E: GauShala Trust Harda",  "Cattle_Dung",  14.0, 3.80, 195.0),

    # Crop Residue (seasonal — paddy straw, soya stalk; high C:N ratio)
    ("Supplier-F: Kisan Agri Collective", "Crop_Residue", 28.0, 5.10, 180.0),
    ("Supplier-G: Sarpanch Farm Produce", "Crop_Residue", 35.0, 5.40, 165.0),
]


def generate_suppliers(conn: sqlite3.Connection) -> None:
    """Seed the suppliers master table."""
    print("[SUPPLIERS] Generating suppliers ...")
    conn.executemany("""
        INSERT INTO suppliers
            (supplier_name, feedstock_type, distance_km,
             freight_rate_per_km_ton, contracted_base_price_ton)
        VALUES (?,?,?,?,?)
    """, SUPPLIERS_DATA)
    conn.commit()

    # Retrieve assigned IDs for FK use
    cursor = conn.execute("SELECT supplier_id, supplier_name FROM suppliers ORDER BY supplier_id")
    rows   = cursor.fetchall()
    print(f"[SUPPLIERS] Inserted {len(rows)} supplier records:")
    for r in rows:
        print(f"  ID={r[0]}: {r[1]}")
    print()


def get_supplier_map(conn: sqlite3.Connection) -> dict:
    """Returns {supplier_name_short: supplier_id} from DB."""
    cursor = conn.execute("SELECT supplier_id, supplier_name FROM suppliers")
    return {row[1]: row[0] for row in cursor.fetchall()}


# ---------------------------------------------------------------------------
# STEP 4 & 5: FEEDSTOCK INWARD LOGS + YARD INVENTORY AGING
# ---------------------------------------------------------------------------

def generate_feedstock_and_yard(conn: sqlite3.Connection) -> dict:
    """
    Generate 180 days of feedstock inward logs and yard inventory aging.
    Returns mapping {feed_date_iso: {quality metrics}} for cross-table causal consistency.

    ARCHITECTURAL FIXES:
    1. Inventory Lag (Causality): Maps daily quality metrics to feed_date (delivery_date + storage_lag)
       so that digester performance drops when the material is actually fed (Days 42-54),
       rather than on gate delivery date (Days 40-52).
    2. Market Volatility: Injects stochastic daily price drift (-1.5% to +2.5%) into material cost.
    """
    print("[FEEDSTOCK] Generating feedstock_inward_logs & yard_inventory_aging ...")
    supplier_map = get_supplier_map(conn)

    # Map short keys to supplier IDs
    sup_a = supplier_map["Supplier-A: Hiranya Sugar Mills"]
    sup_b = supplier_map["Supplier-B: Rajgad Khand Udyog"]
    sup_c = supplier_map["Supplier-C: Om Shakti Agro"]
    sup_d = supplier_map["Supplier-D: Nandanvan Dairy Farm"]
    sup_e = supplier_map["Supplier-E: GauShala Trust Harda"]
    sup_f = supplier_map["Supplier-F: Kisan Agri Collective"]

    inward_records    = []
    delivery_metadata = []
    feed_lots_by_date = defaultdict(list)
    bays = ["Bay-A1", "Bay-A2", "Bay-B1", "Bay-B2", "Bay-C1"]

    for day_idx in range(180):
        op_date = OPS_START_DATE + timedelta(days=day_idx)
        op_day  = day_idx + 1  # 1-indexed

        # Feedstock sourcing mix: Anomaly [A1] Days 40-52 at delivery gate
        is_anomaly_a1 = (40 <= op_day <= 52)

        if is_anomaly_a1:
            daily_suppliers = [
                (sup_b, 13.5 + np.random.uniform(-0.5, 0.5), "Press_Mud"),
                (sup_d, 4.5 + np.random.uniform(-0.2, 0.2), "Cattle_Dung"),
            ]
        elif op_day % 7 == 0:
            daily_suppliers = [
                (sup_a, 12.0 + np.random.uniform(-1.0, 1.0), "Press_Mud"),
                (sup_d, 4.0 + np.random.uniform(-0.3, 0.3), "Cattle_Dung"),
                (sup_e, 2.5 + np.random.uniform(-0.2, 0.2), "Cattle_Dung"),
            ]
        elif op_day % 3 == 0:
            daily_suppliers = [
                (sup_c, 11.0 + np.random.uniform(-0.8, 0.8), "Press_Mud"),
                (sup_d, 4.5 + np.random.uniform(-0.3, 0.3), "Cattle_Dung"),
                (sup_e, 2.0 + np.random.uniform(-0.2, 0.2), "Cattle_Dung"),
            ]
        elif op_day > 120 and op_day % 5 == 0:
            daily_suppliers = [
                (sup_a, 9.0 + np.random.uniform(-0.5, 0.5), "Press_Mud"),
                (sup_d, 5.0 + np.random.uniform(-0.3, 0.3), "Cattle_Dung"),
                (sup_f, 4.0 + np.random.uniform(-0.3, 0.3), "Crop_Residue"),
            ]
        else:
            daily_suppliers = [
                (sup_a, 11.0 + np.random.uniform(-0.8, 0.8), "Press_Mud"),
                (sup_d, 5.0 + np.random.uniform(-0.3, 0.3), "Cattle_Dung"),
                (sup_e, 2.0 + np.random.uniform(-0.2, 0.2), "Cattle_Dung"),
            ]

        # Storage retention for this day's inward batch (standard FIFO retention: 2 days)
        storage_lag = 2
        feed_date   = op_date + timedelta(days=storage_lag)
        vs_loss_pct = min(round(storage_lag * np.random.uniform(1.5, 2.2), 2), 25.0)

        for (sup_id, gross_tons, ftype) in daily_suppliers:
            gross_tons = max(0.5, gross_tons)

            # Quality metrics by feedstock type
            if ftype == "Press_Mud":
                if is_anomaly_a1 and sup_id == sup_b:
                    moisture = np.random.uniform(69.0, 74.0)  # Anomaly: ~72% vs 58% baseline
                    cn_ratio = np.random.uniform(18.0, 22.0)
                    vs_pct   = np.random.uniform(70.0, 76.0)
                else:
                    moisture = np.random.uniform(55.0, 61.0)  # Baseline: 55-61%
                    cn_ratio = np.random.uniform(22.0, 28.0)
                    vs_pct   = np.random.uniform(75.0, 80.0)
            elif ftype == "Cattle_Dung":
                moisture     = np.random.uniform(75.0, 80.0)
                cn_ratio     = np.random.uniform(18.0, 22.0)
                vs_pct       = np.random.uniform(70.0, 75.0)
            else:  # Crop_Residue
                moisture     = np.random.uniform(10.0, 18.0)
                cn_ratio     = np.random.uniform(50.0, 75.0)
                vs_pct       = np.random.uniform(80.0, 88.0)

            # Lookup supplier contract parameters
            sup_row = conn.execute(
                "SELECT distance_km, freight_rate_per_km_ton, contracted_base_price_ton "
                "FROM suppliers WHERE supplier_id=?", (sup_id,)
            ).fetchone()
            distance, freight_rate, base_price = sup_row

            # Market Volatility Injection: stochastic daily drift between -1.5% and +2.5%
            market_volatility_multiplier = 1.0 + np.random.uniform(-0.015, 0.025)
            spot_base_price = round(base_price * market_volatility_multiplier, 2)

            freight_cost   = round(distance * freight_rate * gross_tons, 2)
            unloading_cost = round(gross_tons * 55.0 + np.random.uniform(-5, 5), 2)
            material_cost  = round(gross_tons * spot_base_price, 2)
            total_landed   = round(freight_cost + unloading_cost + material_cost, 2)

            inward_records.append((
                sup_id,
                op_date.isoformat(),
                round(gross_tons, 3),
                round(moisture, 2),
                round(cn_ratio, 2),
                round(vs_pct, 2),
                unloading_cost,
                freight_cost,
                total_landed,
                "A" if moisture < 65 else ("B" if moisture < 72 else "C"),
            ))

            delivery_metadata.append({
                "entry_date": op_date.isoformat(),
                "feed_date": feed_date.isoformat(),
                "vs_loss_pct": vs_loss_pct,
                "storage_lag": storage_lag,
                "bay": random.choice(bays),
            })

            # Map quality metrics to the feed_date (when substrate is actually fed into digester)
            feed_lots_by_date[feed_date.isoformat()].append({
                "moisture": moisture,
                "vs_loss": vs_loss_pct,
                "cn_ratio": cn_ratio,
                "gross_tons": gross_tons,
            })

    # Bulk insert feedstock inward logs
    conn.executemany("""
        INSERT INTO feedstock_inward_logs
            (supplier_id, delivery_date, gross_weight_tons, moisture_pct, cn_ratio,
             volatile_solids_pct, unloading_cost, freight_cost, total_landed_cost, quality_grade)
        VALUES (?,?,?,?,?,?,?,?,?,?)
    """, inward_records)
    conn.commit()

    # Insert yard inventory aging matching each receipt_id
    cursor = conn.execute("SELECT receipt_id FROM feedstock_inward_logs ORDER BY receipt_id")
    receipt_ids = [row[0] for row in cursor.fetchall()]

    yard_records = []
    for receipt_id, meta in zip(receipt_ids, delivery_metadata):
        yard_records.append((
            receipt_id,
            meta["bay"],
            meta["entry_date"],
            meta["feed_date"],
            meta["vs_loss_pct"],
        ))

    conn.executemany("""
        INSERT INTO yard_inventory_aging
            (receipt_id, storage_bay, entry_date, feed_date, volatile_solids_loss_pct)
        VALUES (?,?,?,?,?)
    """, yard_records)
    conn.commit()

    # Aggregate quality metrics per feed_date (weighted blend by tons)
    date_quality_map = {}
    for feed_dt_str, lots in feed_lots_by_date.items():
        total_tons = sum(l["gross_tons"] for l in lots)
        if total_tons > 0:
            avg_moisture = sum(l["moisture"] * l["gross_tons"] for l in lots) / total_tons
            avg_vs_loss  = sum(l["vs_loss"] * l["gross_tons"] for l in lots) / total_tons
            avg_cn       = sum(l["cn_ratio"] * l["gross_tons"] for l in lots) / total_tons
        else:
            avg_moisture = float(np.mean([l["moisture"] for l in lots]))
            avg_vs_loss  = float(np.mean([l["vs_loss"] for l in lots]))
            avg_cn       = float(np.mean([l["cn_ratio"] for l in lots]))

        date_quality_map[feed_dt_str] = {
            "moisture_pct": float(round(avg_moisture, 2)),
            "volatile_solids_loss_pct": float(round(avg_vs_loss, 2)),
            "cn_ratio": float(round(avg_cn, 2)),
        }

    # Ensure baseline fallback for pre-commissioning yard inventory on Days 1 & 2
    for init_day in range(2):
        init_date_str = (OPS_START_DATE + timedelta(days=init_day)).isoformat()
        if init_date_str not in date_quality_map:
            date_quality_map[init_date_str] = {
                "moisture_pct": 64.2,
                "volatile_solids_loss_pct": 3.8,
                "cn_ratio": 24.5,
            }

    print(f"[FEEDSTOCK] Inserted {len(inward_records)} inward log records (stochastic market volatility enabled).")
    print(f"[YARD] Inserted {len(yard_records)} yard aging records (synchronized feed_dates).")
    print(f"[YARD] Mapped quality metrics across {len(date_quality_map)} feed dates (inventory lag causality enforced).\n")
    return date_quality_map


def _get_supplier_row_id(conn, sid):
    """Helper to pass-through supplier ID for lookup."""
    return sid


# ---------------------------------------------------------------------------
# STEP 6: DIGESTER PRODUCTION LOGS
# ---------------------------------------------------------------------------

def generate_production_logs(
    conn: sqlite3.Connection,
    date_quality_map: dict,
) -> None:
    """
    Generate 180 days of digester production logs.
    Biogas yield and CBG production are coupled to feedstock quality.

    Scientific basis:
      - Biogas yield from Press Mud: ~200-220 Nm³/ton VS at 38°C mesophilic
      - CH4 content baseline: 60-65% raw biogas → 95%+ after CO2 scrubbing
      - CBG compression efficiency: ~92% of scrubbed biogas volume
      - Energy density: ~50 MJ/kg CBG (equivalent to ~0.9 kg CBG per Nm³ pure CH4)

    ORGANIC YIELD & PURITY MODELING:
      Removes hardcoded anomaly day triggers (e.g. 40 <= op_day <= 52).
      Yield and purity drop organically whenever the date_quality_map reflects high moisture,
      which occurs 2 days post-delivery (Days 42-54) due to yard storage lag.

    ANOMALY [A2] Days 100-110:
      Compressor seal failure → 18 hrs downtime/day.
    """
    print("[PRODUCTION] Generating digester_production_logs ...")

    records    = []
    BASE_YIELD_NM3_PER_TON_WET = 200.0   # Nm³ raw biogas per ton WET feedstock
    BIOMASS_DESIGN_TPD         = 18.0    # Wet biomass feed rate (ton/day) for 3 TPD CBG
    POWER_DESIGN_KWH           = 1800.0  # kWh/day at full load (18T plant scale)
    CH4_COMPRESSION_FACTOR     = 1.88    # Real-gas compression factor at 200 bar
    CBG_OFFTAKE_PRICE          = 78.0     # INR/kg

    for day_idx in range(180):
        op_date = OPS_START_DATE + timedelta(days=day_idx)
        op_day  = day_idx + 1
        dq      = date_quality_map.get(op_date.isoformat(), {})

        moisture_pct = dq.get("moisture_pct", 64.2)
        vs_loss_pct  = dq.get("volatile_solids_loss_pct", 3.8)
        cn_ratio     = dq.get("cn_ratio", 24.5)

        # Operational equipment anomaly A2: Unscheduled compressor seal failure
        is_anomaly_a2 = (100 <= op_day <= 110)

        # Biomass fed (wet tons): operator increases feed rate by ~4% when feedstock is wet
        base_biomass = BIOMASS_DESIGN_TPD
        if moisture_pct > 68.0:
            base_biomass = BIOMASS_DESIGN_TPD * 1.04
        biomass_fed = max(8.0, base_biomass + np.random.normal(0, 0.5))

        # Organic biochemical yield modeling:
        # Baseline wet blend: ~64.5% moisture (35.5% active dry solids).
        # Substrate availability scales with dry solids: (100 - moisture_pct) / 35.5
        dry_matter_ratio = max(0.50, (100.0 - moisture_pct) / 35.5)

        # Non-linear hydraulic dilution penalty: excess water reduces microbial retention and thermal efficiency
        dilution_penalty = max(0.0, (moisture_pct - 67.0) * 0.018) if moisture_pct > 67.0 else 0.0

        # Volatile solids degradation from yard retention
        vs_loss_factor = max(0.70, 1.0 - (vs_loss_pct / 100.0 * 0.40))

        # Carbon-to-Nitrogen ratio balance (optimum range: 18 - 35)
        cn_factor = 0.92 if (cn_ratio < 18 or cn_ratio > 35) else 1.0

        # Total organic yield factor (driven purely by substrate chemistry & yard retention)
        yield_factor = dry_matter_ratio * (1.0 - dilution_penalty) * vs_loss_factor * cn_factor

        # Raw biogas production (Nm³/day)
        biogas_yield_nm3 = max(0.0,
            biomass_fed * BASE_YIELD_NM3_PER_TON_WET * yield_factor
            + np.random.normal(0, 35))

        # CH4 purity after scrubbing: baseline 92.5% - 95.5%
        # When blend moisture > 67%, elevated CO2 & moisture loading in raw gas causes organic scrubbing drag
        if moisture_pct > 67.0:
            purity_drag = (moisture_pct - 66.0) * 0.55
            ch4_pct = max(86.5, np.random.uniform(92.0, 94.0) - purity_drag + np.random.normal(0, 0.3))
        else:
            ch4_pct = np.random.uniform(92.2, 95.5)

        # CBG produced (kg):
        ch4_volume_nm3 = biogas_yield_nm3 * 0.63         # ~63% CH4 in raw biogas (pre-scrub)
        scrub_eff      = np.random.uniform(0.91, 0.95)   # Scrubbing capture efficiency
        cbg_produced   = max(0.0,
            ch4_volume_nm3 * 0.717 * CH4_COMPRESSION_FACTOR * scrub_eff
            + np.random.normal(0, 25))

        # ---------------------------------------------------------------
        # ANOMALY A2: Compressor seal failure → 18 hrs/day downtime
        # ---------------------------------------------------------------
        if is_anomaly_a2:
            downtime_hrs  = np.random.uniform(16.0, 20.0)   # 16-20 hrs downtime
            cbg_produced *= 0.65 + np.random.uniform(-0.05, 0.05)  # 65% fulfillment
            ch4_pct       = np.random.uniform(85.0, 90.0)   # Seal failure affects purity
        else:
            downtime_hrs  = np.random.uniform(0.0, 1.5)     # Normal minor downtime

        cbg_produced = max(0.0, cbg_produced)

        # Power consumption scales with production (plus base load)
        base_power = 800.0   # kWh base load (agitators, controls, lighting, pumps)
        prod_power = (cbg_produced / CBG_TARGET_KG) * (POWER_DESIGN_KWH - base_power)
        if is_anomaly_a2:
            prod_power *= 0.7  # Partial compressor operation
        power_kwh  = max(0.0, base_power + prod_power + np.random.normal(0, 30))

        # Revenue: PSU pays for actual dispatched CBG
        penalty_factor = 1.0
        if is_anomaly_a2 and cbg_produced < 0.65 * CBG_TARGET_KG:
            penalty_factor = 0.95
        offtake_rev = round(cbg_produced * CBG_OFFTAKE_PRICE * penalty_factor, 2)

        records.append((
            op_date.isoformat(),
            round(biomass_fed, 3),
            round(biogas_yield_nm3, 2),
            round(ch4_pct, 2),
            round(cbg_produced, 2),
            round(power_kwh, 2),
            round(downtime_hrs, 2),
            offtake_rev,
            0.0,  # grid_export_units
        ))

    conn.executemany("""
        INSERT INTO digester_production_logs
            (production_date, tons_biomass_fed, biogas_yield_nm3, ch4_purity_pct,
             cbg_produced_kg, power_consumed_kwh, plant_downtime_hrs, offtake_revenue,
             grid_export_units)
        VALUES (?,?,?,?,?,?,?,?,?)
    """, records)
    conn.commit()
    print(f"[PRODUCTION] Inserted {len(records)} production log records (organic yield & purity modeled).\n")


# ---------------------------------------------------------------------------
# STEP 7: DAILY CASH TREASURY
# ---------------------------------------------------------------------------

def generate_cash_treasury(conn: sqlite3.Connection) -> None:
    """
    Generate 180-day daily cash treasury ledger.
    Feeds operational inflow from production logs.

    ANOMALY [A3] Days 145-165: PSU payment delay (receivables stretch 30→75 days)
    → Opening cash plunges; DSCR warning triggered.

    Working Capital model:
      - Inflow: CBG offtake revenue (30-day collection cycle, normally)
      - Outflow: Feedstock cost, Power cost, OPEX, monthly debt service
    """
    print("[TREASURY] Generating daily_cash_treasury ...")

    # Fetch production data
    prod_df = pd.read_sql_query(
        "SELECT production_date, offtake_revenue, cbg_produced_kg, "
        "power_consumed_kwh FROM digester_production_logs ORDER BY production_date",
        conn,
    )
    prod_df["production_date"] = pd.to_datetime(prod_df["production_date"])
    prod_df.set_index("production_date", inplace=True)

    # Fetch feedstock cost by day
    feed_df = pd.read_sql_query(
        "SELECT delivery_date, SUM(total_landed_cost) as daily_feedstock_cost "
        "FROM feedstock_inward_logs GROUP BY delivery_date ORDER BY delivery_date",
        conn,
    )
    feed_df["delivery_date"] = pd.to_datetime(feed_df["delivery_date"])
    feed_df.set_index("delivery_date", inplace=True)

    # Debt service: check monthly dates
    debt_df = pd.read_sql_query(
        "SELECT repayment_date, debt_service_total FROM debt_schedule ORDER BY repayment_date",
        conn,
    )
    debt_df["repayment_date"] = pd.to_datetime(debt_df["repayment_date"])
    debt_lookup = {}
    for _, row in debt_df.iterrows():
        # Match month-year to repayment date
        key = (row["repayment_date"].year, row["repayment_date"].month)
        debt_lookup[key] = row["debt_service_total"]

    # OPEX constants (INR/day) — scaled to 18T/day plant
    MISC_OPEX_PER_DAY   = 18_000   # Admin, lab chemicals, insurance, O&M reserves (larger plant)
    POWER_COST_RATE     = POWER_RATE_UNIT

    # Opening cash: INR 45 lakhs (DSR + working capital post-commissioning)
    opening_cash = 4_500_000.0
    COLLECTION_DAYS_NORMAL  = 30   # Normal PSU payment cycle
    COLLECTION_DAYS_ANOMALY = 75   # Anomaly A3 payment stretch

    # Build a revenue queue (FIFO) to simulate collection lag
    # Pre-seed with 30 days of historical receivables (plant was running before Day 1)
    # This prevents an artificial cash-dry period in the first 30 days
    revenue_queue = []  # List of (collection_date, amount)
    PRE_SEED_DAYS = 30
    avg_daily_rev = float(prod_df["offtake_revenue"].mean())
    for pre_day in range(PRE_SEED_DAYS, 0, -1):
        collect_on = OPS_START_DATE + timedelta(days=COLLECTION_DAYS_NORMAL - pre_day)
        pre_rev    = avg_daily_rev * np.random.uniform(0.90, 1.05)
        revenue_queue.append((collect_on, round(pre_rev, 2)))

    records     = []
    current_cash = opening_cash

    for day_idx in range(180):
        op_date = OPS_START_DATE + timedelta(days=day_idx)
        op_day  = day_idx + 1

        is_anomaly_a3 = (145 <= op_day <= 165)
        collection_days = COLLECTION_DAYS_ANOMALY if is_anomaly_a3 else COLLECTION_DAYS_NORMAL

        # Enqueue today's revenue for collection after lag
        if op_date in prod_df.index:
            todays_rev = prod_df.loc[op_date, "offtake_revenue"]
            collect_on = op_date + timedelta(days=collection_days)
            revenue_queue.append((collect_on, todays_rev))

        # Inflow: collect revenue that is due today
        operational_inflow = sum(amt for (cdate, amt) in revenue_queue if cdate == op_date)
        revenue_queue      = [(cd, a) for (cd, a) in revenue_queue if cd != op_date]

        # Feedstock outflow (paid on delivery, net 7 days)
        if op_date in feed_df.index:
            feedstock_outflow = feed_df.loc[op_date, "daily_feedstock_cost"]
        else:
            feedstock_outflow = 15_000.0  # Baseline daily feedstock spend

        # Power outflow
        if op_date in prod_df.index:
            power_kwh     = prod_df.loc[op_date, "power_consumed_kwh"]
        else:
            power_kwh     = 420.0
        power_outflow = round(power_kwh * POWER_COST_RATE, 2)

        # Misc OPEX
        misc_opex = round(MISC_OPEX_PER_DAY + np.random.normal(0, 300), 2)

        # Debt servicing (only on repayment date — 1st of month)
        month_key       = (op_date.year, op_date.month)
        debt_servicing  = 0.0
        if op_date.day == 1 and month_key in debt_lookup:
            debt_servicing = debt_lookup[month_key]

        # Compute closing cash
        closing_cash = (
            current_cash
            + operational_inflow
            - feedstock_outflow
            - power_outflow
            - misc_opex
            - debt_servicing
        )

        receivables_stretch = COLLECTION_DAYS_ANOMALY if is_anomaly_a3 else COLLECTION_DAYS_NORMAL

        records.append((
            op_date.isoformat(),
            round(current_cash, 2),
            round(operational_inflow, 2),
            round(feedstock_outflow, 2),
            round(power_outflow, 2),
            round(misc_opex, 2),
            round(debt_servicing, 2),
            receivables_stretch,
        ))

        # Roll forward
        current_cash = closing_cash

    conn.executemany("""
        INSERT INTO daily_cash_treasury
            (entry_date, opening_cash, operational_inflow, feedstock_outflow,
             power_outflow, misc_opex, debt_servicing, receivables_stretch_days)
        VALUES (?,?,?,?,?,?,?,?)
    """, records)
    conn.commit()
    print(f"[TREASURY] Inserted {len(records)} treasury records.\n")


# ---------------------------------------------------------------------------
# MAIN ORCHESTRATOR
# ---------------------------------------------------------------------------

def main():
    """Run the full data generation pipeline."""
    print("=" * 65)
    print(" BioPulse CBG Data Generator — Narmada Biofuels Pvt. Ltd.")
    print(" Seeding 3.0 TPD CBG facility analytics database")
    print("=" * 65)
    print()

    # Verify schema file exists
    if not os.path.exists(SCHEMA_PATH):
        raise FileNotFoundError(
            f"Schema file not found: {SCHEMA_PATH}\n"
            "Ensure schema.sql is in the same directory."
        )

    # Initialize database
    conn = init_database(DB_PATH, SCHEMA_PATH)

    try:
        # Seed all tables in dependency order
        generate_capex_milestones(conn)
        generate_debt_schedule(conn)
        generate_suppliers(conn)
        date_quality_map = generate_feedstock_and_yard(conn)
        generate_production_logs(conn, date_quality_map)
        generate_cash_treasury(conn)

        # Validation summary
        print("=" * 65)
        print(" DATA GENERATION COMPLETE — VALIDATION SUMMARY")
        print("=" * 65)
        tables = [
            "capex_milestones", "debt_schedule", "suppliers",
            "feedstock_inward_logs", "yard_inventory_aging",
            "digester_production_logs", "daily_cash_treasury",
        ]
        for t in tables:
            cnt = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"  {t:<35} → {cnt:>4} rows")

        print()
        print(f"  Database file: {os.path.abspath(DB_PATH)}")
        print("=" * 65)

        # Anomaly verification
        print("\n ANOMALY CLUSTER VERIFICATION:")
        a1 = conn.execute(
            "SELECT COUNT(*) FROM feedstock_inward_logs WHERE moisture_pct > 65 "
            "AND delivery_date BETWEEN '2024-02-09' AND '2024-02-21'"
        ).fetchone()[0]
        print(f"  [A1] High-moisture gate deliveries (Days 40-52):       {a1} records")

        a1_feed = conn.execute(
            "SELECT COUNT(*) FROM yard_inventory_aging y "
            "JOIN feedstock_inward_logs f ON y.receipt_id = f.receipt_id "
            "WHERE f.moisture_pct > 65 AND y.feed_date BETWEEN '2024-02-10' AND '2024-02-25'"
        ).fetchone()[0]
        print(f"  [A1] Compromised lots fed post-yard-lag (Days 41-56):  {a1_feed} records")

        a1_prod = conn.execute(
            "SELECT COUNT(*) FROM digester_production_logs "
            "WHERE cbg_produced_kg < 2550 AND plant_downtime_hrs < 5 "
            "AND production_date BETWEEN '2024-02-10' AND '2024-02-27'"
        ).fetchone()[0]
        print(f"  [A1] Organic yield drop in production (Days 41-57):    {a1_prod} days")

        a2 = conn.execute(
            "SELECT COUNT(*) FROM digester_production_logs WHERE plant_downtime_hrs > 10 "
            "AND production_date BETWEEN '2024-04-09' AND '2024-04-19'"
        ).fetchone()[0]
        print(f"  [A2] Compressor failure days (Days 100-110):           {a2} records")

        a3 = conn.execute(
            "SELECT COUNT(*) FROM daily_cash_treasury WHERE receivables_stretch_days > 30 "
            "AND entry_date BETWEEN '2024-05-24' AND '2024-06-13'"
        ).fetchone()[0]
        print(f"  [A3] Payment stretch days (Days 145-165):             {a3} records")
        print()

    except Exception as exc:
        conn.rollback()
        print(f"\n[ERROR] Data generation failed: {exc}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
