"""Export pre-shaped CSV extracts to dashboards/extracts/ so the Tableau / Power BI
dashboards can be assembled quickly (no pivoting needed). Each extract is a tidy,
aggregated table built straight from the synthetic SQLite DB. You can instead
connect the raw data/*.csv and build the calcs yourself if you want to show the
wrangling. Run AFTER data/generate_data.py.

Out: dashboards/extracts/*.csv
"""
import os
import sqlite3
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(HERE, "..", "data", "vendor_ap.db")
OUT = os.path.join(HERE, "extracts")
os.makedirs(OUT, exist_ok=True)

con = sqlite3.connect(DB)

# Common "paid AP invoice line" predicate, reused below.
PAID = ("l.statpay = 89 AND l.valuedoc > 0 AND h.doccode LIKE 'AP%'")


def q(sql: str) -> pd.DataFrame:
    return pd.read_sql_query(sql, con)


# 1 · Vendor spend ranking + running % (full Pareto curve, all vendors with spend)
vendor_rank = q(f"""
WITH vs AS (
  SELECT l.el3 AS vendor_code, SUM(l.valuedoc) AS total_spend, COUNT(*) AS paid_lines
  FROM oas_docline l JOIN oas_dochead h
    ON h.cmpcode=l.cmpcode AND h.docnum=l.docnum
  WHERE {PAID}
  GROUP BY l.el3)
SELECT ROW_NUMBER() OVER (ORDER BY vs.total_spend DESC) AS spend_rank,
       vs.vendor_code,
       e.name AS vendor_name,
       ROUND(vs.total_spend, 2) AS total_spend,
       vs.paid_lines,
       ROUND(100.0 * vs.total_spend / SUM(vs.total_spend) OVER (), 4) AS pct_of_total,
       ROUND(100.0 * SUM(vs.total_spend) OVER (ORDER BY vs.total_spend DESC) /
             SUM(vs.total_spend) OVER (), 4) AS running_pct_of_total
FROM vs
LEFT JOIN (SELECT code, MIN(name) name FROM oas_element WHERE elmlevel=3 GROUP BY code) e
  ON e.code = vs.vendor_code
ORDER BY spend_rank;
""")
vendor_rank.to_csv(f"{OUT}/01_vendor_spend_ranking.csv", index=False)

# 2 · Spend by department (with line counts) — for the bar / treemap
spend_dept = q(f"""
SELECT d.department,
       ROUND(SUM(l.valuedoc), 2) AS total_spend,
       COUNT(*) AS paid_lines,
       COUNT(DISTINCT l.el3) AS distinct_vendors
FROM oas_docline l
JOIN oas_dochead h ON h.cmpcode=l.cmpcode AND h.docnum=l.docnum
JOIN dim_division d ON d.division_code = l.el2
WHERE {PAID}
GROUP BY d.department
ORDER BY total_spend DESC;
""")
spend_dept.to_csv(f"{OUT}/02_spend_by_department.csv", index=False)

# 3 · Vendor hygiene scorecard (the four data-quality KPIs + denominator)
hygiene = pd.read_sql_query(
    open(os.path.join(HERE, "..", "sql", "05_vendor_hygiene_scorecard.sql")).read(), con)
hygiene.to_csv(f"{OUT}/03_vendor_hygiene_scorecard.csv", index=False)

# 4 · Payment-lag distribution (binned) — for the histogram / SLA marker
pay_hist = q(f"""
WITH paid AS (
  SELECT CAST(julianday(l.paydate) - julianday(h.adddate) AS INT) AS lag_days, l.valuedoc
  FROM oas_docline l JOIN oas_dochead h ON h.cmpcode=l.cmpcode AND h.docnum=l.docnum
  WHERE {PAID} AND l.paydate IS NOT NULL AND l.paydate <> '')
SELECT (lag_days / 5) * 5 AS lag_bucket_start,
       COUNT(*) AS paid_lines,
       ROUND(SUM(valuedoc), 2) AS spend_in_bucket,
       CASE WHEN lag_days > 45 THEN 'Late (>45d)' ELSE 'On time' END AS sla_band
FROM paid
GROUP BY lag_bucket_start, sla_band
ORDER BY lag_bucket_start;
""")
pay_hist.to_csv(f"{OUT}/04_payment_lag_distribution.csv", index=False)

# 5 · Spend by category group x entity — for a stacked/grouped bar + entity filter
spend_group = q(f"""
SELECT l.cmpcode AS entity,
       g.grpcode AS category_group,
       ROUND(SUM(l.valuedoc), 2) AS total_spend,
       COUNT(*) AS paid_lines
FROM oas_docline l
JOIN oas_dochead h ON h.cmpcode=l.cmpcode AND h.docnum=l.docnum
JOIN oas_grplist g ON g.cmpcode=l.cmpcode AND g.code=l.el3 AND g.grpcode <> 'XDEPT'
WHERE {PAID}
GROUP BY l.cmpcode, g.grpcode
ORDER BY total_spend DESC;
""")
spend_group.to_csv(f"{OUT}/05_spend_by_category_entity.csv", index=False)

# 6 · Monthly AP spend trend (paid) — for a line chart / KPI sparkline
spend_trend = q(f"""
SELECT substr(h.adddate, 1, 7) AS month,
       h.yr AS fiscal_year,
       ROUND(SUM(l.valuedoc), 2) AS total_spend,
       COUNT(*) AS paid_lines
FROM oas_docline l
JOIN oas_dochead h ON h.cmpcode=l.cmpcode AND h.docnum=l.docnum
WHERE {PAID}
GROUP BY month, h.yr
ORDER BY month;
""")
spend_trend.to_csv(f"{OUT}/06_monthly_spend_trend.csv", index=False)

for name, df in [
    ("01_vendor_spend_ranking", vendor_rank),
    ("02_spend_by_department", spend_dept),
    ("03_vendor_hygiene_scorecard", hygiene),
    ("04_payment_lag_distribution", pay_hist),
    ("05_spend_by_category_entity", spend_group),
    ("06_monthly_spend_trend", spend_trend),
]:
    print(f"{name}.csv: {len(df)} rows")

print("\nExtracts written to dashboards/extracts/")
con.close()
