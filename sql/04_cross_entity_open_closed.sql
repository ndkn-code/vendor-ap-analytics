-- 04 · Vendors CLOSED in one entity but still OPEN in the other (governance gap)
-- ------------------------------------------------------------------
-- Business question: where is the vendor master out of sync between the two legal
-- entities? A supplier deactivated in MSO but still open in FDN (or vice-versa)
-- means a blocked vendor can still be paid from the other set of books — a control
-- gap that should be reconciled.
--
-- Business rules:
--   * "Open"   in an entity  = oas_element.endyear = 0.
--   * "Closed" in an entity  = oas_element.endyear <> 0 (a closing FY was stamped).
--   * We want vendor CODES that appear as OPEN in at least one entity AND CLOSED
--     in at least one entity. Implemented with INTERSECT over two CTEs — the set
--     intersection of {codes open somewhere} and {codes closed somewhere}.
--   * Because a vendor is only in 1-2 entities, an INTERSECT membership implies the
--     open and closed states live in DIFFERENT entities (the governance gap).
-- ------------------------------------------------------------------
WITH open_codes AS (
    SELECT DISTINCT code
    FROM oas_element
    WHERE elmlevel = 3
      AND endyear = 0
),
closed_codes AS (
    SELECT DISTINCT code
    FROM oas_element
    WHERE elmlevel = 3
      AND endyear <> 0
),
gap_codes AS (
    SELECT code FROM open_codes
    INTERSECT
    SELECT code FROM closed_codes
)
SELECT e.code AS vendor_code,
       MIN(e.name) AS vendor_name,
       -- which entity holds the OPEN record vs the CLOSED record
       MAX(CASE WHEN e.endyear =  0 THEN e.cmpcode END) AS open_in_entity,
       MAX(CASE WHEN e.endyear <> 0 THEN e.cmpcode END) AS closed_in_entity,
       MAX(CASE WHEN e.endyear <> 0 THEN e.endyear  END) AS closed_fy,
       MAX(CASE WHEN e.endyear <> 0 THEN e.endperiod END) AS closed_period
FROM oas_element e
JOIN gap_codes gc ON gc.code = e.code
WHERE e.elmlevel = 3
GROUP BY e.code
ORDER BY e.code;
