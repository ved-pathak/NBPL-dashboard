"""
generate_data.py
Synthetic data generator for CBG Plant Production Funnel.

Generates 180 days of feed data and 135 days of output data (day 46–180).
Faults are drawn randomly from per-day probabilities — no predetermined
fault schedule. Each run with the same seed produces identical data.

Assumptions:
- All noise is Gaussian unless otherwise noted.
- Agri residue moisture treated same as dung (both have wet-material moisture).
- Vendor moisture_frac = 1 - solids_frac.
- Calibrated design_ch4_kg_per_t_solids is written back into config after computing.
"""

import sqlite3
import numpy as np
from datetime import date, timedelta
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "cbg.db")
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema.sql")

# ---------------------------------------------------------------------------
# Configuration (must match config table defaults)
# ---------------------------------------------------------------------------
START_DATE = date(2026, 8, 23)   # day 1
N_DAYS = 180
LAG_DAYS = 45
NAMEPLATE_KG = 3000.0
PLANT_NEED_T = 65.0
TARGET_SOLIDS_FRAC = 0.15
DESIGN_PURITY = 0.98
DESIGN_SLIP = 0.01
CH4_DENSITY = 0.717          # kg/nm3
DESIGN_CH4_FRAC = 0.55

# Calibrated yield: perfect feed inputs => exactly 3,000 kg output
DESIGN_CH4_IN_KG = NAMEPLATE_KG * DESIGN_PURITY / (1 - DESIGN_SLIP)
DESIGN_SOLIDS_AT_PLANT = PLANT_NEED_T * TARGET_SOLIDS_FRAC
DESIGN_CH4_KG_PER_T_SOLIDS = DESIGN_CH4_IN_KG / DESIGN_SOLIDS_AT_PLANT

# ---------------------------------------------------------------------------
# Vendor definitions
# ---------------------------------------------------------------------------
VENDORS = {
    "A": {"material": "dung",  "dcq_t": 7,  "price_per_t": 650, "freight_per_t": 80,
          "fill_mean": 1.00, "fill_std": 0.03, "moisture_mean": 0.850, "moisture_std": 0.005},
    "B": {"material": "dung",  "dcq_t": 7,  "price_per_t": 600, "freight_per_t": 120,
          "fill_mean": 0.93, "fill_std": 0.03, "moisture_mean": 0.865, "moisture_std": 0.005},
    "C": {"material": "agri",  "dcq_t": 20, "price_per_t": 450, "freight_per_t": 60,
          "fill_mean": 1.00, "fill_std": 0.03, "moisture_mean": 0.850, "moisture_std": 0.005},
    "D": {"material": "agri",  "dcq_t": 18, "price_per_t": 430, "freight_per_t": 90,
          "fill_mean": 0.97, "fill_std": 0.03, "moisture_mean": 0.850, "moisture_std": 0.005},
    "E": {"material": "agri",  "dcq_t": 18, "price_per_t": 480, "freight_per_t": 50,
          "fill_mean": 1.00, "fill_std": 0.03, "moisture_mean": 0.845, "moisture_std": 0.005},
}

# ---------------------------------------------------------------------------
# Random fault probabilities (per output day)
# These are independent draws — each day has a small chance of a fault.
# ---------------------------------------------------------------------------
FAULT_PROBS = {
    "digester_drop":   0.06,   # ~6% chance of digester yield drop on any output day
    "high_slip":       0.04,   # ~4% chance of high purifier slip
    "low_purity":      0.04,   # ~4% chance of low plant purity
    "transit_short":   0.03,   # ~3% chance of transit pressure/billing issue
}

# Feed-side faults (per feed day, per vendor)
FEED_FAULT_PROBS = {
    "moisture_spike":  0.03,   # ~3% chance per vendor per day of moisture spike
    "supply_short":    0.04,   # ~4% chance per vendor per day of short delivery
}


def day_date(day: int) -> str:
    """Convert 1-indexed day number to ISO date string."""
    return (START_DATE + timedelta(days=day - 1)).isoformat()


