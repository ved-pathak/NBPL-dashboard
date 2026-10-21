# CBG Plant Production Loss Analytics

CBG Plant Production Loss Analytics: where a 3 TPD biogas plant lost output versus nameplate, what it cost in rupees, and which stage or vendor caused it.

The data is synthetic, generated with random faults and noise for demonstration.

## Funnel

```
Supply -> Moisture/solids -> Digester -> Purification -> Transit/billing
```

At each stage, loss is the drop in output potential from that stage's defect: delivered tonnage below plant need, solids below target fraction, methane yield below design from the solids fed, gas lost in purifier slip, or dispatched gas not billed by the off-taker.

## How the loss is split

The sequential walk steps from nameplate capacity down to billed output:
`nameplate -> after supply -> after moisture -> after digester -> after purification -> billed`.
Each stage loss is the drop from one step to the next, so the five stage losses add up to nameplate minus billed kg.

The split depends on the order (upstream first). That is a modelling choice, not a measurement: evaluating supply before moisture means missing tonnage is blamed on supply, and only the remaining received feed is judged on moisture.

Financial loss is valued as kg lost times the design price per kg, plus separate price losses for purity deficits at the plant gate and in transit.

Price formula: `price/kg = slope x purity + compression charge`, yielding Rs 111.02/kg at 98% design purity (about Rs 3.33 lakh/day at 3,000 kg nameplate), derived from the pricing sheet (`slope = GCV x price_per_mmbtu / density x 0.95 = 105.12`).

## The 45-day lag

Feed received on day D shows up in digester output on day D+45, implemented once in `v_day_map` using `lag_days` from `config`. Feed problems (supply shortfall, high moisture) are traced back through this lag to the originating feed date and vendor. Digester, purification, and transit problems are treated as same-day events and have no vendor attribution. The 45-day lag is a fixed shift for simplicity; a real digester would smear the effect over several days.

## Vendor scorecard

Summary across all 180 feed days from `v_vendor_summary`:

| Vendor | Material | Landed cost (Rs/dry t) | Reliability score | Days < 90% DCQ | Avg moisture | Rank in material |
|:---:|:---:|---:|---:|---:|---:|:---:|
| C | agri | 3,475.94 | 0.9587 | 9 | 85.3% | 1 |
| E | agri | 3,494.50 | 0.9749 | 6 | 84.8% | 2 |
| D | agri | 3,500.52 | 0.9408 | 10 | 85.1% | 3 |
| A | dung | 4,893.91 | 0.9459 | 12 | 85.1% | 1 |
| B | dung | 5,339.65 | 0.9117 | 30 | 86.5% | 2 |

Landed cost per dry tonne = `sum(qty x (price + freight)) / sum(qty x (1 - moisture))`. Reliability = `average(qty / DCQ)`.

Best vendor is the lowest dry cost among vendors with reliability >= 95% (the config threshold). In agri, Vendor C is best (Rs 3,475.94/dry t, 95.9% reliability). In dung, Vendor A is cheapest (Rs 4,893.91/dry t) but has 94.6% reliability, so neither dung vendor meets the 95% reliability threshold. Vendors are compared only within the same material.

## What the seeded data shows

Over the 135 output days (average production 2,828.9 kg/day, or 94.3% of nameplate), 69 days operate within normal variation, while 35 days fall below 90% of nameplate. Total loss across all 135 days is Rs 28.08 lakh, comprising Rs 27.09 lakh in quantity losses and Rs 0.99 lakh in purity price losses.

These results follow directly from the random faults injected in `generate_data.py`; the point is that the loss attribution isolates each stage. By primary cause across the 135 days:
- Within normal variation: 69 days
- Moisture / low solids: 25 days (Rs 6.91 lakh loss, 24.6% of Rs lost)
- Supply shortfall: 16 days (Rs 9.05 lakh loss, 32.2% of Rs lost)
- Digester underperformance: 16 days (Rs 8.88 lakh loss, 31.6% of Rs lost)
- Purification methane slip: 4 days (Rs 0.81 lakh loss, 2.9% of Rs lost)
- Transit pressure loss: 3 days (Rs 1.44 lakh loss, 5.1% of Rs lost)
- Low purity at plant gate: 2 days (Rs 0.55 lakh loss, 2.0% of Rs lost)

## Dashboard

The Streamlit app (`app.py`) has three pages:
- Overview: summary cards, daily production vs nameplate, and a rupee waterfall of stage losses.
- Daily Detail: 135-day table with primary and secondary cause, traced vendor, and loss components.
- Aggregate & Vendors: ranked cause totals, vendor loss contributions, and the vendor scorecard.

## Run it

```bash
pip install -r requirements.txt
python generate_data.py
python validate.py
streamlit run app.py
```

`generate_data.py` creates `cbg.db` (180 feed days, 135 output days) and loads `views.sql`. `validate.py` runs 46 integrity tests. `app.py` serves the dashboard.

## Validation

`validate.py` runs 46 checks against `cbg.db`. These fall into two groups:
- Identity checks: five stage losses sum to nameplate minus billed kg; seven rupee loss components sum to total Rs lost; price view is internally consistent.
- Data integrity: row counts match day calculations; no nulls in fact tables; physical ranges valid; feed fed equals minimum of receipts and plant need; vendor allocations sum to stage totals; and traced vendor matches the highest-shortfall vendor for that cause.

## Assumptions and limits

- Vendors, prices, fill rates, and moisture values are synthetic.
- Design yield is calibrated so perfect feed gives exactly 3,000 kg.
- Purity affects price only, not kg output.
- Correction factor is constant 0.95; price per MMBTU is 2110.
- Delivery pressure minimum (200 bar), 90% production target, 3% slip limit, and 2% materiality threshold are assumptions in the `config` table.
- Agri residue is treated as wet material at the same 15% solids target as dung.
- The 45-day lag is a fixed shift (see section 4).
- Attribution order is an upstream-first modelling choice (see section 3).
