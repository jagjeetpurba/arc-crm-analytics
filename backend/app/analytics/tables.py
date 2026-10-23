"""Table widgets + exceptions register. All rows come from governed ERP data."""
from __future__ import annotations
from collections import Counter, defaultdict
from .common import d, is_open, is_status, norm


def test_manager(name, rules):
    n = (name or "").lower()
    return any(p in n for p in rules.get("test_manager_patterns", []))


def exceptions(data, rules, as_of, filters):
    opps = data.get("opportunities", [])
    ids = Counter(r.get("arc_opportunity_id") for r in opps)
    out = []

    def add(rule_key, r, severity, detail, exposure=None):
        rl = rules[rule_key]
        out.append({
            "rule_id": rl["id"], "rule": rl["label"], "source_field": rl["source_field"],
            "record": r.get("arc_opportunity_id") or r["guid"], "guid": r["guid"], "account": r.get("account_display"),
            "client_manager": r.get("client_manager"), "gp_exposure": exposure if exposure is not None else r.get("est_gp"),
            "severity": severity, "detail": detail, "as_of": as_of.isoformat(),
        })

    for r in opps:
        ec, cr = d(r.get("estimated_close")), d(r.get("created_on"))
        if is_open(r):
            if ec is None:
                add("open_without_close_date", r, rules["open_without_close_date"]["severity"], "No estimated close date; excluded from dated forecast")
            else:
                days = (as_of - ec).days
                ru = rules["overdue_open_deal"]
                if days >= ru["monitor_days"]:
                    sev = "Critical" if days >= ru["critical_days"] else "High" if days >= ru["high_days"] else "Monitor"
                    add("overdue_open_deal", r, sev, f"Estimated close {ec} is {days} days before as-of")
            if r.get("probability") is None:
                add("open_without_probability", r, rules["open_without_probability"]["severity"], "Probability blank; not defaulted")
            if not r.get("est_gp"):
                add("open_without_gp", r, rules["open_without_gp"]["severity"], "Estimated GP missing or zero", 0)
        if is_status(r, "won") and not r.get("actual_gp"):
            add("won_without_actual_gp", r, rules["won_without_actual_gp"]["severity"], "Won with no Actual GP", 0)
        if ec and cr and ec < cr:
            add("close_before_created", r, rules["close_before_created"]["severity"], f"Estimated close {ec} precedes created {cr}")
        if ids[r.get("arc_opportunity_id")] > 1:
            add("duplicate_business_id", r, rules["duplicate_business_id"]["severity"], f"{ids[r.get('arc_opportunity_id')]} records share this business id")
        if test_manager(r.get("client_manager"), rules):
            add("test_manager_record", r, rules["test_manager_record"]["severity"], f"Manager '{r.get('client_manager')}' looks like a test/system record")
    order = {"Critical": 0, "High": 1, "Monitor": 2}
    out.sort(key=lambda x: (order[x["severity"]], -(x["gp_exposure"] or 0)))
    return out


def filter_exceptions(rows, filters):
    f = filters or {}
    if f.get("client_manager"):
        rows = [r for r in rows if norm(r["client_manager"]) == norm(f["client_manager"])]
    return rows