def main():
    rng = np.random.default_rng(42)

    # Remove existing DB so schema is clean
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")

    with open(SCHEMA_PATH) as f:
        conn.executescript(f.read())

    # -----------------------------------------------------------------------
    # 1. Populate dim_vendor
    # -----------------------------------------------------------------------
    conn.executemany(
        "INSERT INTO dim_vendor VALUES (?,?,?,?,?)",
        [(v, d["material"], d["dcq_t"], d["price_per_t"], d["freight_per_t"])
         for v, d in VENDORS.items()]
    )

    # -----------------------------------------------------------------------
    # 2. Generate fact_rm_receipt (N_DAYS x 5 vendors)
    #
    #    Feed-side faults are drawn randomly per vendor per day.
    # -----------------------------------------------------------------------
    receipts = []
    daily_received = {}    # feed_day -> {vendor: (qty, moisture)}
    fault_log_feed = []

    for day in range(1, N_DAYS + 1):
        daily_received[day] = {}
        for v, d in VENDORS.items():
            fill = float(rng.normal(d["fill_mean"], d["fill_std"]))
            fill = max(0.5, min(1.5, fill))
            moisture = float(rng.normal(d["moisture_mean"], d["moisture_std"]))
            moisture = max(0.70, min(0.97, moisture))

            qty_t = d["dcq_t"] * fill

            # Random moisture spike
            if rng.random() < FEED_FAULT_PROBS["moisture_spike"]:
                moisture = float(rng.normal(0.92, 0.003))
                moisture = max(0.91, min(0.94, moisture))
                fault_log_feed.append((day, v, "moisture_spike", moisture))

            # Random supply shortfall
            if rng.random() < FEED_FAULT_PROBS["supply_short"]:
                qty_t = d["dcq_t"] * float(rng.normal(0.20, 0.05))
                qty_t = max(d["dcq_t"] * 0.10, qty_t)
                fault_log_feed.append((day, v, "supply_short", qty_t))

            moisture = max(0.0, min(1.0, moisture))
            qty_t = max(0.01, qty_t)

            receipts.append((day_date(day), v, round(qty_t, 4), round(moisture, 5)))
            daily_received[day][v] = (qty_t, moisture)

    conn.executemany(
        "INSERT INTO fact_rm_receipt VALUES (?,?,?,?)", receipts
    )

    # -----------------------------------------------------------------------
    # 3. Generate fact_digester_feed (N_DAYS rows)
    # -----------------------------------------------------------------------
    feed_rows = []
    daily_feed = {}    # feed_day -> (rm_fed_t, solids_fed_t)

    for day in range(1, N_DAYS + 1):
        vendors_day = daily_received[day]
        received_t = sum(qty for qty, _ in vendors_day.values())

        # Capped at plant need
        rm_fed_t = min(received_t, PLANT_NEED_T)
        scale = rm_fed_t / received_t if received_t > 0 else 1.0

        # Solids: each vendor contributes qty_v * scale * (1 - moisture_v)
        solids_fed_t = sum(
            qty * scale * (1.0 - m) for qty, m in vendors_day.values()
        )

        daily_feed[day] = (rm_fed_t, solids_fed_t)
        feed_rows.append((day_date(day), round(rm_fed_t, 4), round(solids_fed_t, 5)))

    conn.executemany(
        "INSERT INTO fact_digester_feed VALUES (?,?,?)", feed_rows
    )

    # -----------------------------------------------------------------------
    # 4. Generate downstream tables for output days (LAG_DAYS+1 to N_DAYS)
    #
    #    Process faults are drawn randomly per output day.
    # -----------------------------------------------------------------------
    first_output_day = LAG_DAYS + 1
    last_output_day = N_DAYS

    digester_rows = []
    purification_rows = []
    billing_rows = []
    fault_log_output = []

    for out_day in range(first_output_day, last_output_day + 1):
        f_day = out_day - LAG_DAYS         # feed day providing biomass
        rm_fed_t, solids_fed_t = daily_feed[f_day]

        # ---- Digester output ----
        ch4_frac = float(rng.normal(DESIGN_CH4_FRAC, 0.005))
        ch4_frac = max(0.48, min(0.60, ch4_frac))
        yield_noise = float(rng.normal(1.0, 0.010))
        yield_noise = max(0.92, min(1.08, yield_noise))

        # Random digester drop
        if rng.random() < FAULT_PROBS["digester_drop"]:
            yield_noise *= float(rng.normal(0.78, 0.03))
            ch4_frac = float(rng.normal(0.50, 0.005))
            ch4_frac = max(0.47, min(0.53, ch4_frac))
            fault_log_output.append((out_day, "digester_drop", yield_noise))

        # ch4_kg produced by digester
        design_ch4_from_solids = solids_fed_t * DESIGN_CH4_KG_PER_T_SOLIDS
        ch4_kg_actual = design_ch4_from_solids * yield_noise

        # Backcompute biogas_nm3 from ch4_kg and ch4_frac
        biogas_nm3 = ch4_kg_actual / (ch4_frac * CH4_DENSITY)

        digester_rows.append((
            day_date(out_day),
            round(biogas_nm3, 2),
            round(ch4_frac, 5),
        ))

        # ---- Purification ----
        ch4_in_kg = biogas_nm3 * ch4_frac * CH4_DENSITY   # matches digester

        # Slip and purity (normal)
        slip = float(rng.normal(DESIGN_SLIP, 0.003))
        slip = max(0.003, min(0.05, slip))
        purity = float(rng.normal(DESIGN_PURITY, 0.002))
        purity = max(0.93, min(1.0, purity))

        # Random high slip
        if rng.random() < FAULT_PROBS["high_slip"]:
            slip = float(rng.normal(0.06, 0.005))
            slip = max(0.045, min(0.08, slip))
            fault_log_output.append((out_day, "high_slip", slip))

        # Random low purity
        if rng.random() < FAULT_PROBS["low_purity"]:
            purity = float(rng.normal(0.94, 0.003))
            purity = max(0.93, min(0.96, purity))
            fault_log_output.append((out_day, "low_purity", purity))

        # CBG output
        cbg_out_kg = ch4_in_kg * (1.0 - slip) / DESIGN_PURITY

        purification_rows.append((
            day_date(out_day),
            round(ch4_in_kg, 3),
            round(cbg_out_kg, 3),
            round(purity, 5),
        ))

        # ---- OMC Billing ----
        transit_loss_frac = float(rng.normal(0.002, 0.0005))   # 0.1-0.3%
        transit_loss_frac = max(0.001, min(0.005, transit_loss_frac))
        billed_kg = cbg_out_kg * (1.0 - transit_loss_frac)
        billed_purity = purity - float(rng.normal(0.001, 0.0005))
        billed_purity = max(0.92, min(1.0, billed_purity))
        pressure = float(rng.normal(210, 5))
        pressure = max(195, min(230, pressure))

        # Random transit/billing issue
        if rng.random() < FAULT_PROBS["transit_short"]:
            pressure = float(rng.normal(160, 5))
            pressure = max(145, min(175, pressure))
            billed_kg = cbg_out_kg * float(rng.normal(0.93, 0.005))
            billed_kg = max(cbg_out_kg * 0.88, billed_kg)
            billed_purity = purity - float(rng.normal(0.008, 0.002))
            billed_purity = max(0.92, min(1.0, billed_purity))
            fault_log_output.append((out_day, "transit_short", pressure))

        billing_rows.append((
            day_date(out_day),
            round(billed_kg, 3),
            round(billed_purity, 5),
            round(pressure, 2),
        ))

    conn.executemany(
        "INSERT INTO fact_digester_output VALUES (?,?,?)", digester_rows
    )
    conn.executemany(
        "INSERT INTO fact_purification VALUES (?,?,?,?)", purification_rows
    )
    conn.executemany(
        "INSERT INTO fact_omc_billing VALUES (?,?,?,?)", billing_rows
    )

    # -----------------------------------------------------------------------
    # 5. Write calibrated design_ch4_kg_per_t_solids back into config
    # -----------------------------------------------------------------------
    cur = conn.execute("""
        UPDATE config SET design_ch4_kg_per_t_solids = ?
    """, (round(DESIGN_CH4_KG_PER_T_SOLIDS, 6),))
    if cur.rowcount == 0:
        conn.execute("""
            INSERT INTO config (design_ch4_kg_per_t_solids) VALUES (?)
        """, (round(DESIGN_CH4_KG_PER_T_SOLIDS, 6),))

    # -----------------------------------------------------------------------
    # 6. Load SQL views into database
    # -----------------------------------------------------------------------
    views_path = os.path.join(os.path.dirname(__file__), "views.sql")
    if os.path.exists(views_path):
        with open(views_path, "r") as vf:
            conn.executescript(vf.read())

    conn.commit()
    conn.close()

    n_output_days = last_output_day - first_output_day + 1
    print(f"Database written to: {DB_PATH}")
    print(f"design_ch4_kg_per_t_solids = {DESIGN_CH4_KG_PER_T_SOLIDS:.6f}")
    print(f"Receipts: {N_DAYS * len(VENDORS)}, Feed: {N_DAYS}, Output/Purification/Billing: {n_output_days} each")
    print(f"\nFeed-side faults injected: {len(fault_log_feed)}")
    for day, vendor, ftype, val in fault_log_feed[:10]:
        print(f"  Day {day}, Vendor {vendor}: {ftype} ({val:.4f})")
    if len(fault_log_feed) > 10:
        print(f"  ... and {len(fault_log_feed) - 10} more")
    print(f"\nOutput-side faults injected: {len(fault_log_output)}")
    for day, ftype, val in fault_log_output[:10]:
        print(f"  Day {day}: {ftype} ({val:.4f})")
    if len(fault_log_output) > 10:
        print(f"  ... and {len(fault_log_output) - 10} more")


if __name__ == "__main__":
    main()
