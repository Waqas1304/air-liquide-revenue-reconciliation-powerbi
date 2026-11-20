"""
Builds the Power BI Project (PBIP) for the Air Liquide revenue bridge & reconciliation cockpit:
  powerbi/AirLiquide_Revenue_Cockpit.pbip
  powerbi/AirLiquide_Revenue_Cockpit.SemanticModel/  (star schema, DAX measures, RLS roles)
  powerbi/AirLiquide_Revenue_Cockpit.Report/         (3 report pages)
Open the .pbip file with Power BI Desktop, set the DataFolder parameter, then Refresh.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NAME = "AirLiquide_Revenue_Cockpit"
OUT = ROOT / "powerbi"
DEFAULT_FOLDER = r"C:\Users\waqas\Documents\air-liquide-finance-reconciliation\data\clean" + "\\"

# ---------------------------------------------------------------- tables
TABLES = {
    "dim_period": [("period_key", "string", "text"), ("period", "string", "text"), ("period_code", "string", "text"),
                   ("year", "int64", "Int64.Type"), ("period_type", "string", "text"),
                   ("quarter_num", "int64", "Int64.Type"), ("period_end_date", "dateTime", "date"),
                   ("sort_order", "int64", "Int64.Type")],
    "dim_segment": [("segment_key", "string", "text"), ("segment", "string", "text"), ("segment_type", "string", "text"),
                    ("parent_segment", "string", "text"), ("sort_order", "int64", "Int64.Type")],
    "dim_source": [("source_id", "string", "text"), ("source_document", "string", "text"),
                   ("publication_date", "dateTime", "date"), ("url", "string", "text"), ("official_page", "string", "text")],
    "fact_revenue": [("row_id", "int64", "Int64.Type"), ("source_id", "string", "text"), ("period_key", "string", "text"),
                     ("segment_key", "string", "text"), ("role", "string", "text"), ("revenue_eur_m", "double", "number"),
                     ("published_change_pct", "double", "number"), ("comparable_change_pct", "double", "number"),
                     ("is_reference", "int64", "Int64.Type"), ("note", "string", "text")],
    "fact_bridge": [("period_key", "string", "text"), ("segment_key", "string", "text"), ("driver", "string", "text"),
                    ("amount_eur_m", "double", "number"), ("is_derived", "int64", "Int64.Type"),
                    ("source_id", "string", "text"), ("note", "string", "text"), ("step_order", "int64", "Int64.Type")],
    "fact_checks": [("check_id", "string", "text"), ("check_type", "string", "text"), ("period_key", "string", "text"),
                    ("scope", "string", "text"), ("expected", "double", "number"), ("actual", "double", "number"),
                    ("unit", "string", "text"), ("difference", "double", "number"), ("status", "string", "text")],
}
SORT_BY = {("dim_period", "period"): "sort_order", ("dim_segment", "segment"): "sort_order",
           ("fact_bridge", "driver"): "step_order"}
HIDDEN = {"sort_order", "step_order", "row_id"}

# ---------------------------------------------------------------- measures (DAX)
M = {
 "fact_revenue": [
  ("Revenue (EUR m)", "CALCULATE ( SUM ( fact_revenue[revenue_eur_m] ), fact_revenue[is_reference] = 1 )", "#,0"),
  ("Revenue PY (EUR m)",
   "VAR _year = SELECTEDVALUE ( dim_period[year] )\nVAR _code = SELECTEDVALUE ( dim_period[period_code] )\nRETURN\n    CALCULATE ( [Revenue (EUR m)], REMOVEFILTERS ( dim_period ), dim_period[year] = _year - 1, dim_period[period_code] = _code )", "#,0"),
  ("Published Growth % (recalc)", "DIVIDE ( [Revenue (EUR m)] - [Revenue PY (EUR m)], [Revenue PY (EUR m)] )", "0.0%"),
  ("Published Growth % (as reported)",
   "DIVIDE ( CALCULATE ( MAX ( fact_revenue[published_change_pct] ), fact_revenue[role] = \"Reported period\" ), 100 )", "0.0%"),
  ("Comparable Growth % (as reported)",
   "DIVIDE ( CALCULATE ( MAX ( fact_revenue[comparable_change_pct] ), fact_revenue[role] = \"Reported period\" ), 100 )", "0.0%"),
  ("G&S Total (EUR m)", "CALCULATE ( [Revenue (EUR m)], REMOVEFILTERS ( dim_segment ), dim_segment[segment] = \"Gas & Services\" )", "#,0"),
  ("Sum of Regions (EUR m)", "CALCULATE ( [Revenue (EUR m)], REMOVEFILTERS ( dim_segment ), dim_segment[segment_type] = \"Region\" )", "#,0"),
  ("Sum of Business Lines (EUR m)", "CALCULATE ( [Revenue (EUR m)], REMOVEFILTERS ( dim_segment ), dim_segment[segment_type] = \"Business line\" )", "#,0"),
  ("Regions Check Diff (EUR m)", "[Sum of Regions (EUR m)] - [G&S Total (EUR m)]", "#,0;-#,0;0"),
  ("Business Lines Check Diff (EUR m)", "[Sum of Business Lines (EUR m)] - [G&S Total (EUR m)]", "#,0;-#,0;0"),
  ("Share of G&S %", "DIVIDE ( [Revenue (EUR m)], [G&S Total (EUR m)] )", "0.0%"),
  ("Publications Count", "DISTINCTCOUNT ( fact_revenue[source_id] )", "0"),
  ("Restatement Spread (EUR m)",
   "SUMX (\n    SUMMARIZE ( fact_revenue, fact_revenue[period_key], fact_revenue[segment_key] ),\n    CALCULATE ( MAX ( fact_revenue[revenue_eur_m] ) - MIN ( fact_revenue[revenue_eur_m] ) )\n)", "#,0"),
  ("Reconciliation Status",
   "VAR _d = MAX ( ABS ( [Regions Check Diff (EUR m)] ), ABS ( [Business Lines Check Diff (EUR m)] ) )\nRETURN\n    SWITCH ( TRUE (), ISBLANK ( [G&S Total (EUR m)] ), BLANK (), _d = 0, \"OK\", _d <= 2, \"Rounding\", \"Break\" )", None),
 ],
 "fact_bridge": [
  ("Bridge Amount (EUR m)", "SUM ( fact_bridge[amount_eur_m] )", "#,0"),
  ("Bridge Prior-year Revenue (EUR m)", "CALCULATE ( [Bridge Amount (EUR m)], fact_bridge[driver] = \"Prior-year revenue\" )", "#,0"),
  ("Bridge Current Revenue (EUR m)", "[Bridge Amount (EUR m)]", "#,0"),
  ("Currency Impact (EUR m)", "CALCULATE ( [Bridge Amount (EUR m)], fact_bridge[driver] = \"Currency\" )", "#,0"),
  ("Energy Impact (EUR m)", "CALCULATE ( [Bridge Amount (EUR m)], fact_bridge[driver] IN { \"Natural gas\", \"Electricity\" } )", "#,0"),
  ("Scope Impact (EUR m)", "CALCULATE ( [Bridge Amount (EUR m)], fact_bridge[driver] = \"Significant scope\" )", "#,0"),
  ("Comparable Growth (EUR m)", "CALCULATE ( [Bridge Amount (EUR m)], fact_bridge[driver] = \"Comparable growth\" )", "#,0"),
  ("Comparable Growth % (recalc)", "DIVIDE ( [Comparable Growth (EUR m)], [Bridge Prior-year Revenue (EUR m)] )", "0.00%"),
  ("Comparable Gap vs Reported (pts)", "( [Comparable Growth % (recalc)] - [Comparable Growth % (as reported)] ) * 100", "0.00"),
 ],
 "fact_checks": [
  ("Checks Total", "COUNTROWS ( fact_checks )", "0"),
  ("Checks OK", "CALCULATE ( COUNTROWS ( fact_checks ), fact_checks[status] = \"OK\" )", "0"),
  ("Checks Rounding", "CALCULATE ( COUNTROWS ( fact_checks ), fact_checks[status] = \"Rounding\" )", "0"),
  ("Checks Break", "CALCULATE ( COUNTROWS ( fact_checks ), fact_checks[status] IN { \"Break\", \"Investigate\" } )", "0"),
  ("Check Pass Rate %", "DIVIDE ( [Checks OK] + [Checks Rounding], [Checks Total] )", "0.0%"),
  ("Max Abs Difference", "MAXX ( fact_checks, ABS ( fact_checks[difference] ) )", "0.00"),
 ],
}

def m_expression(table, cols):
    types = ", ".join(f'{{"{c}", type {t}}}' if not t.startswith("Int64") else f'{{"{c}", Int64.Type}}' for c, _, t in cols)
    return [
        "let",
        f'    Source = Csv.Document(File.Contents(DataFolder & "{table}.csv"), [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),',
        "    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
        f'    Typed = Table.TransformColumnTypes(Promoted, {{{types}}}, "en-US")',
        "in",
        "    Typed",
    ]

tables = []
for t, cols in TABLES.items():
    columns = []
    for c, dtype, _ in cols:
        col = {"name": c, "dataType": dtype, "sourceColumn": c,
               "summarizeBy": "sum" if dtype in ("double",) and c not in ("published_change_pct", "comparable_change_pct") else "none"}
        if dtype == "dateTime":
            col["formatString"] = "yyyy-mm-dd"
        if (t, c) in SORT_BY:
            col["sortByColumn"] = SORT_BY[(t, c)]
        if c in HIDDEN or c.endswith("_key") and t.startswith("fact"):
            col["isHidden"] = True
        if c == "url" or c == "official_page":
            col["dataCategory"] = "WebUrl"
        columns.append(col)
    table = {"name": t, "columns": columns,
             "partitions": [{"name": t, "mode": "import", "source": {"type": "m", "expression": m_expression(t, cols)}}]}
    if t in M:
        table["measures"] = [dict(name=n, expression=e.split("\n"), **({"formatString": f} if f else {}))
                             for n, e, f in M[t]]
    tables.append(table)

relationships = []
for fact, keys in {"fact_revenue": ["period_key", "segment_key", "source_id"],
                   "fact_bridge": ["period_key", "segment_key"],
                   "fact_checks": ["period_key"]}.items():
    for k in keys:
        dim = {"period_key": "dim_period", "segment_key": "dim_segment", "source_id": "dim_source"}[k]
        relationships.append({"name": f"{fact}_{k}", "fromTable": fact, "fromColumn": k, "toTable": dim, "toColumn": k})

roles = [{"name": f"Regional Controller - {r}", "modelPermission": "read",
          "tablePermissions": [{"name": "dim_segment", "filterExpression": f'dim_segment[segment] = "{r}"'},
                               {"name": "fact_checks", "filterExpression": f'fact_checks[scope] = "{r}"'}]}
         for r in ["Americas", "EMEA", "Asia Pacific"]]

folder_literal = DEFAULT_FOLDER.replace("\\", "\\\\") if False else DEFAULT_FOLDER
model = {
    "compatibilityLevel": 1567,
    "model": {
        "culture": "en-US",
        "dataAccessOptions": {"legacyRedirects": True, "returnErrorValuesAsNull": True},
        "defaultPowerBIDataSourceVersion": "powerBI_V3",
        "sourceQueryCulture": "en-US",
        "tables": tables,
        "relationships": relationships,
        "roles": roles,
        "expressions": [{"name": "DataFolder", "kind": "m",
                         "expression": f'"{folder_literal}" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]'}],
        "annotations": [{"name": "PBI_QueryOrder", "value": json.dumps(["DataFolder"] + list(TABLES))},
                        {"name": "__PBI_TimeIntelligenceEnabled", "value": "0"}],
    },
}

sm = OUT / f"{NAME}.SemanticModel"
rp = OUT / f"{NAME}.Report"
sm.mkdir(parents=True, exist_ok=True)
rp.mkdir(parents=True, exist_ok=True)
(sm / "model.bim").write_text(json.dumps(model, indent=2), encoding="utf-8")
(sm / "definition.pbism").write_text(json.dumps({"version": "1.0", "settings": {}}, indent=2), encoding="utf-8")
(OUT / f"{NAME}.pbip").write_text(json.dumps(
    {"version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}], "settings": {"enableAutoRecovery": True}},
    indent=2), encoding="utf-8")
(rp / "definition.pbir").write_text(json.dumps(
    {"version": "1.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}, "byConnection": None}},
    indent=2), encoding="utf-8")

# ---------------------------------------------------------------- report pages
ALIAS = {"dim_period": "p", "dim_segment": "s", "dim_source": "src", "fact_revenue": "r", "fact_bridge": "b", "fact_checks": "c"}
MEASURE_TABLE = {n: t for t, ms in M.items() for n, _, _ in ms}

def field(ref):
    """'table.column' for columns, a bare measure name for measures."""
    if ref in MEASURE_TABLE:
        t = MEASURE_TABLE[ref]
        return t, {"Measure": {"Expression": {"SourceRef": {"Source": ALIAS[t]}}, "Property": ref}, "Name": f"{t}.{ref}"}
    t, c = ref.split(".", 1)
    return t, {"Column": {"Expression": {"SourceRef": {"Source": ALIAS[t]}}, "Property": c}, "Name": f"{t}.{c}"}

def visual(vid, vtype, x, y, w, h, roles, title=None, filters=None):
    used, select, projections = [], [], {}
    for role, refs in roles.items():
        projections[role] = []
        for ref in refs:
            t, sel = field(ref)
            if t not in used:
                used.append(t)
            if sel["Name"] not in [s["Name"] for s in select]:
                select.append(sel)
            projections[role].append({"queryRef": sel["Name"]})
    sv = {"visualType": vtype, "projections": projections,
          "prototypeQuery": {"Version": 2, "From": [{"Name": ALIAS[t], "Entity": t, "Type": 0} for t in used],
                             "Select": select},
          "drillFilterOtherVisuals": True}
    if title:
        sv["vcObjects"] = {"title": [{"properties": {
            "show": {"expr": {"Literal": {"Value": "true"}}},
            "text": {"expr": {"Literal": {"Value": "'" + title.replace("'", "''") + "'"}}}}}]}
    config = {"name": vid, "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": 0, "width": w, "height": h}}],
              "singleVisual": sv}
    return {"config": json.dumps(config), "filters": json.dumps(filters or []), "x": x, "y": y, "z": 0,
            "width": w, "height": h}

def textbox(vid, x, y, w, h, text, size="14pt", bold=True):
    config = {"name": vid, "layouts": [{"id": 0, "position": {"x": x, "y": y, "z": 0, "width": w, "height": h}}],
              "singleVisual": {"visualType": "textbox", "drillFilterOtherVisuals": True,
                               "objects": {"general": [{"properties": {"paragraphs": [{"textRuns": [
                                   {"value": text, "textStyle": {"fontSize": size, "fontWeight": "bold" if bold else "normal"}}]}]}}]}}}
    return {"config": json.dumps(config), "filters": "[]", "x": x, "y": y, "z": 0, "width": w, "height": h}

def page(name, display, visuals):
    return {"name": name, "displayName": display, "displayOption": 1, "width": 1280, "height": 720,
            "config": "{}", "filters": "[]", "visualContainers": visuals}

pages = [
    page("p1_bridge", "1. Revenue Bridge", [
        textbox("t1", 20, 10, 1240, 40, "Revenue bridge: from prior-year to current revenue (EUR m) - Air Liquide published data"),
        visual("sl_period", "slicer", 20, 60, 220, 300, {"Values": ["dim_period.period"]}, "Period"),
        visual("sl_scope", "slicer", 20, 370, 220, 140, {"Values": ["dim_segment.segment"]}, "Scope (Group / Gas & Services)"),
        visual("wf", "waterfallChart", 260, 60, 680, 450, {"Category": ["fact_bridge.driver"], "Y": ["Bridge Amount (EUR m)"]},
               "Prior-year revenue -> drivers -> current revenue"),
        visual("k1", "card", 960, 60, 300, 105, {"Values": ["Currency Impact (EUR m)"]}, "Currency impact"),
        visual("k2", "card", 960, 175, 300, 105, {"Values": ["Energy Impact (EUR m)"]}, "Energy pass-through"),
        visual("k3", "card", 960, 290, 300, 105, {"Values": ["Scope Impact (EUR m)"]}, "Significant scope"),
        visual("k4", "card", 960, 405, 300, 105, {"Values": ["Comparable Growth % (recalc)"]}, "Comparable growth (recalculated)"),
        visual("tb", "tableEx", 20, 525, 1240, 180, {"Values": ["dim_period.period", "dim_segment.segment",
               "Bridge Prior-year Revenue (EUR m)", "Comparable Growth (EUR m)", "Comparable Growth % (recalc)",
               "Comparable Growth % (as reported)", "Comparable Gap vs Reported (pts)"]},
               "Check: recalculated comparable growth vs figure printed in the release"),
    ]),
    page("p2_recon", "2. Reconciliation", [
        textbox("t2", 20, 10, 1240, 40, "Reconciliation: do the published figures add up, roll up and stay stable across publications?"),
        visual("c1", "card", 20, 60, 230, 100, {"Values": ["Checks Total"]}, "Checks run"),
        visual("c2", "card", 260, 60, 230, 100, {"Values": ["Checks OK"]}, "Exact match"),
        visual("c3", "card", 500, 60, 230, 100, {"Values": ["Checks Rounding"]}, "Rounding (<= EUR 2m)"),
        visual("c4", "card", 740, 60, 230, 100, {"Values": ["Checks Break"]}, "Breaks to investigate"),
        visual("c5", "card", 980, 60, 280, 100, {"Values": ["Check Pass Rate %"]}, "Pass rate"),
        visual("mx", "pivotTable", 20, 175, 620, 260, {"Rows": ["fact_checks.check_type"], "Columns": ["fact_checks.status"],
               "Values": ["Checks Total"]}, "Results by check type"),
        visual("rc", "tableEx", 660, 175, 600, 260, {"Values": ["dim_period.period", "G&S Total (EUR m)", "Sum of Regions (EUR m)",
               "Regions Check Diff (EUR m)", "Sum of Business Lines (EUR m)", "Business Lines Check Diff (EUR m)",
               "Reconciliation Status"]}, "Live DAX check: segments vs Gas & Services total"),
        visual("dt", "tableEx", 20, 450, 1240, 255, {"Values": ["fact_checks.check_id", "fact_checks.check_type", "dim_period.period",
               "fact_checks.scope", "fact_checks.expected", "fact_checks.actual", "fact_checks.difference", "fact_checks.status"]},
               "Check log (drill-down)"),
    ]),
    page("p3_breakdown", "3. Revenue Breakdown", [
        textbox("t3", 20, 10, 1240, 40, "Gas & Services revenue by region and business line (quarterly, EUR m)"),
        visual("sl_type", "slicer", 20, 60, 220, 160, {"Values": ["dim_segment.segment_type"]}, "Segment type"),
        visual("sl_ptype", "slicer", 20, 230, 220, 160, {"Values": ["dim_period.period_type"]}, "Period type"),
        visual("col", "clusteredColumnChart", 260, 60, 1000, 330, {"Category": ["dim_period.period"], "Series": ["dim_segment.segment"],
               "Y": ["Revenue (EUR m)"]}, "Revenue by period and segment"),
        visual("mt", "pivotTable", 20, 405, 1240, 300, {"Rows": ["dim_segment.segment"], "Columns": ["dim_period.period"],
               "Values": ["Revenue (EUR m)", "Published Growth % (recalc)"]}, "Revenue and published growth (recalculated)"),
    ]),
]

report = {
    "config": json.dumps({"version": "5.43", "themeCollection": {}, "activeSectionIndex": 0,
                          "defaultDrillFilterOtherVisuals": True, "linguisticSchemaSyncVersion": 0,
                          "settings": {"useNewFilterPaneExperience": True, "allowChangeFilterTypes": True,
                                       "useStylableVisualContainerHeader": True, "exportDataMode": 1},
                          "objects": {}}),
    "layoutOptimization": 0,
    "sections": [dict(p, ordinal=i) for i, p in enumerate(pages)],
}
(rp / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

# human-readable copy of every measure for the README / interview
lines = ["// DAX measures used in the AirLiquide_Revenue_Cockpit semantic model", ""]
for t, ms in M.items():
    lines.append(f"// ===== table: {t} =====")
    for n, e, f in ms:
        lines += [f"{n} =", "    " + e.replace("\n", "\n    "), ""]
lines.append("// ===== RLS roles (Modeling > Manage roles) =====")
for r in roles:
    lines.append(f"// {r['name']}: " + " ; ".join(f"{tp['name']} -> {tp['filterExpression']}" for tp in r["tablePermissions"]))
(OUT / "measures.dax").write_text("\n".join(lines), encoding="utf-8")
print("PBIP written to", OUT)
