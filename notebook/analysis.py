# %% [markdown]
# # Vendor & AP Spend Analytics
#
# **Synthetic dataset** modeled on the schema of a Unit4 / Coda-style ERP
# (accounts-payable + vendor master) for an academic health system. Production
# financial data is confidential, so every row here is generated — but the table
# and column names (`oas_element`, `oas_dochead`, `oas_docline`, …), the business
# rules, and the analyses are exactly what I'd run against the live AP tables.
#
# **Business question:** where do our AP dollars concentrate, and how clean and
# well-controlled is the vendor master that feeds payments?
#
# Data: `../data/*.csv` (regenerate with `python ../data/generate_data.py`).
# Every headline number below is cross-checked against the SQL in `../sql/`.

# %%
import os
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import PercentFormatter, FuncFormatter

D = os.path.join(os.path.dirname(__file__), "..", "data")
OUT = os.path.join(os.path.dirname(__file__), "figures")
os.makedirs(OUT, exist_ok=True)

INK, MUTED, PRIMARY = "#1a1a2e", "#6b7280", "#2563eb"   # one consistent blue accent
ACCENTS = ["#2563eb", "#0ea5e9", "#10b981", "#f59e0b", "#ef4444"]
LATE = "#ef4444"
plt.rcParams.update({
    "figure.dpi": 150, "font.size": 11, "axes.edgecolor": "#e5e7eb",
    "axes.grid": True, "grid.color": "#eef0f3", "axes.spines.top": False,
    "axes.spines.right": False, "axes.titlesize": 13, "axes.titleweight": "bold",
    "axes.titlecolor": INK, "text.color": INK, "axes.labelcolor": MUTED,
    "xtick.color": MUTED, "ytick.color": MUTED,
})


def usd(x, _=None):
    """Compact USD axis formatter ($1.2B / $340M / $12K)."""
    a = abs(x)
    if a >= 1e9:
        return f"${x/1e9:.1f}B"
    if a >= 1e6:
        return f"${x/1e6:.0f}M"
    if a >= 1e3:
        return f"${x/1e3:.0f}K"
    return f"${x:.0f}"


# %% [markdown]
# ## Load the synthetic ERP tables
# Four tables mirror the real AP slice: the element master (vendors + divisions),
# group membership, AP document headers, and the transaction lines.

# %%
element = pd.read_csv(f"{D}/oas_element.csv", dtype={"code": str, "endyear": int, "endperiod": int})
grplist = pd.read_csv(f"{D}/oas_grplist.csv", dtype={"code": str})
dochead = pd.read_csv(f"{D}/oas_dochead.csv", parse_dates=["adddate"])
docline = pd.read_csv(f"{D}/oas_docline.csv", dtype={"el3": str, "el2": str})
dim_div = pd.read_csv(f"{D}/dim_division.csv", dtype={"division_code": str})

vendors = element[element.elmlevel == 3].copy()           # vendor master rows
n_records = len(vendors)
n_codes = vendors.code.nunique()
active = vendors[vendors.endyear == 0]
n_active = active.code.nunique()
print(f"{len(docline):,} AP lines | {n_records:,} vendor records "
      f"({n_codes:,} distinct codes) | {n_active:,} active vendors | "
      f"{len(dochead):,} documents")

# Paid AP invoice lines = the spend universe (statpay 89, AP doc, positive line).
heads = dochead.set_index(["cmpcode", "docnum"])
lines = docline.merge(dochead[["cmpcode", "docnum", "doccode", "adddate"]],
                      on=["cmpcode", "docnum"], how="left")
paid = lines[(lines.statpay == 89) & (lines.valuedoc > 0) &
             (lines.doccode.str.startswith("AP"))].copy()
total_spend = paid.valuedoc.sum()
print(f"paid AP lines: {len(paid):,}  |  total synthetic AP spend: ${total_spend:,.0f}")

# %% [markdown]
# ## 1 · The headline — vendor spend is heavily Pareto
# A small set of vendors carries most of the dollars. That's the strategic-sourcing
# target: a handful of contracts move the entire AP budget.

# %%
by_vendor = (paid.groupby("el3").valuedoc.sum()
             .sort_values(ascending=False).rename("spend"))
cum = by_vendor.cumsum()
cum_pct = 100.0 * cum / total_spend

