-- 03 · Active vendors with a FOREIGN default address (compliance review)
-- ------------------------------------------------------------------
-- Business question: which active vendors are paid to a non-US default address?
-- Cross-border payments carry OFAC/sanctions-screening, tax (1042/W-8), and
-- FX-control obligations, so AP compliance reviews this population each quarter.
--
-- Business rules:
--   * Default address only: oas_element.defaddr = 1 (the primary remit-to row).
--   * Foreign = country IS NOT 'USA' (and not blank — divisions carry no country).
--   * Active = endyear = 0.
--   * Joined to YTD paid spend so reviewers triage by exposure (biggest first).
-- ------------------------------------------------------------------
WITH vendor_paid AS (
    SELECT l.el3 AS vendor_code,
           SUM(l.valuedoc) AS paid_spend,
           COUNT(*)        AS paid_lines
    FROM oas_docline l
    JOIN oas_dochead h
      ON h.cmpcode = l.cmpcode AND h.docnum = l.docnum
    WHERE l.statpay = 89
      AND l.valuedoc > 0
      AND h.doccode LIKE 'AP%'
    GROUP BY l.el3
)
SELECT e.cmpcode,
       e.code                          AS vendor_code,
       e.name                          AS vendor_name,
       e.country,
       COALESCE(ROUND(vp.paid_spend, 2), 0) AS paid_spend,
       COALESCE(vp.paid_lines, 0)            AS paid_lines
FROM oas_element e
LEFT JOIN vendor_paid vp ON vp.vendor_code = e.code
WHERE e.elmlevel = 3
  AND e.endyear  = 0                    -- active
  AND e.defaddr  = 1                    -- default address row
  AND e.country IS NOT NULL
  AND e.country <> ''
  AND e.country <> 'USA'               -- foreign
ORDER BY paid_spend DESC, e.cmpcode, e.code;
