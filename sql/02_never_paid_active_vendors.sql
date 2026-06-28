-- 02 · Never-paid ACTIVE vendors (master-data cleanup candidates)
-- ------------------------------------------------------------------
-- Business question: which active vendor records have never been transacted
-- against? They bloat the vendor file, widen the fraud surface (dormant records
-- are a known abuse vector), and are prime candidates for deactivation.
--
-- Business rules:
--   * Active = open in the entity: oas_element.endyear = 0 (not closed).
--   * "Never paid" = the vendor CODE has zero rows in oas_docline (in ANY entity).
--     We use NOT EXISTS against oas_docline.el3 (an anti-join), the canonical
--     pattern for "master rows with no child transactions".
--   * Reported once per (entity, vendor) so AP can action the record in the
--     system where it lives; a vendor open in BOTH entities therefore appears
--     twice here. The hygiene scorecard (query 05) counts DISTINCT vendor codes,
--     so its headline (~561) is lower than this row count (~640 entity-records).
-- ------------------------------------------------------------------
SELECT e.cmpcode,
       e.code        AS vendor_code,
       e.name        AS vendor_name,
       e.country,
       e.adddate,
       g.grpcode     AS category_group
FROM oas_element e
-- attach the vendor's category group (exclude the generic 'XDEPT' bucket)
LEFT JOIN oas_grplist g
       ON g.cmpcode = e.cmpcode
      AND g.code    = e.code
      AND g.elmlevel = 3
      AND g.grpcode <> 'XDEPT'
WHERE e.elmlevel = 3            -- vendors only
  AND e.endyear  = 0            -- active (open)
  AND NOT EXISTS (              -- no transaction line anywhere for this vendor code
        SELECT 1
        FROM oas_docline l
        WHERE l.el3 = e.code
      )
ORDER BY e.cmpcode, e.code;