top10_share = by_vendor.head(10).sum() / total_spend * 100
n_top1 = max(1, round(len(by_vendor) * 0.01))
top1pct_share = by_vendor.head(n_top1).sum() / total_spend * 100
print(f"top-10 vendors  = {top10_share:5.1f}% of AP spend")
print(f"top-1% vendors  = {top1pct_share:5.1f}% of AP spend  (n={n_top1})")
print(f"vendors to reach 80% of spend: "
      f"{int((cum_pct <= 80).sum()) + 1} of {len(by_vendor):,}")

# Pareto chart: top-15 vendor bars (left axis) + full cumulative-% curve (right).
TOPN = 15
names = (element[element.elmlevel == 3]
         .drop_duplicates("code").set_index("code").name)
top = by_vendor.head(TOPN)
labels = [names.get(c, c).rsplit(" ", 1)[0] for c in top.index]   # trim serial token

fig, ax1 = plt.subplots(figsize=(9, 4.8))
x = np.arange(TOPN)
ax1.bar(x, top.values, color=PRIMARY, alpha=0.85, width=0.72)
ax1.set_ylabel("Paid AP spend (top 15 vendors)")
ax1.yaxis.set_major_formatter(FuncFormatter(usd))
ax1.set_xticks(x)
ax1.set_xticklabels(labels, rotation=40, ha="right", fontsize=7.5)
ax1.set_xlim(-0.7, TOPN - 0.3)

ax2 = ax1.twinx()
full_cum = cum_pct.reset_index(drop=True)
ax2.plot(np.arange(len(full_cum)), full_cum.values, color=INK, lw=2.2)
ax2.scatter(x, full_cum.values[:TOPN], color=INK, s=18, zorder=5)
ax2.axhline(80, color=MUTED, ls="--", lw=1)
ax2.text(len(full_cum) * 0.62, 82, "80% of spend", color=MUTED, fontsize=9)
ax2.set_ylabel("Cumulative % of total AP spend")
ax2.set_ylim(0, 105)
ax2.yaxis.set_major_formatter(PercentFormatter())
ax2.grid(False)
ax1.set_title(f"Vendor spend is Pareto: top 1% of vendors = {top1pct_share:.0f}% of AP dollars")
fig.subplots_adjust(left=0.115, right=0.885, bottom=0.32, top=0.91)
fig.savefig(f"{OUT}/spend_pareto.png", facecolor="white")
plt.close(fig)

# %% [markdown]
# ## 2 · Vendor master hygiene scorecard
# Four data-quality issues on the **active** vendor file, each a cleanup or control
# action. Denominator is distinct active vendor codes.

# %%
codes_with_lines = set(docline.el3.unique())
active_codes = set(active.code.unique())
never_paid = active_codes - codes_with_lines

foreign = active[(active.defaddr == 1) & (active.country.notna()) &
                 (active.country != "") & (active.country != "USA")].code.nunique()

open_codes = set(vendors.loc[vendors.endyear == 0, "code"])
closed_codes = set(vendors.loc[vendors.endyear != 0, "code"])
cross_entity = open_codes & closed_codes


def _norm(s):
    return (s.str.upper().str.replace(" ", "", regex=False)
            .str.replace(",", "", regex=False).str.replace(".", "", regex=False)
            .str.replace("-", "", regex=False)
            .str.replace("INCORPORATED", "INC", regex=False))


act = active.copy()
act["norm"] = _norm(act["name"])
dup_groups = act.groupby(["cmpcode", "norm"]).size()
near_dupes = int((dup_groups[dup_groups > 1] - 1).sum())   # extra records beyond the first

scorecard = pd.DataFrame({
    "issue": ["Never-paid\nactive", "Foreign\naddress",
              "Cross-entity\nopen/closed", "Near-duplicate\nnames"],
    "count": [len(never_paid), foreign, len(cross_entity), near_dupes],
})
scorecard["pct"] = 100.0 * scorecard["count"] / n_active
print(f"active vendors (denominator): {n_active:,}")
print(scorecard.to_string(index=False))

fig, ax = plt.subplots(figsize=(8, 4.4))
b = ax.bar(scorecard["issue"], scorecard["count"], color=PRIMARY, width=0.62)
for r, c, p in zip(b, scorecard["count"], scorecard["pct"]):
    ax.text(r.get_x() + r.get_width() / 2, c, f"{c:,}\n({p:.1f}%)",
            ha="center", va="bottom", fontsize=9.5, color=INK)
ax.set_ylabel("Active vendors flagged")
ax.margins(y=0.22)
ax.set_title(f"Vendor master hygiene: 4 cleanup signals across {n_active:,} active vendors")
fig.tight_layout()
fig.savefig(f"{OUT}/vendor_hygiene.png", facecolor="white")
plt.close(fig)

