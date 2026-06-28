"""
Vendor & AP Spend Analytics — synthetic data generator
==============================================================================
Generates a SYNTHETIC dataset modeled on the schema of a Unit4 / Coda-style ERP
(accounts-payable + vendor master) as run by an academic health system. NO real
rows, vendor names, dollar figures, or PII are used — production financial data is
confidential. The table and column names mirror the real ERP so the SQL reads
authentically (oas_element, oas_grplist, oas_dochead, oas_docline); the contents
are simulated, calibrated to realistic AP distributions.

Two legal entities are modeled, matching a typical MSO / Foundation structure:
  MSO  — medical service organization
  FDN  — affiliated foundation
Some vendors are onboarded in BOTH entities (the same master record, replicated).

Modeled relationships the analysis surfaces:
  1. Vendor spend is heavily Pareto (lognormal): a handful of vendors carry most
     of the AP dollars — the case for strategic-sourcing focus.
  2. A long tail of ACTIVE vendors have ZERO paid lines (never-paid) — master-data
     cleanup / deactivation candidates that bloat the vendor file.
  3. Governance gaps: vendors active (foreign address), or closed in one entity but
     still open in the other, or near-duplicate names (double-payment risk).
  4. Payment timing: most invoices paid ~28 days out, with a tail paid late
     (>45 / >60 days) — working-capital and discount-capture signal.

Run: python generate_data.py
Out: data/*.csv + data/schema.sql load into data/vendor_ap.db (deterministic, seed=42)
==============================================================================
"""
from __future__ import annotations
import os
import sqlite3
import numpy as np
import pandas as pd

SEED = 42
HERE = os.path.dirname(os.path.abspath(__file__))

# ---- Dataset size knobs (calibrated to the spec) ---------------------------
N_VENDORS = 3500          # distinct vendor master records (across both entities)
N_LINES_TARGET = 90_000   # AP transaction lines (oas_docline)
ENTITIES = ["MSO", "FDN"]

# Fiscal calendar: ~2.5 fiscal years of postings. FY runs Jul 1 -> Jun 30, so
# FY2024 = period 1 is Jul-2023. We post from FY2024 P1 through FY2026 P6.
FY_START_CAL_MONTH = 7    # July
POST_START = pd.Timestamp("2023-07-01")   # FY2024 period 1
POST_END = pd.Timestamp("2025-12-31")     # mid FY2026

# Compliance / hygiene mix targets (share of ACTIVE vendors)
P_FOREIGN = 0.065         # ~5-8% active vendors with a foreign default address
P_NEVER_PAID = 0.175      # ~15-20% active vendors with zero transactions
P_CROSS_ENTITY = 0.030    # ~2-4% closed in one entity but open in the other
P_NEAR_DUP = 0.015        # ~1-2% near-duplicate vendor names

# Payment timing (doc adddate -> paydate)
PAY_LAG_MEAN = 28.0
LATE_THRESHOLD = 45       # days; the AP team's late-payment SLA marker

# ---- Generic department mapping (NO real org structure) --------------------
# ~12-15 generic clinical/finance departments, each fed by a few 4-digit divisions.
DEPARTMENTS = [
    "Cardiology", "Neurology", "OBGYN", "Radiology", "Internal Medicine",
    "Surgery", "Family Medicine", "Orthopedics", "Pediatrics", "Dermatology",
    "Pathology", "Emergency Medicine", "Oncology", "Anesthesiology",
    "Administration",
]

