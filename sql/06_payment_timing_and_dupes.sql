-- 06 · Payment-timing analysis + near-duplicate vendor detection
-- ------------------------------------------------------------------
-- Two AP-operations questions in one file (run the blocks separately):
--   (A) How fast do we pay, and how much is LATE? Late payments risk vendor
--       relationships and forfeit early-pay discounts; the lag distribution is the
--       working-capital signal. Lag = paydate - document adddate (days).
--   (B) Which active vendors look like DUPLICATES of each other within an entity?
--       Near-duplicate masters are the classic double-payment / fraud risk.
--
-- Business rules:
--   * Paid lines only: statpay = 89, valuedoc > 0, doccode LIKE 'AP%'.
--   * Late threshold = 45 days (the AP team's SLA marker); 60d shown too.
--   * Duplicate key = normalized name (UPPER, strip spaces/punctuation, fold
--     "INCORPORATED"->"INC") within the same cmpcode.
--   * String aggregation uses SQLite GROUP_CONCAT; production Unit4 (SQL Server)
--     would use STRING_AGG(name, ' | ') WITHIN GROUP (ORDER BY code).
-- ==================================================================

-- (A) Payment-timing summary -----------------------------------------------
WITH paid AS (
    SELECT (julianday(l.paydate) - julianday(h.adddate)) AS lag_days,
           l.valuedoc
    FROM oas_docline l
    JOIN oas_dochead h
      ON h.cmpcode = l.cmpcode AND h.docnum = l.docnum
    WHERE l.statpay = 89
      AND l.valuedoc > 0
      AND h.doccode LIKE 'AP%'
      AND l.paydate IS NOT NULL AND l.paydate <> ''
)
SELECT COUNT(*)                                                        AS paid_lines,
       ROUND(AVG(lag_days), 1)                                         AS avg_lag_days,
       ROUND(AVG(CASE WHEN lag_days <= 30 THEN 1.0 ELSE 0 END) * 100, 1) AS pct_within_30d,
       ROUND(AVG(CASE WHEN lag_days >  45 THEN 1.0 ELSE 0 END) * 100, 1) AS pct_late_45d,
       ROUND(AVG(CASE WHEN lag_days >  60 THEN 1.0 ELSE 0 END) * 100, 1) AS pct_late_60d,
       ROUND(SUM(CASE WHEN lag_days > 45 THEN valuedoc ELSE 0 END), 2) AS dollars_paid_late_45d
FROM paid;

-- (B) Near-duplicate vendor names within an entity -------------------------
WITH normalized AS (
    SELECT cmpcode,
           code,
           name,
           REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(name),
                  ' ', ''), ',', ''), '.', ''), '-', ''), 'INCORPORATED', 'INC') AS norm_name
    FROM oas_element
    WHERE elmlevel = 3
      AND endyear = 0                 -- active records only
)
SELECT cmpcode,
       norm_name,
       COUNT(*)                       AS n_records,
       GROUP_CONCAT(code, ' | ')      AS vendor_codes,   -- prod: STRING_AGG(code, ' | ')
       GROUP_CONCAT(name, ' | ')      AS vendor_names     -- prod: STRING_AGG(name, ' | ')
FROM normalized
GROUP BY cmpcode, norm_name
HAVING COUNT(*) > 1                    -- 2+ active records share a normalized name
ORDER BY n_records DESC, cmpcode, norm_name;