# %% [markdown]
# ## 3 · Where the money goes — AP spend by department
# Divisions roll up to ~15 generic clinical/finance departments. This is the view
# a finance partner uses to see which service lines drive third-party spend.

# %%
dept_map = dim_div.set_index("division_code").department
paid["department"] = paid.el2.map(dept_map)
by_dept = paid.groupby("department").valuedoc.sum().sort_values(ascending=False)
print((by_dept / 1e6).round(1).rename("spend_$M"))

fig, ax = plt.subplots(figsize=(8.6, 5))
y = np.arange(len(by_dept))
ax.barh(y, by_dept.values, color=PRIMARY, height=0.7)
ax.set_yticks(y)
ax.set_yticklabels(by_dept.index, fontsize=9.5)
ax.invert_yaxis()
ax.xaxis.set_major_formatter(FuncFormatter(usd))
ax.set_xlabel("Paid AP spend")
for yi, v in zip(y, by_dept.values):
    ax.text(v, yi, "  " + usd(v), va="center", ha="left", fontsize=8.5, color=MUTED)
ax.margins(x=0.12)
ax.set_title("AP spend by department (synthetic clinical/finance roll-up)")
fig.tight_layout()
fig.savefig(f"{OUT}/spend_by_department.png", facecolor="white")
plt.close(fig)

# %% [markdown]
# ## 4 · Payment timing — how much do we pay late?
# Lag = payment date − document add date. A late tail (> 45 days) strains vendor
# relationships and forfeits early-pay discounts.

# %%
paid_pay = paid[paid.paydate.notna() & (paid.paydate != "")].copy()
paid_pay["lag"] = (pd.to_datetime(paid_pay.paydate) - paid_pay.adddate).dt.days
mean_lag = paid_pay.lag.mean()
pct_late = (paid_pay.lag > 45).mean() * 100
pct_late60 = (paid_pay.lag > 60).mean() * 100
dollars_late = paid_pay.loc[paid_pay.lag > 45, "valuedoc"].sum()
print(f"mean payment lag : {mean_lag:.1f} days")
print(f"paid late (>45d) : {pct_late:.1f}%  (>60d: {pct_late60:.1f}%)")
print(f"$ paid late (>45d): ${dollars_late:,.0f}")

fig, ax = plt.subplots(figsize=(8.6, 4.6))
clip = paid_pay.lag.clip(upper=120)
ax.hist(clip, bins=np.arange(0, 122, 4), color=PRIMARY, alpha=0.85, edgecolor="white")
ax.axvline(45, color=LATE, ls="--", lw=2)
ax.text(46, ax.get_ylim()[1] * 0.92, f"  45-day SLA\n  {pct_late:.0f}% paid late",
        color=LATE, fontsize=10, va="top")
ax.axvline(mean_lag, color=INK, ls=":", lw=1.6)
ax.text(mean_lag + 1, ax.get_ylim()[1] * 0.62, f"mean {mean_lag:.0f}d", color=INK, fontsize=9)
ax.set_xlabel("Payment lag (days from document entry to payment)")
ax.set_ylabel("Paid AP lines")
ax.set_title(f"Payment timing: mean {mean_lag:.0f} days, but {pct_late:.0f}% of invoices clear the 45-day SLA")
fig.tight_layout()
fig.savefig(f"{OUT}/payment_timing.png", facecolor="white")
plt.close(fig)

# %% [markdown]
# ## Headline summary (cross-checks the SQL in `../sql/`)

# %%
print("=" * 58)
print("VENDOR & AP SPEND — headline metrics (synthetic)")
print("=" * 58)
print(f"total AP spend (paid)      : ${total_spend:,.0f}")
print(f"AP transaction lines       : {len(docline):,}  (paid: {len(paid):,})")
print(f"vendor records / codes     : {n_records:,} / {n_codes:,}")
print(f"active vendors             : {n_active:,}")
print(f"top-10 vendor spend share  : {top10_share:.1f}%")
print(f"top-1% vendor spend share  : {top1pct_share:.1f}%  (n={n_top1})")
print(f"never-paid active vendors  : {len(never_paid):,}  ({len(never_paid)/n_active*100:.1f}%)")
print(f"foreign-address active     : {foreign:,}  ({foreign/n_active*100:.1f}%)")
print(f"cross-entity open/closed   : {len(cross_entity):,}")
print(f"near-duplicate name pairs  : {near_dupes:,}")
print(f"% paid invoices late (>45d): {pct_late:.1f}%")
print(f"mean payment lag           : {mean_lag:.1f} days")
print("\nAll figures saved to notebook/figures/")