# Vendor category groups (oas_grplist grpcode), drives spend scale + payment habit.
VENDOR_GROUPS = {
    "PHARMA":   {"share": 0.10, "scale": 2.10, "late": 0.10},  # drug distributors — big spend
    "MEDDEV":   {"share": 0.12, "scale": 1.70, "late": 0.14},  # medical devices / implants
    "LABSUP":   {"share": 0.14, "scale": 0.95, "late": 0.18},  # lab + clinical supplies
    "ITSVC":    {"share": 0.10, "scale": 1.25, "late": 0.16},  # software / IT services
    "FACIL":    {"share": 0.11, "scale": 1.05, "late": 0.22},  # facilities / maintenance
    "PROSVC":   {"share": 0.13, "scale": 1.40, "late": 0.20},  # professional services
    "STAFFNG":  {"share": 0.08, "scale": 1.55, "late": 0.24},  # locum / staffing agencies
    "OFFICE":   {"share": 0.12, "scale": 0.55, "late": 0.15},  # office / general supplies
    "TRAVEL":   {"share": 0.06, "scale": 0.45, "late": 0.12},  # travel / conferences
    "UTIL":     {"share": 0.04, "scale": 0.80, "late": 0.06},  # utilities — paid on time
}

# Tokens for synthetic vendor names — generic, no real company maps to these.
_NAME_HEAD = [
    "Apex", "Summit", "Vertex", "Beacon", "Cornerstone", "Pinnacle", "Keystone",
    "Meridian", "Cascade", "Horizon", "Granite", "Harbor", "Frontier", "Sterling",
    "Vanguard", "Cardinal", "Atlas", "Crescent", "Allied", "United", "Premier",
    "Integrated", "Advanced", "Precision", "Reliable", "Metro", "Regional",
    "National", "Coastal", "Highland", "Riverside", "Northgate", "Southpoint",
    "Evergreen", "Brightline", "Trinity", "Liberty", "Sentinel", "Paramount",
    "Continental", "Dominion", "Heritage", "Lakeshore", "Bluegrass", "Ironwood",
]
_NAME_MID = {
    "PHARMA":  ["Pharmaceuticals", "Pharma Distribution", "RX Wholesale", "Biologics", "Drug Supply"],
    "MEDDEV":  ["Medical Devices", "Surgical Systems", "Implant Solutions", "Diagnostics", "MedTech"],
    "LABSUP":  ["Laboratory Supply", "Clinical Reagents", "Diagnostics Supply", "Lab Solutions", "BioSupply"],
    "ITSVC":   ["Technology Group", "Software Solutions", "Health IT", "Data Systems", "Cloud Services"],
    "FACIL":   ["Facilities Services", "Building Maintenance", "Mechanical Group", "Environmental Svcs", "Property Mgmt"],
    "PROSVC":  ["Consulting Group", "Advisory Partners", "Professional Services", "Associates", "Partners LLP"],
    "STAFFNG": ["Staffing Group", "Locum Partners", "Healthcare Staffing", "Workforce Solutions", "Clinical Staffing"],
    "OFFICE":  ["Office Supply", "Business Products", "General Supply", "Print Services", "Supply Company"],
    "TRAVEL":  ["Travel Services", "Conference Group", "Events Management", "Hospitality Group", "Lodging Partners"],
    "UTIL":    ["Power & Light", "Energy Services", "Water Authority", "Gas Company", "Utility Services"],
}
_NAME_SUFFIX = ["Inc", "LLC", "Corp", "Co", "Group", "Holdings", "LP", "Ltd"]
_FOREIGN_COUNTRIES = ["CAN", "GBR", "DEU", "IRL", "CHE", "IND", "JPN", "NLD"]


def _period_of(ts: pd.Timestamp) -> tuple[int, int]:
    """Map a calendar date to (fiscal_year, fiscal_period 1..12), FY starts in July."""
    m, y = ts.month, ts.year
    if m >= FY_START_CAL_MONTH:
        fy = y + 1
        period = m - FY_START_CAL_MONTH + 1
    else:
        fy = y
        period = m + (12 - FY_START_CAL_MONTH) + 1
    return fy, period


