"""
Air Liquide - Revenue Bridge & Reconciliation
Step 1: read the RAW transcription of Air Liquide's published press releases
Step 2: clean it (labels, periods, keys) into a star schema for Power BI
Step 3: run reconciliation checks (additivity, restatement, period roll-up, bridge)

Run from the repository root:
    python scripts/clean_and_check.py
Inputs : data/raw/*.csv
Outputs: data/clean/*.csv
"""
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"
CLEAN.mkdir(parents=True, exist_ok=True)

ROUNDING_TOL_EUR_M = 2      # published figures are rounded to EUR 1m -> sums can differ by 1-2m
ROUNDING_TOL_PCT = 0.1      # published growth rates are rounded to 0.1 pt

# ---------------------------------------------------------------------------
# 1. LOAD RAW
# ---------------------------------------------------------------------------
rev_raw = pd.read_csv(RAW / "air_liquide_revenue_raw.csv")
bridge_raw = pd.read_csv(RAW / "air_liquide_bridge_raw.csv")
sources = pd.read_csv(RAW / "sources.csv")

# ---------------------------------------------------------------------------
# 2. CLEAN
# ---------------------------------------------------------------------------
# 2a. Harmonise segment labels: the releases use different names for the same thing
LABEL_MAP = {
    "Group Revenue": "Group",
    "Group": "Group",
    "Europe, Middle East & Africa (EMEA)": "EMEA",
    "Europe, Middle East & Africa": "EMEA",
    "Europe": "EMEA",
    "EMEA": "EMEA",
}
rev = rev_raw.copy()
rev["segment"] = rev["segment_as_published"].map(LABEL_MAP).fillna(rev["segment_as_published"])
label_log = (rev[rev["segment"] != rev["segment_as_published"]]
             .groupby(["segment_as_published", "segment"]).size()
             .reset_index(name="rows_relabelled"))

# 2b. Dimension: segments (a simple hierarchy Group > Activity, Gas & Services > Region / Business line)
dim_segment = pd.DataFrame([
    ("SEG01", "Group", "Group", None, 1),
    ("SEG02", "Gas & Services", "Activity", "Group", 2),
    ("SEG03", "Engineering & Technologies", "Activity", "Group", 3),
    ("SEG04", "Americas", "Region", "Gas & Services", 4),
    ("SEG05", "EMEA", "Region", "Gas & Services", 5),
    ("SEG06", "Asia Pacific", "Region", "Gas & Services", 6),
    ("SEG07", "Large Industries", "Business line", "Gas & Services", 7),
    ("SEG08", "Industrial Merchant", "Business line", "Gas & Services", 8),
    ("SEG09", "Healthcare", "Business line", "Gas & Services", 9),
    ("SEG10", "Electronics", "Business line", "Gas & Services", 10),
], columns=["segment_key", "segment", "segment_type", "parent_segment", "sort_order"])
rev = rev.merge(dim_segment[["segment_key", "segment"]], on="segment", how="left")
assert rev["segment_key"].notna().all(), "Unmapped segment label in raw data"

# 2c. Dimension: periods
def period_attrs(label: str) -> dict:
    kind, year = label.split()
    year = int(year)
    end_month = {"Q1": 3, "Q2": 6, "Q3": 9, "Q4": 12, "H1": 6, "9M": 9, "FY": 12}[kind]
    ptype = "Quarter" if kind.startswith("Q") else {"H1": "Half-year", "9M": "Nine months", "FY": "Full year"}[kind]
    return {
        "period_key": f"{year}-{kind}",
        "period": label,
        "period_code": kind,
        "year": year,
        "period_type": ptype,
        "quarter_num": int(kind[1]) if kind.startswith("Q") else None,
        "period_end_date": pd.Timestamp(year=year, month=end_month, day=1) + pd.offsets.MonthEnd(0),
        "sort_order": year * 100 + {"Q1": 1, "Q2": 2, "H1": 3, "Q3": 4, "9M": 5, "Q4": 6, "FY": 7}[kind],
    }

