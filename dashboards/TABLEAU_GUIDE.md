# Tableau Public build guide — "Vendor & AP Spend: Concentration, Hygiene & Timing"

**Goal:** one interactive Tableau Public dashboard an AP / procurement lead could use to
target sourcing, clean the vendor master, and tighten payment timing.
**Time:** ~90 min. **Cost:** free. All datasets are pre-aggregated in `dashboards/extracts/`
(run `python dashboards/export_extracts.py` first) — no pivoting needed. Connect the raw
`../data/*.csv` instead if you want to show the wrangling.

> All figures are **synthetic**, modeled on a Unit4/Coda-style ERP schema. Keep the
> footer disclaimer below on the published dashboard.

## 0. Setup
Download **Tableau Public** (free), create an account, **Connect → Text file** for each CSV below.

## 1. Worksheets

| # | Sheet | Data source | Build |
|---|-------|-------------|-------|
| A | **Vendor spend Pareto** (headline) | `01_vendor_spend_ranking.csv` | Filter to `spend_rank <= 20`. Bars: Columns `vendor_name` (sort by `total_spend` desc), Rows `total_spend`. Add a second axis line on `running_pct_of_total`; dual-axis, **do not** synchronize (different scales), right axis 0–100%. Add a reference line at 80%. Title: *"A few vendors carry the spend — top 1% = 61% of AP dollars."* |
| B | **Vendor hygiene scorecard** | `03_vendor_hygiene_scorecard.csv` | Exclude the *"Active vendors (denominator)"* row. Horizontal bars: Rows `issue`, Columns `vendor_count`; label `vendor_count` + `pct_of_active`. Color a single accent. Title: *"4 master-data cleanup signals."* |
| C | **AP spend by department** | `02_spend_by_department.csv` | Bars: Rows `department` (sort by `total_spend` desc), Columns `total_spend`. Optionally a treemap (Size = `total_spend`, Label = `department`). Title: *"Where AP dollars land by service line."* |
| D | **Payment-lag distribution** | `04_payment_lag_distribution.csv` | Bars: Columns `lag_bucket_start` (continuous), Rows `SUM(paid_lines)`, Color by `sla_band` (On time / Late). Add a reference line at 45. Title: *"Mean ~29 days; 17% of invoices clear the 45-day SLA."* |
| E | **Spend by category × entity** | `05_spend_by_category_entity.csv` | Stacked bars: Rows `category_group` (sort desc), Columns `total_spend`, Color `entity` (MSO/FDN). Add `entity` to **Filters** so the whole dashboard can be sliced. |
| F | **Monthly spend trend** | `06_monthly_spend_trend.csv` | Line: Columns `month` (continuous), Rows `total_spend`. Light, for the top strip / sparkline feel. |

**KPI tiles (text objects or single-number sheets):**
`$7.23B AP spend` · `90,231 AP lines` · `3,504 active vendors` · `17% paid late` ·
`561 never-paid vendors`. (Pull from the extracts; e.g. total spend = `SUM(total_spend)`
on `02_spend_by_department.csv`.)

## 2. Dashboard
- New Dashboard **1200×900**. Title: **Vendor & AP Spend — Concentration, Hygiene & Timing**.
- Top: KPI tiles + sheet F (trend) as a thin strip.
- Left column: **A** (the spend story) over **C** (departments).
- Right column: **B** (hygiene) over **D** (payment timing); **E** below spanning width.
- Blue accent (#2563eb), hide gridlines on the bar sheets, tooltips on.
- **Footer text (required):** *"Synthetic dataset modeled on a Unit4/Coda-style ERP schema
  (academic health-system AP). No real vendors, dollar figures, or PII. Two legal entities: MSO / FDN."*

## 3. Publish + wire back
1. **Server → Tableau Public → Save** → copy the URL.
2. Set `TABLEAU_URL` in the portfolio `src/app/projects/vendor-ap-analytics/dashboards.tsx`,
   and screenshot the dashboard to `public/images/vendor-ap-analytics/tableau.png` for a sharper preview.
3. Send me the URL and I'll wire it in / embed the live viz.
