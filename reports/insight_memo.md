# Insight memo — Vendor & AP spend analytics

**To:** Procurement / Controllership · **From:** Data Analyst · **Re:** Where AP dollars concentrate, and how clean the vendor master is
*(Synthetic dataset modeled on a Unit4/Coda-style ERP schema for an academic health system — 2 legal entities, ~2.5 fiscal years, 3,552 vendors, 90,231 AP lines, $7.23B paid spend. No real vendors, dollar figures, or PII; production financial data is confidential.)*

## TL;DR
AP value is **highly concentrated** and the vendor master is **noisier than it should be**. Two low-cost levers beat chasing more savings projects: focus sourcing on the handful of vendors that move the budget, and run a one-time master-data cleanup that also closes real payment-control gaps. Payment timing is healthy on average but has a sizable late tail worth recovering.

## What we found
1. **Spend is Pareto.** The **top 10 vendors are 38% of AP spend** and the **top 1% (29 vendors) are 61%**; just **82 of 2,876** paying vendors reach 80% of dollars. Sourcing effort should be ranked by spend, not vendor count.
2. **The vendor master needs a cleanup.** Of **3,504 active vendors**: **561 (16%) have never been paid** (dormant records that widen the fraud surface), **207 (5.9%) have a foreign default address** (cross-border compliance review), and there are **52 near-duplicate name pairs** (double-payment risk).
3. **A cross-entity control gap.** **118 vendor codes are closed in one legal entity but still open in the other** — a blocked vendor can still be paid from the other set of books. These should be reconciled to a single status.
4. **Payment timing is fine on average, but the tail is costly.** Mean lag is **~29 days**, yet **17% of invoices clear the 45-day SLA** (8% clear 60 days), representing **$1.23B** of late-paid invoice value — relationship risk and forfeited early-pay discounts.

## Recommendations (ranked)
1. **Run strategic sourcing on the top ~30 vendors first.** They carry 61% of spend; even small rate or term improvements there dwarf long-tail work.
2. **Execute a vendor-master cleanup sprint.** Deactivate/merge the 561 never-paid records, resolve the 52 near-duplicate pairs before they cause double payments, and route the 207 foreign-address vendors through compliance screening.
3. **Reconcile the 118 cross-entity open/closed vendors** and add a periodic control so a vendor's status can't diverge between MSO and FDN.
4. **Attack the late-payment tail** — target the categories driving >45-day lags to protect discounts and vendor relationships; the mean is fine, the tail is the problem.

## Caveat
Synthetic dataset; magnitudes are illustrative but calibrated to realistic AP distributions (Pareto concentration, master-data hygiene rates, ~28-day payment timing). The schema, SQL, and methodology are production-faithful — the same queries would run unchanged against the live ERP tables.