all_periods = sorted(set(rev["period"]) | set(bridge_raw["period"]))
dim_period = pd.DataFrame([period_attrs(p) for p in all_periods]).sort_values("sort_order")
dim_period["quarter_num"] = dim_period["quarter_num"].astype("Int64")
rev = rev.merge(dim_period[["period", "period_key"]], on="period", how="left")

# 2d. Reference value ("golden record"): one figure per period x segment.
#     Rule: first publication of the period itself; if the period was never the
#     reported period in our sources (2024), use the earliest prior-year comparative.
role_rank = {"Reported period": 1, "Quarterly table": 2, "Prior-year comparative": 3}
rev["role_rank"] = rev["role"].map(role_rank)
rev = rev.merge(sources[["source_id", "publication_date"]], on="source_id", how="left")
rev = rev.sort_values(["period_key", "segment_key", "role_rank", "publication_date"])
rev["is_reference"] = (~rev.duplicated(["period_key", "segment_key"], keep="first")).astype(int)

fact_revenue = rev[["source_id", "period_key", "segment_key", "role", "revenue_eur_m",
                    "published_change_pct", "comparable_change_pct", "is_reference", "note"]].copy()
fact_revenue.insert(0, "row_id", range(1, len(fact_revenue) + 1))

ref = fact_revenue[fact_revenue["is_reference"] == 1].merge(dim_segment, on="segment_key")
ref_val = ref.set_index(["period_key", "segment"])["revenue_eur_m"]

# 2e. Bridge fact: prior-year revenue -> drivers -> comparable growth (derived) = current revenue
br = bridge_raw.copy()
br = br.merge(dim_period[["period", "period_key"]], on="period")
br["segment_key"] = br["scope"].map({"Group": "SEG01", "Gas & Services": "SEG02"})
br["is_derived"] = 0

# Q4 2025 Gas & Services internal transfer is not shown in the release -> derive it: FY - (Q1+Q2+Q3)
mask_q4 = (br["period"] == "Q4 2025") & (br["scope"] == "Gas & Services") & (br["driver"] == "Internal transfer")
fy_tr = br[(br["period"] == "FY 2025") & (br["scope"] == "Gas & Services") & (br["driver"] == "Internal transfer")]["impact_eur_m"].sum()
q13_tr = br[(br["period"].isin(["Q1 2025", "Q2 2025", "Q3 2025"])) & (br["scope"] == "Gas & Services")
            & (br["driver"] == "Internal transfer")]["impact_eur_m"].sum()
br.loc[mask_q4, "impact_eur_m"] = fy_tr - q13_tr
br.loc[mask_q4, "is_derived"] = 1
br.loc[mask_q4, "note"] = f"Derived: FY 2025 ({fy_tr:.0f}) minus Q1-Q3 2025 ({q13_tr:.0f})"

PRIOR = {"Q1 2025": "Q1 2024", "Q2 2025": "Q2 2024", "Q3 2025": "Q3 2024", "Q4 2025": "Q4 2024",
         "FY 2025": "FY 2024", "Q1 2026": "Q1 2025", "Q2 2026": "Q2 2025", "Q3 2026": "Q3 2025"}
STEP_ORDER = {"Prior-year revenue": 1, "Currency": 2, "Natural gas": 3, "Electricity": 4,
              "Significant scope": 5, "Internal transfer": 6, "Comparable growth": 7}

def prior_revenue(period: str, scope: str) -> float:
    p = PRIOR[period]
    key = (dim_period.set_index("period").loc[p, "period_key"], scope)
    if key in ref_val.index:
        return float(ref_val.loc[key])
    if p == "FY 2024" and scope == "Group":   # not printed in FY release -> sum of 2024 quarters
        return float(sum(ref_val.loc[(f"2024-Q{q}", "Group")] for q in range(1, 5)))
    raise KeyError(key)

