-- 05 · Vendor master HYGIENE scorecard (one-query data-quality summary)
-- ------------------------------------------------------------------
-- Business question: how clean is the vendor master overall? This is the single
-- KPI tile an AP / internal-audit lead checks — one row per data-quality issue,
-- with a count and its share of the active vendor population.
--
-- Each metric is computed as a scalar subquery so the whole scorecard is one
-- result set (issue, vendor_count, pct_of_active). Denominator = distinct ACTIVE
-- vendor codes (endyear = 0).
--
-- Business rules per issue are documented inline. "Active" = endyear = 0 unless a
-- check is intrinsically about closed records (cross-entity gap).
-- ------------------------------------------------------------------
WITH active_vendor_count AS (
    SELECT COUNT(DISTINCT code) AS n
    FROM oas_element
    WHERE elmlevel = 3 AND endyear = 0
)
SELECT 'Active vendors (denominator)' AS issue,
       (SELECT n FROM active_vendor_count) AS vendor_count,
       100.0                               AS pct_of_active

UNION ALL
-- Count DISTINCT vendor CODES (a vendor in both entities is one vendor, not two).
SELECT 'Never-paid active (no AP lines)',
       (SELECT COUNT(DISTINCT e.code) FROM oas_element e
         WHERE e.elmlevel = 3 AND e.endyear = 0
           AND NOT EXISTS (SELECT 1 FROM oas_docline l WHERE l.el3 = e.code)),
       ROUND(100.0 *
         (SELECT COUNT(DISTINCT e.code) FROM oas_element e
           WHERE e.elmlevel = 3 AND e.endyear = 0
             AND NOT EXISTS (SELECT 1 FROM oas_docline l WHERE l.el3 = e.code))
         / (SELECT n FROM active_vendor_count), 1)

UNION ALL
SELECT 'Foreign default address (active)',
       (SELECT COUNT(DISTINCT code) FROM oas_element
         WHERE elmlevel = 3 AND endyear = 0 AND defaddr = 1
           AND country IS NOT NULL AND country <> '' AND country <> 'USA'),
       ROUND(100.0 *
         (SELECT COUNT(DISTINCT code) FROM oas_element
           WHERE elmlevel = 3 AND endyear = 0 AND defaddr = 1
             AND country IS NOT NULL AND country <> '' AND country <> 'USA')
         / (SELECT n FROM active_vendor_count), 1)

UNION ALL
-- Cross-entity gap: codes that are open in one entity and closed in another.
SELECT 'Cross-entity open/closed gap',
       (SELECT COUNT(*) FROM (
           SELECT code FROM oas_element WHERE elmlevel = 3 AND endyear = 0
           INTERSECT
           SELECT code FROM oas_element WHERE elmlevel = 3 AND endyear <> 0)),
       ROUND(100.0 *
         (SELECT COUNT(*) FROM (
             SELECT code FROM oas_element WHERE elmlevel = 3 AND endyear = 0
             INTERSECT
             SELECT code FROM oas_element WHERE elmlevel = 3 AND endyear <> 0))
         / (SELECT n FROM active_vendor_count), 1)

UNION ALL
-- Near-duplicate names: vendors sharing a normalized name within the same entity.
-- Normalize = uppercase, strip spaces and common punctuation/suffix noise, so
-- "Apex Pharma Inc", "Apex Pharma, Inc." and "APEX PHARMA INC" collapse together.
-- (Prod Unit4 would use STRING_AGG; SQLite uses GROUP_CONCAT — see query 06.)
SELECT 'Near-duplicate vendor names',
       (SELECT COALESCE(SUM(cnt - 1), 0) FROM (
           SELECT cmpcode,
                  REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(name),
                         ' ', ''), ',', ''), '.', ''), '-', ''), 'INCORPORATED', 'INC') AS norm_name,
                  COUNT(*) AS cnt
           FROM oas_element
           WHERE elmlevel = 3 AND endyear = 0
           GROUP BY cmpcode, norm_name
           HAVING COUNT(*) > 1)),
       ROUND(100.0 *
         (SELECT COALESCE(SUM(cnt - 1), 0) FROM (
             SELECT cmpcode,
                    REPLACE(REPLACE(REPLACE(REPLACE(REPLACE(UPPER(name),
                           ' ', ''), ',', ''), '.', ''), '-', ''), 'INCORPORATED', 'INC') AS norm_name,
                    COUNT(*) AS cnt
             FROM oas_element
             WHERE elmlevel = 3 AND endyear = 0
             GROUP BY cmpcode, norm_name
             HAVING COUNT(*) > 1))
         / (SELECT n FROM active_vendor_count), 1);
