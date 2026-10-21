"""
validate.py
Data-quality and structural-integrity checks for CBG analytics.
Prints PASS/FAIL per check. Exits non-zero on any failure.

These checks test STRUCTURAL PROPERTIES of the data and views — not
specific fault outcomes. They verify that the pipeline is internally
consistent regardless of what the random data generator produces.

Run after generate_data.py (which also loads views.sql).
"""

import sqlite3
import sys
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "cbg.db")

PASS = "PASS"
FAIL = "FAIL"

passed_count = 0
failed_count = 0
failures = []


def check(name: str, condition: bool, detail: str = ""):
    global passed_count, failed_count
    status = PASS if condition else FAIL
    suffix = f"  [{detail}]" if detail else ""
    print(f"  [{status}] {name}{suffix}")
    if condition:
        passed_count += 1
    else:
        failed_count += 1
        failures.append(name)


def section(title: str):
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print("=" * 60)


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # Load config for dynamic row-count expectations
    cfg = dict(conn.execute("SELECT * FROM config").fetchone())
    n_vendors = conn.execute("SELECT COUNT(*) FROM dim_vendor").fetchone()[0]

    # Infer N_DAYS from fact_digester_feed (total feed days)
    n_feed_days = conn.execute("SELECT COUNT(*) FROM fact_digester_feed").fetchone()[0]
    lag_days = cfg["lag_days"]
    expected_output_days = n_feed_days - lag_days  # output days = total - lag
    expected_receipts = n_feed_days * n_vendors

    # -----------------------------------------------------------------------
    # SECTION 1: ROW COUNTS (dynamic, not hardcoded)
    # -----------------------------------------------------------------------
    section("Row Counts")

    def count(table):
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    actual_receipts = count("fact_rm_receipt")
    check(f"fact_rm_receipt: {expected_receipts} rows (days × vendors)",
          actual_receipts == expected_receipts,
          f"got {actual_receipts}")

    check(f"fact_digester_feed: {n_feed_days} rows",
          count("fact_digester_feed") == n_feed_days,
          f"got {count('fact_digester_feed')}")

    actual_output = count("fact_digester_output")
    check(f"fact_digester_output: {expected_output_days} rows",
          actual_output == expected_output_days,
          f"got {actual_output}")

    check(f"fact_purification: {expected_output_days} rows",
          count("fact_purification") == expected_output_days,
          f"got {count('fact_purification')}")

    check(f"fact_omc_billing: {expected_output_days} rows",
          count("fact_omc_billing") == expected_output_days,
          f"got {count('fact_omc_billing')}")

    # -----------------------------------------------------------------------
    # SECTION 2: DATA QUALITY - NO NULLS
    # -----------------------------------------------------------------------
    section("NULL Checks in Fact Tables")

    null_checks = [
        ("fact_rm_receipt",     ["receipt_date", "vendor", "qty_t", "moisture_frac"]),
        ("fact_digester_feed",  ["feed_date", "rm_fed_t", "solids_fed_t"]),
        ("fact_digester_output",["output_date", "biogas_nm3", "ch4_frac"]),
        ("fact_purification",   ["output_date", "ch4_in_kg", "cbg_out_kg", "purity_frac"]),
        ("fact_omc_billing",    ["output_date", "billed_kg", "billed_purity_frac", "delivery_pressure_bar"]),
    ]
    for table, cols in null_checks:
        for col in cols:
            n = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {col} IS NULL"
            ).fetchone()[0]
            check(f"{table}.{col} has no NULLs", n == 0, f"{n} NULLs found")

    # -----------------------------------------------------------------------
    # SECTION 3: VALUE-RANGE CHECKS
    # -----------------------------------------------------------------------
    section("Value Range Checks")

    out_of_range = conn.execute(
        "SELECT COUNT(*) FROM fact_rm_receipt WHERE moisture_frac < 0 OR moisture_frac > 1"
    ).fetchone()[0]
    check("moisture_frac in [0,1]", out_of_range == 0, f"{out_of_range} rows out of range")

    out_purity = conn.execute(
        "SELECT COUNT(*) FROM fact_purification WHERE purity_frac < 0.9 OR purity_frac > 1"
    ).fetchone()[0]
    check("purity_frac in [0.9,1]", out_purity == 0, f"{out_purity} rows out of range")

    out_bpurity = conn.execute(
        "SELECT COUNT(*) FROM fact_omc_billing WHERE billed_purity_frac < 0.9 OR billed_purity_frac > 1"
    ).fetchone()[0]
    check("billed_purity_frac in [0.9,1]", out_bpurity == 0, f"{out_bpurity} rows out of range")

    positive_qty = conn.execute(
        "SELECT COUNT(*) FROM fact_rm_receipt WHERE qty_t <= 0"
    ).fetchone()[0]
    check("qty_t > 0 for all receipts", positive_qty == 0, f"{positive_qty} non-positive rows")

    positive_biogas = conn.execute(
        "SELECT COUNT(*) FROM fact_digester_output WHERE biogas_nm3 <= 0"
    ).fetchone()[0]
    check("biogas_nm3 > 0 for all output days", positive_biogas == 0, f"{positive_biogas} non-positive rows")

    # -----------------------------------------------------------------------
    # SECTION 4: FEED CONSISTENCY
    # -----------------------------------------------------------------------
    section("Feed Consistency: rm_fed_t = min(received, plant_need_t)")

    inconsistent = conn.execute("""
        WITH daily_rcvd AS (
            SELECT receipt_date, SUM(qty_t) AS received_t
            FROM fact_rm_receipt
            GROUP BY receipt_date
        )
        SELECT COUNT(*) FROM daily_rcvd dr
        JOIN fact_digester_feed f ON f.feed_date = dr.receipt_date
        CROSS JOIN config c
        WHERE ABS(f.rm_fed_t - MIN(dr.received_t, c.plant_need_t)) > 0.001
    """).fetchone()[0]
    check(f"rm_fed_t = min(received, plant_need_t) for all {n_feed_days} days",
          inconsistent == 0, f"{inconsistent} inconsistent rows")

    # -----------------------------------------------------------------------
    # SECTION 5: CH4 CONSISTENCY
    # -----------------------------------------------------------------------
    section("CH4 Consistency: ch4_in_kg within 0.5% of biogas × ch4_frac × density")

    ch4_inconsistent = conn.execute("""
        SELECT COUNT(*) FROM fact_purification p
        JOIN fact_digester_output o ON o.output_date = p.output_date
        CROSS JOIN config c
        WHERE ABS(p.ch4_in_kg - o.biogas_nm3 * o.ch4_frac * c.ch4_density_kg_per_nm3)
              / (o.biogas_nm3 * o.ch4_frac * c.ch4_density_kg_per_nm3) > 0.005
    """).fetchone()[0]
    check("ch4_in_kg within 0.5% of computed value", ch4_inconsistent == 0,
          f"{ch4_inconsistent} rows out of tolerance")

    # -----------------------------------------------------------------------
    # SECTION 6: STAGE-LOSS DECOMPOSITION IDENTITY (all output days)
    #
    # This tests that the five stage losses sum to (N - billed_kg).
    # This is an algebraic identity by construction — it confirms the
    # view SQL implements the funnel formulas correctly, NOT that the
    # data has any particular quality.
    # -----------------------------------------------------------------------
    section("Stage-Loss Identity: sum(5 losses) ≡ N − billed_kg  (tol 0.01 kg)")

    recon_kg = conn.execute("""
        SELECT COUNT(*) FROM v_stage_losses
        WHERE ABS(supply_loss_kg + moisture_loss_kg + digester_loss_kg
                  + purification_loss_kg + transit_loss_kg
                  - (N - billed_kg)) > 0.01
    """).fetchone()[0]
    check(f"kg losses decompose correctly for all {expected_output_days} days",
          recon_kg == 0, f"{recon_kg} days fail identity check")

    # -----------------------------------------------------------------------
    # SECTION 7: RUPEE DECOMPOSITION IDENTITY (all output days)
    # -----------------------------------------------------------------------
    section("Rs Identity: total_rs_lost ≡ sum of all 7 Rs components  (tol Rs 1)")

    recon_rs = conn.execute("""
        SELECT COUNT(*) FROM v_stage_losses
        WHERE ABS(total_rs_lost
                  - (supply_loss_rs + moisture_loss_rs + digester_loss_rs
                     + purification_loss_rs + transit_qty_loss_rs
                     + purity_plant_loss_rs + purity_transit_loss_rs)) > 1.0
    """).fetchone()[0]
    check(f"Rs losses decompose correctly for all {expected_output_days} days",
          recon_rs == 0, f"{recon_rs} days fail Rs identity check")

    # -----------------------------------------------------------------------
    # SECTION 8: PRICE FORMULA CHECK
    # -----------------------------------------------------------------------
    section("Price Check: v_price formula is self-consistent")

    price_row = conn.execute(
        "SELECT slope, design_price, compression_charge_per_kg, design_purity FROM v_price"
    ).fetchone()
    # design_price should equal slope * design_purity + compression
    expected_dp = price_row["slope"] * price_row["design_purity"] + price_row["compression_charge_per_kg"]
    dp_ok = abs(price_row["design_price"] - expected_dp) < 0.01
    check("design_price = slope × design_purity + compression_charge",
          dp_ok, f"expected {expected_dp:.2f}, got {price_row['design_price']:.2f}")

    check("slope > 0 (positive price per unit purity)",
          price_row["slope"] > 0, f"got {price_row['slope']:.2f}")

    # -----------------------------------------------------------------------
    # SECTION 9: VIEW OUTPUT COUNTS
    # -----------------------------------------------------------------------
    section("View Output Row Counts")

    view_counts = {
        "v_stage_losses":     expected_output_days,
        "v_loss_daily":       expected_output_days,
        "v_daily_trend":      expected_output_days,
        "v_loss_causes":      expected_output_days * 7,   # 7 causes per day
        "v_window_vendors":   n_vendors,
        "v_vendor_summary":   n_vendors,
        "v_headline_summary": 1,
    }
    for view_name, expected in view_counts.items():
        actual = count(view_name)
        check(f"{view_name}: {expected} rows", actual == expected, f"got {actual}")

    # -----------------------------------------------------------------------
    # SECTION 10: DIAGNOSTIC NOTE INTEGRITY
    # -----------------------------------------------------------------------
    section("Diagnostic Note Integrity")

    null_empty = conn.execute("""
        SELECT COUNT(*) FROM v_loss_daily
        WHERE diagnostic_note IS NULL OR TRIM(diagnostic_note) = ''
    """).fetchone()[0]
    check("diagnostic_note has no NULL or empty values", null_empty == 0,
          f"{null_empty} invalid rows found")

    # Every row should have a primary cause (either a named cause or 'Within normal variation')
    no_primary = conn.execute("""
        SELECT COUNT(*) FROM v_loss_daily
        WHERE primary_cause IS NULL OR TRIM(primary_cause) = ''
    """).fetchone()[0]
    check("primary_cause populated for all output days", no_primary == 0,
          f"{no_primary} rows with no primary cause")

    # -----------------------------------------------------------------------
    # SECTION 11: VENDOR ALLOCATION CONSISTENCY
    # -----------------------------------------------------------------------
    section("Vendor Allocation Consistency")

    # Per output day: sum of vendor supply allocations ≈ total supply loss
    alloc_check = conn.execute("""
        WITH vendor_sums AS (
            SELECT output_date,
                   SUM(supply_loss_kg_v)  AS sum_supply_alloc,
                   SUM(moisture_loss_kg_v) AS sum_moisture_alloc
            FROM v_vendor_allocation
            GROUP BY output_date
        )
        SELECT COUNT(*) FROM vendor_sums vs
        JOIN v_stage_losses sl ON sl.output_date = vs.output_date
        WHERE (sl.supply_loss_kg > 0 AND ABS(vs.sum_supply_alloc - sl.supply_loss_kg) > 0.1)
           OR (sl.moisture_loss_kg > 0 AND ABS(vs.sum_moisture_alloc - sl.moisture_loss_kg) > 0.1)
    """).fetchone()[0]
    check("Vendor allocations sum to stage totals (supply + moisture)",
          alloc_check == 0, f"{alloc_check} days with allocation mismatch")

    # -----------------------------------------------------------------------
    # SECTION 12: VENDOR ATTRIBUTION INTEGRITY (Supply vs Moisture Separation)
    # -----------------------------------------------------------------------
    section("Vendor Attribution Integrity")

    supply_attr_errors = conn.execute("""
        WITH top_supply AS (
            SELECT output_date, vendor,
                   ROW_NUMBER() OVER (PARTITION BY output_date ORDER BY supply_loss_kg_v DESC) AS rn
            FROM v_vendor_allocation
        )
        SELECT COUNT(*)
        FROM v_loss_daily ld
        JOIN top_supply ts ON ts.output_date = ld.output_date AND ts.rn = 1
        WHERE ld.primary_cause = 'Supply shortfall'
          AND ld.traced_vendor != ts.vendor
    """).fetchone()[0]
    check("traced_vendor for Supply shortfall matches highest supply-shortfall vendor",
          supply_attr_errors == 0, f"{supply_attr_errors} attribution mismatches found")

    moisture_attr_errors = conn.execute("""
        WITH top_moisture AS (
            SELECT output_date, vendor,
                   ROW_NUMBER() OVER (PARTITION BY output_date ORDER BY moisture_loss_kg_v DESC) AS rn
            FROM v_vendor_allocation
        )
        SELECT COUNT(*)
        FROM v_loss_daily ld
        JOIN top_moisture tm ON tm.output_date = ld.output_date AND tm.rn = 1
        WHERE ld.primary_cause = 'Moisture / low solids'
          AND ld.traced_vendor != tm.vendor
    """).fetchone()[0]
    check("traced_vendor for Moisture matches highest moisture-loss vendor",
          moisture_attr_errors == 0, f"{moisture_attr_errors} attribution mismatches found")

    # -----------------------------------------------------------------------
    # SECTION 13: BASIC STATISTICS (informational, not pass/fail)
    # -----------------------------------------------------------------------
    section("Summary Statistics (informational)")

    stats = conn.execute("""
        SELECT
            ROUND(AVG(cbg_out_kg), 1) AS avg_prod,
            ROUND(MIN(cbg_out_kg), 1) AS min_prod,
            ROUND(MAX(cbg_out_kg), 1) AS max_prod,
            SUM(CASE WHEN cbg_out_kg < 0.9 * N THEN 1 ELSE 0 END) AS days_below_90,
            COUNT(*) AS total_days
        FROM v_stage_losses
    """).fetchone()
    print(f"\n  Output days: {stats['total_days']}")
    print(f"  Avg production: {stats['avg_prod']} kg/day")
    print(f"  Range: [{stats['min_prod']}, {stats['max_prod']}] kg/day")
    print(f"  Days below 90% nameplate: {stats['days_below_90']}")

    cause_dist = conn.execute("""
        SELECT primary_cause, COUNT(*) AS n_days
        FROM v_loss_daily
        GROUP BY primary_cause
        ORDER BY n_days DESC
    """).fetchall()
    print(f"\n  Primary cause distribution:")
    for row in cause_dist:
        print(f"    {row['primary_cause']}: {row['n_days']} days")

    # -----------------------------------------------------------------------
    # SUMMARY
    # -----------------------------------------------------------------------
    section("SUMMARY")
    total = passed_count + failed_count

    if failures:
        print(f"\n  FAILED CHECKS ({failed_count} of {total}):")
        for f in failures:
            print(f"    - {f}")
        print(f"\n  Result: FAIL ({failed_count} checks failed)")
        sys.exit(1)
    else:
        print(f"\n  All {passed_count} checks PASSED.")
        sys.exit(0)


if __name__ == "__main__":
    main()