def main() -> None:
    rng = np.random.default_rng(SEED)

    # ======================================================================
    # 1. DIVISIONS (oas_element elmlevel=2) and their department mapping
    # ======================================================================
    # ~40 division codes (4-digit numeric strings) mapped to the generic depts.
    n_div = 40
    div_codes = [f"{1000 + 25 * i:04d}" for i in range(n_div)]   # 1000,1025,1050,...
    div_dept = [DEPARTMENTS[i % len(DEPARTMENTS)] for i in range(n_div)]
    # Larger clinical departments draw more transactions (spend weight).
    dept_weight = {d: w for d, w in zip(
        DEPARTMENTS,
        [1.6, 1.3, 1.2, 1.5, 1.7, 1.8, 1.1, 1.2, 1.3, 0.7,
         0.9, 1.4, 1.5, 1.0, 2.0])}
    div_weight = np.array([dept_weight[d] for d in div_dept])
    div_weight = div_weight / div_weight.sum()

    # ======================================================================
    # 2. VENDOR MASTER (oas_element elmlevel=3) + groups (oas_grplist)
    # ======================================================================
    group_names = list(VENDOR_GROUPS)
    gp = np.array([VENDOR_GROUPS[g]["share"] for g in group_names])
    gp = gp / gp.sum()
    vendor_group = rng.choice(group_names, N_VENDORS, p=gp)

    vendor_code = [f"V{i + 1:04d}" for i in range(N_VENDORS)]

    # Synthetic vendor names (head + group-specific middle + suffix). The token
    # vocabulary is finite, so to keep each vendor's name UNIQUE (and make the only
    # name collisions the near-duplicates we deliberately inject below), we suffix a
    # zero-padded serial drawn from the vendor index. Realistic enough — many real
    # suppliers carry a regional/branch number — and it isolates the dup signal.
    heads = rng.choice(_NAME_HEAD, N_VENDORS)
    mids = np.array([rng.choice(_NAME_MID[g]) for g in vendor_group])
    sufs = rng.choice(_NAME_SUFFIX, N_VENDORS)
    serials = rng.permutation(N_VENDORS)   # unique 0..N-1, shuffled
    vendor_name = np.array([
        f"{h} {m} {s} {serials[i]:04d}"
        for i, (h, m, s) in enumerate(zip(heads, mids, sufs))])
    short_name = np.array([f"{h[:10].upper()}" for h in heads])

    # Foreign default address (compliance review): ~6.5% of vendors.
    is_foreign = rng.random(N_VENDORS) < P_FOREIGN
    country = np.where(is_foreign,
                       rng.choice(_FOREIGN_COUNTRIES, N_VENDORS),
                       "USA")

    # Which entity(ies) a vendor is registered in. ~30% are in BOTH entities;
    # the rest split between MSO-only and FDN-only.
    placement = rng.choice(["MSO", "FDN", "BOTH"], N_VENDORS, p=[0.40, 0.30, 0.30])

    # Onboarding date for the master record (adddate), spread over ~6 years.
    add_span_days = (POST_END - pd.Timestamp("2019-01-01")).days
    add_offsets = rng.integers(0, add_span_days, N_VENDORS)
    add_dates = pd.Timestamp("2019-01-01") + pd.to_timedelta(add_offsets, unit="D")

    # Spend scale per vendor: lognormal -> Pareto. Group scale shifts the mean,
    # and a heavy sigma produces the long head we want (top 1% dominate). This is
    # the vendor's relative SHARE of total dollars (drives both line count AND the
    # per-vendor average line value, so a few vendors carry most of the spend).
    grp_scale = np.array([VENDOR_GROUPS[g]["scale"] for g in vendor_group])
    spend_potential = rng.lognormal(mean=0.0, sigma=2.05, size=N_VENDORS) * grp_scale

    # Never-paid ACTIVE vendors: tag a share to receive ZERO lines. (We pick them
    # among vendors that will otherwise be active; closed vendors handled below.)
    never_paid = rng.random(N_VENDORS) < P_NEVER_PAID

    # Cross-entity governance gap: a small share are CLOSED in one entity but OPEN
    # in the other. Only meaningful for BOTH-entity vendors.
    cross_entity_gap = (placement == "BOTH") & (rng.random(N_VENDORS) < (P_CROSS_ENTITY / 0.30))
    closed_side = np.where(rng.random(N_VENDORS) < 0.5, "MSO", "FDN")

    # Build the vendor rows per entity. A vendor in BOTH entities yields two
    # oas_element rows (one per cmpcode), mirroring the real replicated master.
    vrows = []          # oas_element vendor rows
    grows = []          # oas_grplist rows (XDEPT + category group, per entity row)
    # Index helpers for the transaction generator.
    active_vendor_keys = []   # (cmpcode, vendor_code, group, spend_potential, never_paid)

    for i in range(N_VENDORS):
        sides = ENTITIES if placement[i] == "BOTH" else [placement[i]]
        for cc in sides:
            # Closed? endyear/endperiod nonzero => closed in this entity.
            closed_here = False
            if cross_entity_gap[i] and cc == closed_side[i]:
                closed_here = True
            # A few standalone closed vendors too (deactivated everywhere) — small.
            elif (placement[i] != "BOTH") and (rng.random() < 0.02):
                closed_here = True

            if closed_here:
                close_dt = add_dates[i] + pd.Timedelta(days=int(rng.integers(180, 1500)))
                if close_dt > POST_END:
                    close_dt = POST_END
                endfy, endp = _period_of(close_dt)
                del_date = close_dt
            else:
                endfy, endp, del_date = 0, 0, pd.NaT

            vrows.append({
                "cmpcode": cc,
                "code": vendor_code[i],
                "name": vendor_name[i],
                "sname": short_name[i],
                "elmlevel": 3,
                "adddate": add_dates[i].date().isoformat(),
                "deldate": (del_date.date().isoformat() if pd.notna(del_date) else ""),
                "endperiod": endp,
                "endyear": endfy,
                "country": country[i],
                "defaddr": 1,
            })
            grows.append({"cmpcode": cc, "code": vendor_code[i], "elmlevel": 3, "grpcode": "XDEPT"})
            grows.append({"cmpcode": cc, "code": vendor_code[i], "elmlevel": 3, "grpcode": vendor_group[i]})

            # Active in this entity (open) and not flagged never-paid => can transact.
            if (not closed_here) and (not never_paid[i]):
                active_vendor_keys.append((cc, vendor_code[i], vendor_group[i], spend_potential[i]))

    # Inject ~1.5% NEAR-DUPLICATE vendor names (double-payment risk). We append a
    # handful of brand-new vendor records whose name is a small mutation of an
    # existing active vendor's name (spacing/suffix/punctuation), in the SAME entity.
    n_dup_pairs = int(round(P_NEAR_DUP * N_VENDORS))
    dup_seed_idx = rng.choice(np.where(~never_paid)[0], n_dup_pairs, replace=False)
    next_vnum = N_VENDORS + 1
    dup_pairs = []  # (cmpcode, original_code, dup_code) for reporting/verification
    for i in dup_seed_idx:
        cc = ENTITIES[0] if placement[i] == "BOTH" else placement[i]
        base = vendor_name[i]
        # All four variants are TRUE near-duplicates: they collapse to the SAME
        # normalized key as `base` under the detection rule (UPPER + strip
        # spaces/punctuation + fold INCORPORATED->INC), so query 06 catches each
        # pair while a human eyeballing the raw name file might not.
        variant_kind = rng.integers(0, 4)
        if variant_kind == 0:
            dup_name = base.replace(" Inc ", ", Inc. ").replace(" LLC ", ", LLC ")
            if dup_name == base:
                dup_name = base + "."                     # trailing period
        elif variant_kind == 1:
            dup_name = base.replace(" ", "  ", 1)         # double space
        elif variant_kind == 2:
            dup_name = base.replace("Inc ", "Incorporated ").replace("Corp ", "Corporation ")
            if dup_name == base:
                dup_name = base.upper()                   # all-caps casing dupe
        else:
            dup_name = base.replace(" ", ".", 1)          # period instead of space
        dcode = f"V{next_vnum:04d}"
        next_vnum += 1
        vrows.append({
            "cmpcode": cc, "code": dcode, "name": dup_name,
            "sname": short_name[i], "elmlevel": 3,
            "adddate": (add_dates[i] + pd.Timedelta(days=int(rng.integers(30, 900)))).date().isoformat(),
            "deldate": "", "endperiod": 0, "endyear": 0,
            "country": country[i], "defaddr": 1,
        })
        grows.append({"cmpcode": cc, "code": dcode, "elmlevel": 3, "grpcode": "XDEPT"})
        grows.append({"cmpcode": cc, "code": dcode, "elmlevel": 3, "grpcode": vendor_group[i]})
        # The duplicate also transacts a little (that's the whole risk).
        active_vendor_keys.append((cc, dcode, vendor_group[i], spend_potential[i] * 0.15))
        dup_pairs.append((cc, vendor_code[i], dcode))

    # Division oas_element rows (one set per entity).
    for cc in ENTITIES:
        for dc, dn in zip(div_codes, div_dept):
            vrows.append({
                "cmpcode": cc, "code": dc, "name": f"{dn} ({dc})", "sname": dn[:10].upper(),
                "elmlevel": 2, "adddate": "2019-01-01", "deldate": "",
                "endperiod": 0, "endyear": 0, "country": "", "defaddr": 0,
            })

    oas_element = pd.DataFrame(vrows)
    oas_grplist = pd.DataFrame(grows)

    # ======================================================================
    # 3. AP DOCUMENTS + LINES (oas_dochead / oas_docline)
    # ======================================================================
    # Allocate the ~90k lines across active vendor-entity keys. We split the two
    # drivers of Pareto concentration:
    #   - line COUNT is only mildly skewed (sqrt of potential), so the long tail of
    #     small vendors still posts a handful of invoices (realistic AP file), and
    #   - per-vendor AVERAGE LINE VALUE carries the heavy Pareto tail, so a few big
    #     vendors dominate total DOLLARS even without dominating line count.
    keys = active_vendor_keys
    pot = np.array([k[3] for k in keys], dtype=float)
    # Line-count weights: damped (sqrt) so counts aren't as extreme as dollars.
    cnt_w = np.sqrt(pot)
    cnt_w = cnt_w / cnt_w.sum()
    exp_lines = cnt_w * N_LINES_TARGET
    n_lines_per_key = np.maximum(1, rng.poisson(np.clip(exp_lines, 0.25, None))).astype(int)
    # Per-vendor average line value ($): anchored low (~$2.5k) and scaled by the
    # FULL potential tail -> top vendors average six-figure lines, tail averages
    # a few thousand. This is what concentrates the dollars.
    pot_norm = pot / np.median(pot)
    vendor_line_mean = np.clip(2_500.0 * pot_norm, 150.0, 1_150_000.0)

    span_days = (POST_END - POST_START).days
    grp_late = {g: VENDOR_GROUPS[g]["late"] for g in VENDOR_GROUPS}

    doc_rows = []       # oas_dochead
    line_rows = []      # oas_docline
    docnum_counter = {cc: 100000 for cc in ENTITIES}

    for kidx, ((cc, vcode, grp, _pot), nlines) in enumerate(zip(keys, n_lines_per_key)):
        line_mean = vendor_line_mean[kidx]   # this vendor's average line value ($)
        # Group lines into documents of 1-4 lines each.
        remaining = int(nlines)
        while remaining > 0:
            k = min(remaining, int(rng.integers(1, 5)))
            remaining -= k
            docnum_counter[cc] += 1
            docnum = docnum_counter[cc]

            # Document add date (invoice received). Recent years weighted slightly.
            frac = rng.beta(1.6, 1.25)            # skew toward recent periods
            add_dt = POST_START + pd.Timedelta(days=int(frac * span_days))
            fy, period = _period_of(add_dt)
            doccode = "API" if rng.random() < 0.8 else "APC"   # invoice vs credit/adj
            doc_rows.append({
                "cmpcode": cc, "docnum": docnum, "yr": fy, "period": period,
                "doccode": doccode, "adddate": add_dt.date().isoformat(),
            })

            # Payment lag -> paydate. Base ~ gamma(mean 28) + group-driven late tail.
            for _ln in range(k):
                # Line amount: lognormal noise (CV ~ fixed) around the vendor's mean
                # line value, so within-vendor variation is realistic but the vendor
                # tier sets the magnitude. exp(N(0, .55^2)) has mean ~1.16 -> divide.
                noise = rng.lognormal(mean=0.0, sigma=0.55) / 1.16
                base_amt = line_mean * noise
                amt = round(float(np.clip(base_amt, 12, 5_000_000)), 2)
                if doccode == "APC":
                    amt = -round(abs(amt) * rng.uniform(0.1, 0.6), 2)   # credit memo

                # Payment status: most paid (89). A few still open (unpaid) -> NULL paydate.
                paid = rng.random() < 0.94
                if paid:
                    # lag: gamma base + a group-driven late tail; the base mean is set
                    # below the SLA so the blended mean lands ~28d (target).
                    base_lag = rng.gamma(shape=4.0, scale=23.0 / 4.0)   # base mean ~23d
                    if rng.random() < grp_late[grp]:
                        base_lag += rng.uniform(20, 55)          # late tail
                    lag = int(np.clip(base_lag, 1, 240))
                    paydate = (add_dt + pd.Timedelta(days=lag)).date().isoformat()
                    statpay = 89
                else:
                    paydate = ""
                    statpay = 0

                line_rows.append({
                    "cmpcode": cc, "docnum": docnum,
                    "el3": vcode, "el2": rng.choice(div_codes, p=div_weight),
                    "valuedoc": amt, "statpay": statpay, "paydate": paydate,
                })

    oas_dochead = pd.DataFrame(doc_rows)
    oas_docline = pd.DataFrame(line_rows)

    # ======================================================================
    # 4. WRITE CSVs
    # ======================================================================
    oas_element.to_csv(f"{HERE}/oas_element.csv", index=False)
    oas_grplist.to_csv(f"{HERE}/oas_grplist.csv", index=False)
    oas_dochead.to_csv(f"{HERE}/oas_dochead.csv", index=False)
    oas_docline.to_csv(f"{HERE}/oas_docline.csv", index=False)
    # A small generic division->department dimension (helps BI joins / readers).
    pd.DataFrame({"division_code": div_codes, "department": div_dept}).to_csv(
        f"{HERE}/dim_division.csv", index=False)

    # ======================================================================
    # 5. LOAD SQLite (so the SQL is runnable)
    # ======================================================================
    db = f"{HERE}/vendor_ap.db"
    if os.path.exists(db):
        os.remove(db)
    conn = sqlite3.connect(db)
    conn.executescript(open(f"{HERE}/schema.sql").read())
    oas_element.to_sql("oas_element", conn, if_exists="append", index=False)
    oas_grplist.to_sql("oas_grplist", conn, if_exists="append", index=False)
    oas_dochead.to_sql("oas_dochead", conn, if_exists="append", index=False)
    oas_docline.to_sql("oas_docline", conn, if_exists="append", index=False)
    pd.DataFrame({"division_code": div_codes, "department": div_dept}).to_sql(
        "dim_division", conn, if_exists="append", index=False)
    conn.commit()

    # ======================================================================
    # 6. ROW COUNTS + HEADLINE CALIBRATION SUMMARY
    # ======================================================================
    n_vendor_master = int((oas_element.elmlevel == 3).sum())
    n_distinct_vendor_codes = oas_element.loc[oas_element.elmlevel == 3, "code"].nunique()
    paid = oas_docline[(oas_docline.statpay == 89) & (oas_docline.valuedoc > 0)].copy()
    total_spend = paid.valuedoc.sum()

    print("=" * 64)
    print("VENDOR & AP SPEND — synthetic dataset (Unit4/Coda-style schema)")
    print("=" * 64)
    print(f"oas_element rows:   {len(oas_element):>8,}  "
          f"(vendors {n_vendor_master:,} incl. {len(dup_pairs)} near-dupes + divisions)")
    print(f"  distinct vendor codes: {n_distinct_vendor_codes:>5,}")
    print(f"oas_grplist rows:   {len(oas_grplist):>8,}")
    print(f"oas_dochead rows:   {len(oas_dochead):>8,}")
    print(f"oas_docline rows:   {len(oas_docline):>8,}")
    print(f"  paid lines (89,+): {len(paid):>8,}")
    print("-" * 64)
    print(f"total paid AP spend:        ${total_spend:>16,.0f}")

    # Pareto check (by vendor code, across entities, paid lines only).
    by_vendor = paid.groupby("el3").valuedoc.sum().sort_values(ascending=False)
    top10_share = by_vendor.head(10).sum() / total_spend * 100
    n_top1pct = max(1, int(round(len(by_vendor) * 0.01)))
    top1pct_share = by_vendor.head(n_top1pct).sum() / total_spend * 100
    print(f"top-10 vendor spend share:  {top10_share:>6.1f}%   (target 35-45%)")
    print(f"top-1% vendor spend share:  {top1pct_share:>6.1f}%   (target 55-65%, n={n_top1pct})")

    # Late payments.
    paid_pay = paid[paid.paydate != ""].copy()
    paid_pay = paid_pay.merge(oas_dochead[["cmpcode", "docnum", "adddate"]],
                              on=["cmpcode", "docnum"], how="left")
    lag = (pd.to_datetime(paid_pay.paydate) - pd.to_datetime(paid_pay.adddate)).dt.days
    pct_late = (lag > LATE_THRESHOLD).mean() * 100
    print(f"mean payment lag:           {lag.mean():>6.1f} days   (target ~28)")
    print(f"% paid invoices late (>{LATE_THRESHOLD}d): {pct_late:>5.1f}%")

    # Hygiene counts (active = open in entity: endyear=0).
    v3 = oas_element[oas_element.elmlevel == 3].copy()
    active = v3[v3.endyear == 0]
    n_active = active.code.nunique()
    vendors_with_lines = set(oas_docline.el3.unique())
    active_codes = set(active.code.unique())
    never_paid_active = active_codes - vendors_with_lines
    foreign_active = active[(active.defaddr == 1) & (active.country != "USA")].code.nunique()
    # Cross-entity: code open (endyear=0) in one entity AND closed (endyear!=0) in the other.
    open_codes = set(v3.loc[v3.endyear == 0, "code"])
    closed_codes = set(v3.loc[v3.endyear != 0, "code"])
    cross = open_codes & closed_codes
    print("-" * 64)
    print(f"distinct active vendors:    {n_active:>8,}")
    print(f"never-paid active vendors:  {len(never_paid_active):>8,}  "
          f"({len(never_paid_active)/n_active*100:.1f}% of active)")
    print(f"foreign-address active:     {foreign_active:>8,}  "
          f"({foreign_active/n_active*100:.1f}% of active)")
    print(f"cross-entity open/closed:   {len(cross):>8,}")
    print(f"near-duplicate name pairs:  {len(dup_pairs):>8,}")
    print("=" * 64)
    print("OK -> data/*.csv + data/vendor_ap.db")


if __name__ == "__main__":
    main()
