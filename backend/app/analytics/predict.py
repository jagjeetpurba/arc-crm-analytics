"""Model-assisted indicators (BRD Phase 3). Every output exposes its drivers and its limits.

1. Win probability  — logistic regression on closed deals (WON vs LOST), using only attributes that are not
   rewritten when a deal closes (size, margin, vertical). See EXCLUDED_AS_LEAKY for what was rejected and why.
2. Deal score       — P(win) x estimated GP, with the top drivers behind each deal.
3. Forecast         — expected GP by close month (overdue deals are slipped to the month after as-of),
                      compared with the CRM's own probability-weighted figure, plus a p10-p90 band
                      from 3,000 Bernoulli simulations.
"""
from __future__ import annotations
import math
from collections import Counter, defaultdict
import numpy as np
from .common import d, is_open, is_status, norm

MIN_PER_CLASS = 20
# Deliberately NOT used (outcome leakage, found by single-feature AUC on the pilot extract):
#  - planned cycle length (estimated_close - created_on): estimated close is edited as deals progress, so for closed
#    deals it already encodes the outcome (single-feature AUC 0.84 reversed).
#  - client manager != CRM owner: 100% of won vs 71% of lost deals differ -> the owner is changed when a deal is closed.
EXCLUDED_AS_LEAKY = ["planned_cycle_days", "manager_differs_from_owner", "stage", "probability", "forecast_category"]


def _feat(r, verticals):
    margin = (r["est_gp"] / r["est_revenue"]) if r.get("est_gp") and r.get("est_revenue") else None
    f = {
        "log_est_gp": math.log1p(max(r.get("est_gp") or 0, 0)),
        "gp_margin": margin,
    }
    for v in verticals:
        f[f"vertical = {v}"] = 1.0 if norm(r.get("vertical")) == v else 0.0
    return f


def train(data, as_of):
    opps = data.get("opportunities", [])
    closed = [r for r in opps if is_status(r, "won", "lost")]
    won = sum(is_status(r, "won") for r in closed)
    lost = len(closed) - won
    meta = {"n_closed": len(closed), "won": won, "lost": lost, "target": "WON vs LOST (cancelled / disqualified / on-hold excluded)"}
    if won < MIN_PER_CLASS or lost < MIN_PER_CLASS:
        return {"available": False, "reason": f"Need ≥{MIN_PER_CLASS} won and ≥{MIN_PER_CLASS} lost deals; have {won}/{lost}.", **meta}
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, cross_val_predict
    from sklearn.metrics import roc_auc_score
    top = [v for v, _ in Counter(norm(r.get("vertical")) for r in closed if r.get("vertical")).most_common(6)]
    rows = [_feat(r, top) for r in closed]
    names = list(rows[0])
    X = np.array([[np.nan if f[n] is None else f[n] for n in names] for f in rows], dtype=float)
    med = np.nanmedian(X, axis=0)
    med = np.where(np.isnan(med), 0, med)
    Xi = np.where(np.isnan(X), med, X)
    mu, sd = Xi.mean(0), Xi.std(0)
    sd[sd == 0] = 1
    Z = (Xi - mu) / sd
    y = np.array([1 if is_status(r, "won") else 0 for r in closed])
    clf = LogisticRegression(C=0.3, max_iter=1000)
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=7)
    auc = float(roc_auc_score(y, cross_val_predict(clf, Z, y, cv=cv, method="predict_proba")[:, 1]))
    clf.fit(Z, y)
    drivers = sorted(({"feature": n, "weight": float(w), "direction": "raises win odds" if w > 0 else "lowers win odds"}
                      for n, w in zip(names, clf.coef_[0])), key=lambda x: -abs(x["weight"]))
    return {"available": True, "clf": clf, "names": names, "med": med, "mu": mu, "sd": sd, "verticals": top,
            "cv_auc": auc, "excluded_as_leaky": EXCLUDED_AS_LEAKY, "base_rate": float(y.mean()), "drivers": drivers, **meta,
            "caveat": "Small pilot extract. Est. GP / margin may themselves be revised when a deal closes, so AUC can be optimistic — re-validate once monthly snapshots exist. Treat as directional."}