bridge_rows, bridge_checks = [], []
for (period, scope), g in br.groupby(["period", "scope"]):
    pkey = g["period_key"].iloc[0]
    seg_key = g["segment_key"].iloc[0]
    prev = prior_revenue(period, scope)
    curr = float(ref_val.loc[(pkey, scope)])
    drivers = g.set_index("driver")["impact_eur_m"].fillna(0)
    comparable_eur = curr - prev - drivers.sum()
    derived_prev = int(period == "FY 2025" and scope == "Group")
    bridge_rows.append(dict(period_key=pkey, segment_key=seg_key, driver="Prior-year revenue",
                            amount_eur_m=prev, is_derived=derived_prev, source_id=g["source_id"].iloc[0],
                            note="Sum of 2024 quarters" if derived_prev else ""))
    for _, r in g.iterrows():
        bridge_rows.append(dict(period_key=pkey, segment_key=seg_key, driver=r["driver"],
                                amount_eur_m=0 if pd.isna(r["impact_eur_m"]) else r["impact_eur_m"],
                                is_derived=r["is_derived"], source_id=r["source_id"],
                                note="" if pd.isna(r["note"]) else r["note"]))
    bridge_rows.append(dict(period_key=pkey, segment_key=seg_key, driver="Comparable growth",
                            amount_eur_m=comparable_eur, is_derived=1, source_id=g["source_id"].iloc[0],
                            note="Residual: current - prior-year - drivers"))
    # check: recomputed comparable growth % vs comparable growth % printed in the release
    printed = fact_revenue[(fact_revenue["period_key"] == pkey) & (fact_revenue["segment_key"] == seg_key)
                           & (fact_revenue["role"] == "Reported period")]["comparable_change_pct"]
    recomputed = round(comparable_eur / prev * 100, 2)
    if len(printed) and pd.notna(printed.iloc[0]):
        bridge_checks.append(("Bridge: recomputed vs published comparable growth", pkey, scope,
                              float(printed.iloc[0]), recomputed, "pct"))

fact_bridge = pd.DataFrame(bridge_rows)
fact_bridge["step_order"] = fact_bridge["driver"].map(STEP_ORDER)
fact_bridge = fact_bridge.sort_values(["period_key", "segment_key", "step_order"])

# ---------------------------------------------------------------------------
# 3. RECONCILIATION CHECKS
# ---------------------------------------------------------------------------
checks = []  # (check_type, period_key, scope, expected, actual, unit)
full = rev.merge(dim_segment[["segment_key", "segment_type"]], on="segment_key")

# 3a. Additivity inside each published table: parts must add up to the total
for (src, pkey, role), g in full.groupby(["source_id", "period_key", "role"]):
    v = g.set_index("segment")["revenue_eur_m"]
    if "Gas & Services" in v:
        regions = g[g["segment_type"] == "Region"]["revenue_eur_m"]
        lines = g[g["segment_type"] == "Business line"]["revenue_eur_m"]
        if len(regions) == 3:
            checks.append(("Additivity: regions = Gas & Services", pkey, f"{src} / {role}",
                           v["Gas & Services"], regions.sum(), "eur_m"))
        if len(lines) == 4:
            checks.append(("Additivity: business lines = Gas & Services", pkey, f"{src} / {role}",
                           v["Gas & Services"], lines.sum(), "eur_m"))
    if {"Group", "Gas & Services", "Engineering & Technologies"} <= set(v.index):
        checks.append(("Additivity: activities = Group", pkey, f"{src} / {role}",
                       v["Group"], v["Gas & Services"] + v["Engineering & Technologies"], "eur_m"))

# 3b. Restatement: the same period x segment published in several documents must be identical
for (pkey, seg), g in full.groupby(["period_key", "segment"]):
    if g["source_id"].nunique() > 1:
        first = g.sort_values(["role_rank", "publication_date"]).iloc[0]
        for _, r in g.iterrows():
            if r["source_id"] != first["source_id"] or r["role"] != first["role"]:
                checks.append(("Restatement: later publication = first publication", pkey,
                               f"{seg} ({first['source_id']} vs {r['source_id']})",
                               first["revenue_eur_m"], r["revenue_eur_m"], "eur_m"))

