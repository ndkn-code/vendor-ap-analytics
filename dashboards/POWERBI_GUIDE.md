# Power BI build guide — "Vendor & AP Spend" (Business Analyst lens)

**Goal:** a dashboard answering *where does AP spend concentrate, how clean is the vendor
master, and are we paying on time?*
**Tool:** Power BI Desktop (Windows). **Time:** ~60–90 min.
**Output:** save `dashboards/vendor_ap_spend.pbix`; optionally publish to Power BI Service.

> All figures are **synthetic**, modeled on a Unit4/Coda-style ERP schema. Keep the footer
> disclaimer below on the published report.

## Data
Fastest path — **Get Data → Text/CSV** for the pre-shaped extracts
(run `python dashboards/export_extracts.py` first):
- `extracts/01_vendor_spend_ranking.csv`
- `extracts/02_spend_by_department.csv`
- `extracts/03_vendor_hygiene_scorecard.csv`
- `extracts/04_payment_lag_distribution.csv`
- `extracts/05_spend_by_category_entity.csv`
- `extracts/06_monthly_spend_trend.csv`

Richer path — load the raw `../data/*.csv` (`oas_element`, `oas_grplist`, `oas_dochead`,
`oas_docline`, `dim_division`), set relationships (`oas_dochead[cmpcode,docnum]` 1—* to
`oas_docline`; `oas_element[code]` to `oas_docline[el3]`; `dim_division[division_code]` to
`oas_docline[el2]`), and write the measures yourself (see bottom).

## Visual 1 — Vendor spend Pareto (headline)
- Source: `01_vendor_spend_ranking`.
- **Line and clustered column chart**: Shared axis = `vendor_name` (filter visual to Top 20 by
  `total_spend`); Column = `total_spend`; Line = `running_pct_of_total` (secondary axis 0–100%).
- Title: **"Vendor spend is Pareto: top 1% of vendors = 61% of AP dollars."**

## Visual 2 — Vendor hygiene scorecard
- Source: `03_vendor_hygiene_scorecard`; filter out the *"Active vendors (denominator)"* row.
- **Clustered bar**: Axis = `issue`; Values = `vendor_count`; data labels show `vendor_count`.
- Title: **"561 never-paid, 207 foreign, 118 cross-entity, 52 near-duplicate."**

## Visual 3 — Payment-lag distribution
- Source: `04_payment_lag_distribution`.
- **Stacked column**: Axis = `lag_bucket_start`; Values = `paid_lines`; Legend = `sla_band`.
- Add a constant line at 45. Title: **"Mean ~29 days; 17% of invoices clear the 45-day SLA."**

## KPI cards (DAX, from the extracts)
```DAX
Total AP Spend = SUM('02_spend_by_department'[total_spend])

Pct Paid Late =
DIVIDE(
    CALCULATE(SUM('04_payment_lag_distribution'[paid_lines]),
              '04_payment_lag_distribution'[sla_band] = "Late (>45d)"),
    SUM('04_payment_lag_distribution'[paid_lines])
)

Never-Paid Vendors =
CALCULATE(SUM('03_vendor_hygiene_scorecard'[vendor_count]),
          '03_vendor_hygiene_scorecard'[issue] = "Never-paid active (no AP lines)")
```
Add Card visuals: **Total AP Spend** ($7.23B), **Pct Paid Late** (17%), **Never-Paid Vendors** (561),
and a **Top-1% spend share** card (61%).

## Layout & theme
- KPI cards across the top; Pareto + hygiene on the main row; payment-lag + a `06_monthly_spend_trend`
  line below; slicer on `entity` (from `05_spend_by_category_entity`) in the corner.
- Title: **Vendor & AP Spend — Concentration, Hygiene & Timing**. Blue theme (#2563eb).
- **Footer text box (required):** *"Synthetic dataset modeled on a Unit4/Coda-style ERP schema
  (academic health-system AP). No real vendors, dollar figures, or PII. Two legal entities: MSO / FDN."*

## Deliver
Save `vendor_ap_spend.pbix` into this folder. If you publish to Power BI Service, copy the report
link and update the portfolio `dashboards.tsx` (Power BI card). Export a screenshot to
`public/images/vendor-ap-analytics/powerbi.png` for the page preview.

## Build from raw (optional, advanced)
Example measures on the raw tables (filter to paid AP invoice lines:
`statpay = 89 && valuedoc > 0 && LEFT(doccode,2) = "AP"`):
```DAX
Paid AP Spend =
CALCULATE(SUM(oas_docline[valuedoc]),
          oas_docline[statpay] = 89, oas_docline[valuedoc] > 0,
          LEFT(RELATED(oas_dochead[doccode]), 2) = "AP")

Active Vendors = CALCULATE(DISTINCTCOUNT(oas_element[code]),
                           oas_element[elmlevel] = 3, oas_element[endyear] = 0)
```