def _score_deals(model, data, as_of):
    rows = [r for r in data.get("opportunities", []) if is_open(r)]
    out = []
    for r in rows:
        f = _feat(r, model["verticals"])
        x = np.array([model["med"][i] if f[n] is None else f[n] for i, n in enumerate(model["names"])], dtype=float)
        z = (x - model["mu"]) / model["sd"]
        p = float(model["clf"].predict_proba(z.reshape(1, -1))[0, 1])
        contrib = sorted(zip(model["names"], z * model["clf"].coef_[0]), key=lambda t: -abs(t[1]))[:3]
        ec = d(r.get("estimated_close"))
        overdue = ec is not None and ec < as_of
        out.append({"record": r.get("arc_opportunity_id"), "guid": r["guid"], "account": r.get("account_display"),
                    "client_manager": r.get("client_manager"), "vertical": r.get("vertical"), "stage": r.get("stage"),
                    "est_gp": r.get("est_gp") or 0, "crm_probability": r.get("probability"),
                    "model_probability": p * 100, "expected_gp": (r.get("est_gp") or 0) * p,
                    "estimated_close": ec.isoformat() if ec else None, "overdue": overdue,
                    "drivers": [f"{n} ({'+' if v > 0 else '−'})" for n, v in contrib]})
    return out


def _month(r, as_of):
    ec = d(r["estimated_close"])
    if ec is None:
        return "No date"
    if ec < as_of:   # overdue: assume it slips to the month after as-of
        ny, nm = (as_of.year + (as_of.month == 12), as_of.month % 12 + 1)
        return f"{ny}-{nm:02d}"
    return ec.strftime("%Y-%m")


def indicators(model, data, as_of, filters):
    if not model.get("available"):
        return {"available": False, "reason": model.get("reason"), "meta": {k: model.get(k) for k in ("n_closed", "won", "lost")}}
    deals = _score_deals(model, data, as_of)
    f = filters or {}
    if f.get("client_manager"):
        deals = [x for x in deals if norm(x["client_manager"]) == norm(f["client_manager"])]
    if f.get("vertical"):
        deals = [x for x in deals if norm(x["vertical"]) == norm(f["vertical"])]
    by = defaultdict(lambda: {"expected_model": 0.0, "weighted_crm": 0.0, "pipeline_gp": 0.0, "deals": 0})
    for x in deals:
        m = by[_month(x, as_of)]
        m["expected_model"] += x["expected_gp"]
        m["weighted_crm"] += x["est_gp"] * (x["crm_probability"] or 0) / 100
        m["pipeline_gp"] += x["est_gp"]
        m["deals"] += 1
    rng = np.random.default_rng(11)
    p = np.array([x["model_probability"] / 100 for x in deals]) if deals else np.array([])
    g = np.array([x["est_gp"] for x in deals]) if deals else np.array([])
    sims = (rng.random((3000, len(p))) < p) @ g if len(p) else np.array([0.0])
    months = [{"month": k, **v} for k, v in sorted(by.items())]
    return {
        "available": True,
        "model": {k: model[k] for k in ("n_closed", "won", "lost", "target", "cv_auc", "base_rate", "caveat", "excluded_as_leaky")},
        "drivers": model["drivers"],
        "forecast": {"months": months,
                     "total_expected_model": float(sum(x["expected_gp"] for x in deals)),
                     "total_weighted_crm": float(sum(m["weighted_crm"] for m in months)),
                     "p10": float(np.percentile(sims, 10)), "p90": float(np.percentile(sims, 90)),
                     "note": "Overdue deals are slipped to the month after as-of. Band = p10–p90 of 3,000 simulated outcomes."},
        "deals": sorted(deals, key=lambda x: -x["expected_gp"]),
        "scope": {"record_count": len(deals), "as_of": as_of.isoformat(),
                  "filters_applied": {k: v for k, v in f.items() if k in ("client_manager", "vertical") and v},
                  "filters_ignored": {"period": "open deals are not period-bound"} if f.get("period") else {}},
    }
