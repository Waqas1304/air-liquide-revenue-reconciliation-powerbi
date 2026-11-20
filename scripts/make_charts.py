"""Static charts for the project report (docs/images). Power BI is the interactive version."""
from pathlib import Path
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
C, IMG = ROOT / "data" / "clean", ROOT / "docs" / "images"
IMG.mkdir(parents=True, exist_ok=True)
b = pd.read_csv(C / "fact_bridge.csv"); chk = pd.read_csv(C / "fact_checks.csv")
r = pd.read_csv(C / "fact_revenue.csv"); per = pd.read_csv(C / "dim_period.csv"); seg = pd.read_csv(C / "dim_segment.csv")
BLUE, GREY, POS, NEG = "#1f4e79", "#9aa5b1", "#2e8b57", "#c0392b"
plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})

def waterfall(period_key, seg_key, title, fname):
    d = b[(b.period_key == period_key) & (b.segment_key == seg_key)].sort_values("step_order")
    labels, vals = list(d.driver), list(d.amount_eur_m)
    fig, ax = plt.subplots(figsize=(9, 4.2))
    run = 0
    for i, (l, v) in enumerate(zip(labels, vals)):
        if i == 0:
            ax.bar(i, v, color=GREY); run = v; ax.text(i, v, f"{v:,.0f}", ha="center", va="bottom")
        else:
            ax.bar(i, v, bottom=run if v >= 0 else run + v, color=POS if v >= 0 else NEG)
            ax.text(i, run + max(v, 0), f"{v:+,.0f}", ha="center", va="bottom"); run += v
    ax.bar(len(labels), run, color=BLUE); ax.text(len(labels), run, f"{run:,.0f}", ha="center", va="bottom")
    ax.set_xticks(range(len(labels) + 1)); ax.set_xticklabels(labels + ["Current revenue"], rotation=20, ha="right")
    lo = min(vals[0], run) * 0.93; ax.set_ylim(lo, max(vals[0], run) * 1.03)
    ax.set_ylabel("EUR m"); ax.set_title(title, loc="left", fontweight="bold")
    fig.tight_layout(); fig.savefig(IMG / fname, dpi=150); plt.close(fig)

waterfall("2026-Q3", "SEG01", "Air Liquide Group - Q3 2026 revenue bridge (EUR m)", "bridge_q3_2026_group.png")
waterfall("2025-FY", "SEG01", "Air Liquide Group - FY 2025 revenue bridge (EUR m)", "bridge_fy_2025_group.png")

# published vs comparable growth by quarter (as reported)
q = r[(r.segment_key == "SEG01") & (r.role == "Reported period")].merge(per, on="period_key")
q = q[q.period_type == "Quarter"].sort_values("sort_order")
fig, ax = plt.subplots(figsize=(9, 3.8)); x = range(len(q))
ax.bar([i - 0.2 for i in x], q.published_change_pct, 0.4, color=GREY, label="Published growth")
ax.bar([i + 0.2 for i in x], q.comparable_change_pct, 0.4, color=BLUE, label="Comparable growth")
ax.axhline(0, color="black", lw=0.8); ax.set_xticks(list(x)); ax.set_xticklabels(q.period)
ax.set_ylabel("%"); ax.legend(frameon=False)
ax.set_title("Group revenue growth: published vs comparable (as reported)", loc="left", fontweight="bold")
fig.tight_layout(); fig.savefig(IMG / "growth_published_vs_comparable.png", dpi=150); plt.close(fig)

# check results
s = chk.groupby(["check_type", "status"]).size().unstack(fill_value=0)
for col in ["OK", "Rounding", "Break"]:
    if col not in s: s[col] = 0
s = s[["OK", "Rounding", "Break"]].sort_values("OK")
fig, ax = plt.subplots(figsize=(9, 4))
s.plot.barh(stacked=True, color=[POS, "#f0ad4e", NEG], ax=ax)
ax.set_xlabel("Number of checks"); ax.set_ylabel(""); ax.legend(frameon=False, loc="lower right")
ax.set_title(f"{len(chk)} reconciliation checks: {(chk.status=='OK').sum()} exact, "
             f"{(chk.status=='Rounding').sum()} rounding, {(chk.status.isin(['Break','Investigate'])).sum()} breaks",
             loc="left", fontweight="bold")
fig.tight_layout(); fig.savefig(IMG / "check_results.png", dpi=150); plt.close(fig)
print("charts:", sorted(p.name for p in IMG.glob("*.png")))
