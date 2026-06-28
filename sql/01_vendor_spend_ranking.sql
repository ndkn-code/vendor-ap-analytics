-- 01 · Vendor spend ranking with running total + running % (Pareto)
-- ------------------------------------------------------------------
-- Business question: which vendors carry our AP dollars? Strategic sourcing and
-- contract negotiation should focus where spend concentrates.
--
-- Business rules:
--   * Spend = PAID AP invoice lines only: statpay = 89, doccode LIKE 'AP%',
--     and valuedoc > 0 (exclude credit/adjustment lines, which net spend down).
--   * Vendor identity = oas_element.code (elmlevel 3), summed ACROSS both entities
--     (cmpcode MSO + FDN) because the same supplier may be paid from either.
--   * Window functions build the cumulative spend and cumulative % of total so the
--     Pareto "vital few" are obvious (top 10 ~ 39%, top 1% ~ 60%).
-- ------------------------------------------------------------------
WITH paid_lines AS (
    SELECT l.el3 AS vendor_code,
           l.valuedoc
    FROM oas_docline l
    JOIN oas_dochead h
      ON h.cmpcode = l.cmpcode AND h.docnum = l.docnum
    WHERE l.statpay = 89               -- paid
      AND l.valuedoc > 0               -- invoices only (drop credit memos)
      AND h.doccode LIKE 'AP%'         -- AP documents
),
vendor_spend AS (
    SELECT vendor_code,
           SUM(valuedoc) AS total_spend,
           COUNT(*)      AS paid_lines
    FROM paid_lines
    GROUP BY vendor_code
),
ranked AS (
    SELECT vs.vendor_code,
           e.name AS vendor_name,
           vs.total_spend,
           vs.paid_lines,
           RANK()      OVER (ORDER BY vs.total_spend DESC)                        AS spend_rank,
           SUM(vs.total_spend) OVER (ORDER BY vs.total_spend DESC
                                     ROWS BETWEEN UNBOUNDED PRECEDING
                                              AND CURRENT ROW)                    AS running_spend,
           SUM(vs.total_spend) OVER ()                                           AS grand_total
    FROM vendor_spend vs
    -- Pull a display name from either entity's master row (names are identical).
    LEFT JOIN (
        SELECT code, MIN(name) AS name
        FROM oas_element WHERE elmlevel = 3 GROUP BY code
    ) e ON e.code = vs.vendor_code
)
SELECT spend_rank,
       vendor_code,
       vendor_name,
       ROUND(total_spend, 2)                              AS total_spend,
       paid_lines,
       ROUND(100.0 * total_spend / grand_total, 2)        AS pct_of_total,
       ROUND(running_spend, 2)                            AS running_spend,
       ROUND(100.0 * running_spend / grand_total, 2)      AS running_pct_of_total
FROM ranked
ORDER BY spend_rank
LIMIT 25;   -- top 25; drop the LIMIT to materialize the full Pareto curve