# 3c. Period roll-up: quarters must add up to half-year / nine months / full year
ROLLUPS = {
    "2025-H1": ["2025-Q1", "2025-Q2"], "2025-9M": ["2025-Q1", "2025-Q2", "2025-Q3"],
    "2025-FY": ["2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"],
    "2024-H1": ["2024-Q1", "2024-Q2"], "2024-FY": ["2024-Q1", "2024-Q2", "2024-Q3", "2024-Q4"],
    "2026-H1": ["2026-Q1", "2026-Q2"], "2026-9M": ["2026-Q1", "2026-Q2", "2026-Q3"],
}
for total_p, parts in ROLLUPS.items():
    for seg in dim_segment["segment"]:
        if (total_p, seg) in ref_val.index and all((p, seg) in ref_val.index for p in parts):
            checks.append(("Roll-up: sum of quarters = cumulative period", total_p, seg,
                           ref_val.loc[(total_p, seg)], sum(ref_val.loc[(p, seg)] for p in parts), "eur_m"))

# 3d. Bridge roll-up: quarterly impacts must add up to the full-year impact
for scope in ["Group", "Gas & Services"]:
    for drv in ["Currency", "Natural gas", "Electricity", "Significant scope"]:
        q = br[(br["scope"] == scope) & (br["driver"] == drv) & br["period"].str.endswith("2025") & br["period"].str.startswith("Q")]
        fy = br[(br["scope"] == scope) & (br["driver"] == drv) & (br["period"] == "FY 2025")]["impact_eur_m"]
        checks.append((f"Bridge roll-up: Q1-Q4 = FY ({drv})", "2025-FY", scope,
                       float(fy.iloc[0]), float(q["impact_eur_m"].sum()), "eur_m"))

checks += bridge_checks

fact_checks = pd.DataFrame(checks, columns=["check_type", "period_key", "scope", "expected", "actual", "unit"])
fact_checks["difference"] = (fact_checks["actual"] - fact_checks["expected"]).round(2)

def status(r):
    d = abs(r["difference"])
    if r["unit"] == "pct":
        return "OK" if d <= 0.05 else ("Rounding" if d <= ROUNDING_TOL_PCT + 0.05 else "Investigate")
    return "OK" if d == 0 else ("Rounding" if d <= ROUNDING_TOL_EUR_M else "Break")

fact_checks["status"] = fact_checks.apply(status, axis=1)
fact_checks.insert(0, "check_id", [f"C{i:03d}" for i in range(1, len(fact_checks) + 1)])

# ---------------------------------------------------------------------------
# 4. WRITE CLEAN FILES
# ---------------------------------------------------------------------------
dim_source = sources.rename(columns={"document": "source_document"})
dim_period.to_csv(CLEAN / "dim_period.csv", index=False)
dim_segment.to_csv(CLEAN / "dim_segment.csv", index=False)
dim_source.to_csv(CLEAN / "dim_source.csv", index=False)
fact_revenue.to_csv(CLEAN / "fact_revenue.csv", index=False)
fact_bridge.to_csv(CLEAN / "fact_bridge.csv", index=False)
fact_checks.to_csv(CLEAN / "fact_checks.csv", index=False)
label_log.to_csv(CLEAN / "log_label_mapping.csv", index=False)

print(f"Raw rows: revenue={len(rev_raw)}, bridge={len(bridge_raw)}, sources={len(sources)}")
print(f"Clean rows: fact_revenue={len(fact_revenue)} (reference={fact_revenue.is_reference.sum()}), "
      f"fact_bridge={len(fact_bridge)}, fact_checks={len(fact_checks)}")
print("\nLabels harmonised:\n", label_log.to_string(index=False))
print("\nCheck results:\n", fact_checks.groupby(["check_type", "status"]).size().to_string())
issues = fact_checks[fact_checks["status"] != "OK"]
print("\nNon-zero differences:\n", issues[["check_type", "period_key", "scope", "expected", "actual", "difference", "status"]].to_string(index=False))
