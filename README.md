# Vendor & AP Spend Analytics

An advanced-SQL + financial-analytics study of **accounts-payable and vendor management** for an
academic health system: *where do our AP dollars concentrate, and how clean and well-controlled is
the vendor master that feeds payments?*

> ⚠️ **Synthetic data.** Production financial data is confidential, so every row in this repo is
> **generated**, there are **no real vendors, dollar figures, or PII anywhere**. The dataset is
> modeled on the **schema of a Unit4 / Coda-style ERP** (the `oas_element` / `oas_grplist` /
> `oas_dochead` / `oas_docline` tables an AP team actually queries) and calibrated to **realistic
> AP distributions**, Pareto vendor spend, master-data hygiene rates, ~28-day payment timing.
> Two legal entities are modeled as `MSO` (medical service org) and `FDN` (foundation). The schema,
> business rules, and queries are production-faithful; only the contents are simulated. Reproducible
> from one seeded generator (`seed=42`).

**Stack:** SQL (SQLite; window functions, CTEs, INTERSECT, anti-joins) · Python (pandas, matplotlib) · Tableau Public / Power BI

---

## The business questions
1. **Spend concentration**: which vendors carry the AP budget? (strategic-sourcing target)
2. **Master-data hygiene**: how many active vendors are never-paid, foreign-address, cross-entity, or near-duplicates?
3. **Payment timing**: how fast do we pay, and how much clears the late-payment SLA?

## Key findings *(actual computed figures from the synthetic data)*

**Spend is heavily Pareto**
- The **top 10 vendors are 37.9% of AP spend**; the **top 1% (29 vendors) are 61.3%**.
- Only **82 of 2,876** paying vendors are needed to reach 80% of dollars; sourcing should rank by spend, not vendor count.

**The vendor master needs cleanup** *(of 3,504 active vendors)*
- **561 (16.0%) have never been paid**: dormant records, a master-data cleanup / fraud-surface concern.
- **207 (5.9%) have a foreign default address**: cross-border compliance review.
- **118 vendor codes are closed in one entity but still open in the other**: a payment-control gap.
- **52 near-duplicate name pairs**: double-payment risk.

**Payment timing is healthy on average, with a costly tail**
- Mean payment lag **~28.6 days**, but **17.0% of invoices clear the 45-day SLA** (8.2% clear 60 days), ≈ **$1.23B** of late-paid invoice value.

## Recommendations
1. **Run strategic sourcing on the top ~30 vendors first**: they carry 61% of spend.
2. **Execute a vendor-master cleanup sprint**: deactivate/merge the 561 never-paid records, resolve the 52 near-duplicate pairs, route the 207 foreign vendors through compliance.
3. **Reconcile the 118 cross-entity open/closed vendors** and add a periodic status-sync control.
4. **Attack the late-payment tail** to protect early-pay discounts and vendor relationships.

*(One-page write-up with the full reasoning: [`reports/insight_memo.md`](reports/insight_memo.md).)*

---

## Dataset at a glance
| | |
|---|---|
| Total paid AP spend (synthetic) | **$7,230,291,705** |
| AP transaction lines (`oas_docline`) | **90,231** (67,957 paid) |
| Vendor master records / distinct vendor codes | **4,630 / 3,552** |
| Active vendors | **3,504** |
| Legal entities | **2** (MSO, FDN) |
| Fiscal span | ~2.5 fiscal years (FY2024 P1 → FY2026 P6) |

## Schema (synthetic, mirrors a Unit4/Coda ERP)
- **`oas_element`**, element master: vendors (`elmlevel=3`, codes like `V0001`) and divisions (`elmlevel=2`, 4-digit codes). Carries `endyear`/`endperiod` (0 = open, nonzero = closed in that entity), `country`, `defaddr`.
- **`oas_grplist`**, vendor group membership (`XDEPT` + a category group: PHARMA, MEDDEV, LABSUP, …).
- **`oas_dochead`**, AP document headers (`doccode` like `AP…`, fiscal `yr`/`period`, `adddate`).
- **`oas_docline`**, AP transaction lines (`el3` vendor, `el2` division, `valuedoc`, `statpay` 89 = paid, `paydate`).

Full DDL with column notes: [`data/schema.sql`](data/schema.sql).

## Repo structure
```
data/        generate_data.py (seeded, calibrated), schema.sql, *.csv  -> data/vendor_ap.db
sql/         6 analysis queries (spend ranking, never-paid, foreign, cross-entity,
             hygiene scorecard, payment timing + near-dupes), CTEs / window fns / INTERSECT
notebook/    analysis.ipynb / analysis.py + figures/*.png
dashboards/  Tableau + Power BI build guides + export_extracts.py + extracts/*.csv
reports/     insight_memo.md
```

## The SQL (what each query answers)
| File | Business question | Techniques |
|------|-------------------|------------|
| `01_vendor_spend_ranking.sql` | Pareto: who carries the spend? | window fns (`RANK`, running `SUM OVER`), running % |
| `02_never_paid_active_vendors.sql` | active vendors with no AP lines | anti-join (`NOT EXISTS`) |
| `03_foreign_address_vendors.sql` | active foreign-address vendors | `defaddr=1`, `country<>'USA'`, spend join |
| `04_cross_entity_open_closed.sql` | closed in one entity, open in the other | CTE + **INTERSECT** |
| `05_vendor_hygiene_scorecard.sql` | one-query data-quality KPI tile | scalar subqueries, normalized-name match |
| `06_payment_timing_and_dupes.sql` | late-payment analysis + near-dupe detection | date math, `GROUP_CONCAT` (prod: `STRING_AGG`) |

## Charts
`notebook/figures/`: `spend_pareto.png`, `vendor_hygiene.png`, `spend_by_department.png`, `payment_timing.png`.

## Reproduce
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python data/generate_data.py          # -> data/*.csv + data/vendor_ap.db (deterministic, seed=42)
python notebook/analysis.py           # -> notebook/figures/*.png
python dashboards/export_extracts.py  # -> dashboards/extracts/*.csv
# run any query:  sqlite3 data/vendor_ap.db < sql/01_vendor_spend_ranking.sql
```

## Dashboards
- **Tableau Public, Vendor & AP Spend:** _link after publishing_ (build steps: [`dashboards/TABLEAU_GUIDE.md`](dashboards/TABLEAU_GUIDE.md)). _TODO: paste published URL._
- **Power BI, Vendor & AP Spend:** _link after publishing_ (build steps: [`dashboards/POWERBI_GUIDE.md`](dashboards/POWERBI_GUIDE.md)). _TODO: paste published URL._

---
*Part of [my portfolio](https://jknguyen-portfolio.vercel.app), case study: `/projects/vendor-ap-analytics`.*
