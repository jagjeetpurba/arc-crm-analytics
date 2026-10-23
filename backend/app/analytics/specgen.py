"""Dashboard auto-extension. Looks at what is actually in the ERP and adds
widgets/filters for anything the curated dashboard.yaml does not already cover:
  * dynamic fields (new columns the client started sending) on any object
  * whole objects that have no curated page (leads, appointments, accounts, ... or a brand-new one)
No code change or redeploy is needed — the frontend just re-reads /api/spec.
"""
from __future__ import annotations
from collections import Counter

SYSTEM_OBJECTS = {"opportunity_snapshots", "agent_action", "activity_types"}
MAX_DIM_CARD = 30
ID_HINTS = ("guid", "_id", "name", "regarding", "account_display", "company", "display")


def _kind(values, name):
    nn = [v for v in values if v not in (None, "")]
    if not nn:
        return None, 0
    if all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in nn):
        return "measure", len(set(nn))
    if all(isinstance(v, str) and len(v) >= 10 and v[4:5] == "-" and v[:4].isdigit() for v in nn):
        return "date", len(set(nn))
    card = len(set(map(str, nn)))
    if 2 <= card <= MAX_DIM_CARD and not any(h in name for h in ID_HINTS):
        return "dimension", card
    return "text", card


def profile(data: dict, schema: dict):
    prof = {}
    for obj, rows in data.items():
        if not rows:
            continue
        decl = set(schema["objects"].get(obj, {}).get("columns", {}))
        cols = {}
        for c in rows[0].keys() | {k for r in rows[:200] for k in r}:
            k, card = _kind([r.get(c) for r in rows], c)
            if k:
                cols[c] = {"kind": k, "distinct": card, "dynamic": c not in decl, "fill": sum(r.get(c) not in (None, "") for r in rows) / len(rows)}
        prof[obj] = cols
    return prof


def generate(data, schema, curated, kpis):
    prof = profile(data, schema)
    referenced = {k.get("dataset") for k in kpis["kpis"].values() if k.get("dataset")}
    widgets, filters = [], []
    for obj, cols in prof.items():
        if obj in SYSTEM_OBJECTS:
            continue
        label = schema["objects"].get(obj, {}).get("label", obj)
        new_obj = obj not in schema["objects"]
        curated_obj = obj in referenced
        dims = [c for c, p in cols.items() if p["kind"] == "dimension" and ((p["dynamic"] and curated_obj) or not curated_obj)]
        meas = [c for c, p in cols.items() if p["kind"] == "measure" and ((p["dynamic"] and curated_obj) or not curated_obj)]
        dates = [c for c, p in cols.items() if p["kind"] == "date"]
        if not dims and not meas:
            continue
        for c in dims:
            if cols[c]["dynamic"]:
                filters.append({"name": c, "label": c.replace("_", " ").title(), "source": obj})
        ws = [{"id": f"auto_{obj}_count", "type": "kpi_strip", "width": 12, "auto": True,
               "kpis": [], "inline": [{"label": f"{label} records", "query": {"dataset": obj, "agg": "count"}, "format": "int"}] +
                       [{"label": f"{c.replace('_',' ')} (sum)", "query": {"dataset": obj, "agg": "sum", "field": c}, "format": "num"} for c in meas[:3]]}]
        for c in dims[:4]:
            ws.append({"id": f"auto_{obj}_{c}", "type": "bar", "width": 6, "auto": True,
                       "title": f"{label}s by {c.replace('_', ' ')}", "query": {"dataset": obj, "agg": "count", "group_by": c, "order": "value", "top": 15}})
        if dates:
            ws.append({"id": f"auto_{obj}_{dates[0]}_m", "type": "bar", "width": 6, "auto": True,
                       "title": f"{label}s by {dates[0].replace('_', ' ')} month", "query": {"dataset": obj, "agg": "count", "group_by": f"{dates[0]}:month", "order": "key"}})
        tag = "NEW OBJECT" if new_obj else ("new fields" if curated_obj else "auto-generated")
        widgets.append({"object": obj, "label": label, "tag": tag, "widgets": ws})
    return {"pages": [{"id": f"auto_{w['object']}", "title": w["label"] + "s" if not w["label"].endswith("s") else w["label"],
                       "question": "Auto-generated from the data that is present in the ERP.", "auto": True, "tag": w["tag"],
                       "widgets": w["widgets"]} for w in widgets],
            "filters": filters, "profile": {o: {c: p["kind"] for c, p in cols.items()} for o, cols in prof.items()}}