def cm_scorecard(engine, rules, data, as_of, filters):
    cms = sorted({norm(r["client_manager"]) for r in data.get("opportunities", []) if r.get("client_manager")} |
                 {norm(g["goal_owner"]) for g in data.get("goals", []) if g.get("goal_owner")})
    exc = Counter(e["client_manager"] for e in exceptions(data, rules, as_of, {}))
    f = {k: v for k, v in (filters or {}).items() if k != "client_manager"}
    rows = []
    for cm in cms:
        ff = {**f, "client_manager": cm}
        g = lambda k: engine.run({"kpi": k}, ff)
        tgt, ach, opn, wtd, wr = g("quarterly_gp_target"), g("achieved_gp"), g("open_forecast_gp"), g("weighted_open_gp"), g("win_rate")
        rows.append({
            "client_manager": cm, "test_record": test_manager(cm, rules),
            "gp_target": tgt["value"] or None, "achieved_gp": ach["value"], "gap": (tgt["value"] - ach["value"]) if tgt["value"] else None,
            "open_gp": opn["value"], "weighted_open_gp": wtd["value"], "win_rate": wr["value"],
            "won": g("won_count")["value"], "lost": g("lost_count")["value"], "exceptions": exc.get(cm, 0),
        })
    sel = (filters or {}).get("client_manager")
    if sel:
        rows = [r for r in rows if norm(r["client_manager"]) == norm(sel)]
    rows.sort(key=lambda r: -(r["achieved_gp"] or 0))
    cols = [("client_manager", "Client manager", "text"), ("gp_target", "GP target", "aed"), ("achieved_gp", "Achieved GP", "aed"),
            ("gap", "Gap (target − achieved)", "aed"), ("open_gp", "Open GP", "aed"), ("weighted_open_gp", "Weighted open GP", "aed"),
            ("win_rate", "Win rate", "pct"), ("won", "Won", "int"), ("lost", "Lost", "int"), ("exceptions", "Exceptions", "int")]
    return {"columns": cols, "rows": rows,
            "note": "Target exists for one fiscal quarter only; achieved GP follows the selected period. Gap is flagged when periods differ."}


def pipeline_completeness(engine, rules, data, as_of, filters):
    rows_ = [r for r in data.get("opportunities", []) if is_open(r)]
    rows_, applied, ignored = engine.apply_filters("opportunities", rows_, {k: v for k, v in (filters or {}).items() if k != "period"}, None)
    def line(label, rule, pred, gp=lambda r: r.get("est_gp") or 0):
        hit = [r for r in rows_ if pred(r)]
        return {"check": label, "records": len(hit), "gp_exposure": sum(gp(r) for r in hit), "treatment": rule}
    rows = [
        line("Open deals (all)", "Reference total", lambda r: True),
        line("No estimated close date", "Counted separately; excluded from dated forecast (FR-11)", lambda r: not r.get("estimated_close")),
        line("Blank probability", "Reported, never defaulted (FR-12)", lambda r: r.get("probability") is None),
        line("Close date before as-of (overdue)", "Computed from date vs as-of, not a stored flag (FR-13)", lambda r: (e := d(r.get("estimated_close"))) is not None and e < as_of),
        line("Missing / zero estimated GP", "Listed as exceptions (DQ-02)", lambda r: not r.get("est_gp")),
    ]
    return {"columns": [("check", "Check", "text"), ("records", "Records", "int"), ("gp_exposure", "GP exposure", "aed"), ("treatment", "Treatment", "text")],
            "rows": rows, "note": f"As of {as_of}. Period filter not applied (open deals are not period-bound)."}


def closed_deals(engine, rules, data, as_of, filters):
    rows = [r for r in data.get("opportunities", []) if is_status(r, "won", "lost")]
    rows, applied, ignored = engine.apply_filters("opportunities", rows, filters, "actual_close")
    out = []
    for r in rows:
        cr, cl = d(r.get("created_on")), d(r.get("actual_close"))
        out.append({"record": r.get("arc_opportunity_id"), "account": r.get("account_display"), "client_manager": r.get("client_manager"),
                    "outcome": r.get("status_reason"), "closed": cl.isoformat() if cl else None,
                    "cycle_days": (cl - cr).days if cl and cr else None, "est_gp": r.get("est_gp"), "actual_gp": r.get("actual_gp"),
                    "vertical": r.get("vertical")})
    out.sort(key=lambda x: -(x["est_gp"] or 0))
    return {"columns": [("record", "Opportunity", "text"), ("account", "Account", "text"), ("client_manager", "Client manager", "text"),
                        ("outcome", "Outcome", "text"), ("closed", "Closed", "text"), ("cycle_days", "Cycle (days)", "int"),
                        ("est_gp", "Est. GP", "aed"), ("actual_gp", "Actual GP", "aed"), ("vertical", "Vertical", "text")],
            "rows": out, "note": "Loss reason and stage-at-loss are not recorded in the extract (FR-16).",
            "scope": {"record_count": len(out), "filters_applied": applied, "filters_ignored": ignored, "governing_date": "actual_close"}}


TABLES = {"cm_scorecard": cm_scorecard, "pipeline_completeness": pipeline_completeness, "closed_deals": closed_deals}
