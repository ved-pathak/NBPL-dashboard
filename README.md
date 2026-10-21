# CBG Plant Production Funnel — Operational Loss & Financial Attribution Analytics

[![Dashboard-Streamlit](https://img.shields.io/badge/Dashboard-Live%20Streamlit-FF4B4B.svg)](http://localhost:8503)
[![SQL-ANSI%20SQLite3](https://img.shields.io/badge/SQL-Advanced%20Analytical%20Views-003B57.svg)](views.sql)
[![Analytics-Funnel%20Decomposition](https://img.shields.io/badge/Analytics-Sequential%20Funnel%20Decomposition-indigo.svg)](README.md#3-analytical-framework-sequential-funnel-decomposition)
[![Financials-SATAT%20Framework](https://img.shields.io/badge/Economics-SATAT%20Offtake%20Pricing-emerald.svg)](README.md#5-pricing-engine--financial-loss-decomposition)

An operational analytics system that models commercial compressed biogas (CBG) manufacturing as a continuous, mass-conserving production funnel. It translates raw operational telemetry into rupee-denominated financial leakage, identifies stage-specific bottlenecks, and isolates supplier-level unit economics.

---

## 1. The Business Problem & Analytical Objective

Commercial CBG plants operate under high fixed capital costs with tight operating margins. A design plant has a nameplate rating of **3,000 kg/day at 98% purity**, generating **₹3.33 lakh/day** (~₹111.02/kg ex-GST) under Indian Oil Marketing Company (OMC) offtake agreements (SATAT scheme). 

On most operating days, actual billed dispatch misses nameplate. When production falls short, leadership faces three critical questions:
1. **Where did production leak?** Was the shortfall driven by feedstock procurement, biological digestion, gas upgrading, or logistics?
2. **What did it cost?** How much loss was caused by missing physical kilograms versus purity discounts on delivered gas?
3. **Who or what is responsible?** Which supplier or plant unit triggered the loss, and what operational or contractual action should be taken?

```
Raw Material Supply ──► Moisture & Solids ──► Digester Biology ──► Purification Slip ──► Transit Delivery
   (Tonnage Deficit)      (Excess Water)        (CH4 Yield Drop)      (Tail-gas Loss)     (Metering / Pressure)
```

### The Analytical Challenge: Upstream Compounding
In continuous process manufacturing, naive aggregations produce **phantom blame**. For example, if raw material feed is 20% below requirement, the biological digester will produce less methane even if the bacteria are operating at peak efficiency. Evaluating each stage in isolation double-counts losses or accuses the wrong operational owner. 

This project solves this through a deterministic, mass-conserving **Sequential Loss Decomposition**.

---

## 2. Key Analytical Findings & Business Decisions

Over the analyzed 135-day operational window, the analytics engine surfaces actionable operational trade-offs:

### 1. Feedstock Quality Outweighs Volume
* **Finding**: Feedstock-related issues (moisture excess and supply deficits) account for over **55% of total rupee losses**, far outpacing mechanical or biological equipment downtime.
* **The "Cheaper Feed" Fallacy**: Vendor C supplies agricultural residue at ₹450/wet tonne (vs. Vendor A dung at ₹650/wet tonne). However, due to higher moisture variance and lower volatile solids yield, Vendor C's **effective landed cost per dry tonne** is significantly higher, eroding net operating margins.
* **Decision**: Transition procurement contracts from gross wet tonnage to **dry-matter indexation** with automatic penalty deductibles for moisture exceeding 85%.

### 2. Physical Deficit vs. Price Degradation Split
* **Finding**: Over 85% of total financial loss stems from **physical volume deficits** (valued at the full design tariff of ₹111.02/kg). Price penalties from sub-spec purity (<98%) represent ~15% of losses.
* **Decision**: Operational priority must focus on maximizing throughput and minimizing tail-gas slip rather than over-scrubbing gas to achieve marginal purity gains above 98%.

### 3. Transit & Logistics Accountability
* **Finding**: Transit leakage accounts for intermittent but severe revenue drops. On days where plant gate production was clean (>90% nameplate, <3% slip, >97.5% purity), delivery pressure fell below the contractual 200 bar threshold, causing OMC billing shortfalls.
* **Decision**: Enforce contractual SLA clauses against the logistics partner for cascade trailer pressure drops below 200 bar, preventing the plant from absorbing transport losses.

---

## 3. Analytical Framework: Sequential Funnel Decomposition

To ensure strict conservation of mass with **zero residual bucket**, the pipeline evaluates production sequentially through five non-overlapping stages:

```
[Design Nameplate: 3,000 kg]
       │
       ├──► 1. Supply Shortfall (Gross Biomass Tonnage Deficit)
       │
       ├──► 2. Moisture Penalty (Excess Water in Delivered Feed)
       │
       ├──► 3. Digester Biology (Methane Conversion Efficiency)
       │
       ├──► 4. Purification Slip (Methane Loss in Scrubbing Off-Gas)
       │
       └──► 5. Transit Discrepancy (Pressure Drop / Metering Gap)
       │
[Actual Billed Output: k5 kg]
```

### Funnel Walk Equations

Let $N = 3,000\text{ kg/day}$ (Nameplate Capacity). The model walks through intermediate virtual yields $k_0 \to k_5$:

| Stage | Efficiency Ratio | Virtual Yield ($k$) | Stage Loss Metric (kg) |
|---|---|---|---|
| **0. Nameplate** | Reference design | $k_0 = N$ | Base capacity |
| **1. Supply** | $\text{qty\_ratio} = \frac{\text{Feed Received}}{\text{Plant Design Need}}$ | $k_1 = N \times \text{qty\_ratio}$ | $\text{Loss}_{\text{supply}} = k_0 - k_1$ |
| **2. Moisture** | $\text{solids\_ratio} = \frac{\text{Dry Solids Fed}}{\text{Design Dry Solids}}$ | $k_2 = N \times \text{solids\_ratio}$ | $\text{Loss}_{\text{moisture}} = k_1 - k_2$ |
| **3. Digester** | $\text{dig\_eff} = \frac{\text{Actual }\text{CH}_4\text{ Produced}}{\text{Expected Yield from Solids Fed}}$ | $k_3 = N \times \text{solids\_ratio} \times \text{dig\_eff}$ | $\text{Loss}_{\text{digester}} = k_2 - k_3$ |
| **4. Purification** | $\text{pur\_eff} = \frac{1 - \text{Actual Slip}}{1 - \text{Design Slip}}$ | $k_4 = k_3 \times \text{pur\_eff} \equiv \text{CBG}_{\text{out}}$ | $\text{Loss}_{\text{purif}} = k_3 - k_4$ |
| **5. Transit** | $\text{transit\_eff} = \frac{\text{Billed kg}}{\text{Dispatched kg}}$ | $k_5 = \text{Billed}_{\text{kg}}$ | $\text{Loss}_{\text{transit}} = k_4 - k_5$ |

### Mathematical Proof of Exhaustive Decomposition
Because each stage loss is defined as $\text{Loss}_i = k_{i-1} - k_i$, summing the losses forms a telescoping series:
$$\sum_{i=1}^{5} \text{Loss}_i = (k_0 - k_1) + (k_1 - k_2) + (k_2 - k_3) + (k_3 - k_4) + (k_4 - k_5) \equiv k_0 - k_5 = N - \text{Billed}_{\text{kg}}$$
The decomposition is **exhaustive by construction**: 100% of the volume gap is accounted for across the 5 process stages with zero unexplained residual.

---

## 4. SQL Analytics Engine & Metric Derivations

The analytical layer is built purely in SQL views ([views.sql](file:///Users/vedpathak/my%20files/chemical_eng/The%20Btech%20Project/placement/New_project/cbg_analytics_v2/views.sql)), demonstrating key analytical engineering patterns:

### 1. Multi-Tier CTE Funnel Walk (`v_stage_losses`)
Structures raw data into logical processing layers (`base` $\to$ `ratios` $\to$ `walk`), isolating data extraction, ratio derivation, and sequential loss computation:
```sql
WITH base AS ( ... ),
ratios AS (
    SELECT *,
        rm_fed_t / plant_need_t                             AS qty_ratio,
        solids_fed_t / (plant_need_t * target_solids_frac) AS solids_ratio,
        ch4_in_kg / (solids_fed_t * design_ch4_yield)      AS dig_eff,
        (cbg_out_kg * design_purity / ch4_in_kg) / (1.0 - design_slip) AS pur_eff,
        billed_kg / cbg_out_kg                             AS transit_eff
    FROM base
),
walk AS (
    SELECT *,
        N                                    AS k0,
        N * qty_ratio                        AS k1,
        N * solids_ratio                     AS k2,
        N * solids_ratio * dig_eff           AS k3,
        N * solids_ratio * dig_eff * pur_eff AS k4,
        billed_kg                            AS k5
    FROM ratios
)
SELECT ... (k0 - k1) AS supply_loss_kg, (k1 - k2) AS moisture_loss_kg ... FROM walk;
```

### 2. Dual-Window Causal Isolation (`v_loss_daily`)
To prevent cross-variable confounding, root supplier attribution is decoupled by failure mode using dual window partitions:
```sql
vendor_trace AS (
    SELECT
        va.output_date, va.vendor, va.feed_date,
        ROW_NUMBER() OVER (PARTITION BY va.output_date ORDER BY va.supply_loss_kg_v DESC)   AS rank_supply,
        ROW_NUMBER() OVER (PARTITION BY va.output_date ORDER BY va.moisture_loss_kg_v DESC) AS rank_moisture
    FROM v_vendor_allocation va
)
...
-- Select culprit conditioned strictly on the diagnosed primary cause:
CASE WHEN pc.primary_cause = 'Supply shortfall'   THEN svt.vendor
     WHEN pc.primary_cause = 'Moisture / low solids' THEN mvt.vendor
     ELSE NULL END AS traced_vendor
```

### 3. Pro-Rata Upstream Cost Allocation (`v_vendor_allocation`)
Allocates daily plant-level losses back to individual suppliers proportionally based on their marginal contribution to the shortfall:
```sql
-- Vendor supply allocation: vendor's share of total daily volume shortfall
CASE WHEN sl.supply_loss_kg > 0 AND dt.total_shortfall > 0
     THEN sl.supply_loss_rs * ds.shortfall_v / dt.total_shortfall
     ELSE 0.0 END AS supply_loss_rs_v,

-- Vendor moisture allocation: vendor's share of excess water delivered
CASE WHEN sl.moisture_loss_kg > 0 AND mt.total_excess > 0
     THEN sl.moisture_loss_rs * me.excess_v / mt.total_excess
     ELSE 0.0 END AS moisture_loss_rs_v
```

### 4. Categorical Unpivoting & Ranked Pareto Distributions (`v_loss_causes`)
Transforms columnar losses into normalized rows via `UNION ALL` to evaluate cumulative loss curves and significance filters:
```sql
WITH unpivoted AS (
    SELECT output_date, 'Supply shortfall' AS cause, supply_loss_kg AS loss_kg, supply_loss_rs AS rs_loss FROM v_stage_losses
    UNION ALL
    SELECT output_date, 'Moisture / low solids', moisture_loss_kg, moisture_loss_rs FROM v_stage_losses
    UNION ALL
    SELECT output_date, 'Digester underperformance', digester_loss_kg, digester_loss_rs FROM v_stage_losses
    ...
)
SELECT *,
    ROW_NUMBER() OVER (PARTITION BY output_date ORDER BY rs_loss DESC) AS rank_by_rs,
    CASE WHEN rs_loss >= c.materiality_pct * c.nameplate_kg * p.design_price THEN 1 ELSE 0 END AS is_significant
FROM unpivoted;
```

---

## 5. Pricing Engine & Financial Loss Decomposition

Commercial contracts index revenue directly to gross calorific value (GCV), creating a variable price per kg based on delivered methane purity:

$$\text{slope} = \frac{\text{GCV} \times \text{Price}_{\text{MMBTU}}}{\rho_{\text{gas}}} \times \eta_{\text{correction}} = \frac{0.0376 \times 2110}{0.717} \times 0.95 \approx ₹105.12 \text{ / kg / unit purity}$$

$$\text{Price}(\text{purity}) = \text{slope} \times \text{purity} + \text{Compression Charge} = 105.12 \times \rho + 8.00$$

* **Benchmark Tariff (@ 98% Design Purity)**: $105.12 \times 0.98 + 8.00 =$ **₹111.02 / kg**
* **Financial Loss Separation**:
  $$\text{Total Financial Loss} = \underbrace{\sum_{i=1}^{5} \text{Loss}_i \times \text{Price}_{\text{design}}}_{\text{Physical Quantity Volume Losses}} + \underbrace{\text{Billed kg} \times (\text{Price}_{\text{design}} - \text{Price}_{\text{actual}})}_{\text{Price-Realization Purity Penalties}}$$
  This isolates whether cash flow drops are caused by missing volume or product quality discounts.

---

## 6. Supplier Analytics & Procurement Unit Economics

Raw material procurement evaluates 5 vendors across two material categories (Dairy Dung vs. Agri Residue).

### Landed Cost per Dry Tonne
Raw wet procurement price (₹/tonne) is an operational vanity metric. The actual economic value is determined by delivered dry matter:
$$\text{Landed Cost per Dry Tonne} = \frac{\sum \text{Tonnage} \times (\text{Base Price} + \text{Freight})}{\sum \text{Tonnage} \times (1 - \text{Moisture Fraction})}$$

```
Vendor A (Dung):  ₹650 price + ₹80 freight  @ 15% solids ──► ₹4,867 / dry tonne
Vendor B (Dung):  ₹600 price + ₹120 freight @ 13.5% solids ──► ₹5,333 / dry tonne  [Worst in Dung]
Vendor C (Agri):  ₹450 price + ₹60 freight  @ 15% solids ──► ₹3,400 / dry tonne
Vendor D (Agri):  ₹430 price + ₹90 freight  @ 15% solids ──► ₹3,467 / dry tonne
Vendor E (Agri):  ₹480 price + ₹50 freight  @ 15.5% solids ──► ₹3,419 / dry tonne [Best Value]
```

### Supplier Scorecard Rules
* **Reliability Score**: $\text{AVG}(\frac{\text{Actual Delivered Tonnage}}{\text{Contracted DCQ}})$.
* **Fulfillment Failure**: Count of days where delivery was $<90\%$ of contracted volume.
* **Top Performer**: Lowest landed cost per dry tonne among vendors meeting $\ge 95\%$ reliability.

---

## 7. Decision Dashboard & Operational Workflows

The Streamlit dashboard ([app.py](file:///Users/vedpathak/my%20files/chemical_eng/The%20Btech%20Project/placement/New_project/cbg_analytics_v2/app.py)) provides three operational interfaces:

1. **Executive Overview**:
   * Summary KPI ribbon tracking average production, % nameplate attainment, and volume vs. price penalty split.
   * Daily production time-series with 7-day rolling baseline and 90% threshold breaches.
   * Rupee loss waterfall bridging theoretical nameplate revenue to actual realized revenue across all 7 physical and purity factors.

2. **Daily Diagnostics & Root-Cause Trace**:
   * Complete 135-day audit table classifying daily operational status (`OK` vs. `Below 90%`).
   * Automated primary/secondary cause attribution with significance noise filtering (2% revenue floor).
   * Operational lineage mapping output days to historical feed dates and responsible supplier IDs.

3. **Supplier Scorecard & Portfolio Contribution**:
   * Ranked loss distribution curve with cumulative percentage tracking.
   * Stacked bar chart comparing supplier volume loss vs. excess moisture penalties.
   * Full procurement scorecard benchmarking landed dry cost against delivery reliability.

---

## 8. Technical Architecture & Setup

### Quickstart

```bash
# 1. Install requirements
pip install -r requirements.txt

# 2. Run structural validation suite (46 assertions)
python3 validate.py

# 3. Launch dashboard
streamlit run app.py
```
Dashboard runs locally at `http://localhost:8503` (or port assigned by Streamlit).

### Repository Structure
```
├── README.md             # Project documentation, analytical methodology, and SQL derivations
├── requirements.txt      # Dependencies: numpy, pandas, streamlit, plotly
├── schema.sql            # Star schema DDL (dim_vendor, fact tables, single-row config)
├── generate_data.py      # Probabilistic operational telemetry generator (180 feed / 135 output days)
├── views.sql             # Analytical SQL views (12-stage modular pipeline)
├── validate.py           # Automated structural testing suite (46 assertions)
└── app.py                # Streamlit operational dashboard
```

### Quality Assurance & Validation
`validate.py` executes **46 automated integrity checks** confirming:
* Exhaustive mass conservation identity: $\sum \text{Stage Losses} \equiv N - \text{Billed kg}$
* Financial balance identity: $\text{Total Rs Lost} \equiv \sum \text{Quantity Losses} + \text{Purity Penalties}$
* Dual-window causal isolation: 0 supplier attribution mismatches across all 135 days
* Range validations, feed consistency, and dynamic row-count assertions.

---

## License

Available under the [MIT License](LICENSE).
