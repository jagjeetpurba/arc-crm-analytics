"""Declarative KPI/query engine. Every number returned carries a `scope` (FR-05 / UX-03)."""
from __future__ import annotations
from collections import defaultdict
from .common import d, norm, period_range

DIM_ALIASES = {"vertical": ["vertical", "business_vertical"]}


class Engine:
    def __init__(self, data: dict, schema: dict, kpis: dict, as_of):
        self.data, self.schema, self.kpis, self.as_of = data, schema, kpis, as_of

    # ---------- filter plumbing ----------
    def _fields(self, ds):
        rows = self.data.get(ds, [])
        return set(rows[0].keys()) if rows else set(self.schema["objects"][ds]["columns"])

    def _dim_field(self, ds, name):
        fields = self._fields(ds)
        if name == "client_manager":
            f = self.schema["objects"][ds].get("cm_field")
            return f if f in fields else None
        for c in DIM_ALIASES.get(name, [name]):
            if c in fields:
                return c
        return None

    def apply_filters(self, ds, rows, filters, date_field):
        applied, ignored, exclusions = {}, {}, []
        for name, val in (filters or {}).items():
            if val in (None, "", "all", []):
                continue
            if name == "period":
                rng = period_range(val)
                if not date_field or not rng:
                    ignored[name] = "no governing date" if not date_field else "unparseable"
                    continue
                s, e = rng
                rows = [r for r in rows if (x := d(r.get(date_field))) and s <= x <= e]
                applied[name] = f"{val} on {date_field}"
                continue
            f = self._dim_field(ds, name)
            if not f:
                ignored[name] = f"'{ds}' has no such field"
                continue
            vals = {norm(v) for v in (val if isinstance(val, list) else [val])}
            rows = [r for r in rows if norm(r.get(f)) in vals]
            applied[name] = f"{f} in {sorted(vals)}"
        return rows, applied, ignored

    @staticmethod
    def _where(rows, conds):
        def ok(r):
            for c in conds or []:
                v, op = r.get(c["field"]), c["op"]
                if op == "eq" and v != c["value"]: return False
                if op == "ne" and v == c["value"]: return False
                if op == "ci_eq" and (norm(v) or "").lower() != str(c["value"]).lower(): return False
                if op == "in" and v not in c["value"]: return False
                if op == "notnull" and v in (None, ""): return False
                if op == "isnull" and v not in (None, ""): return False
            return True
        return [r for r in rows if ok(r)]

    # ---------- group helpers ----------
    @staticmethod
    def _key(r, group_by):
        if not group_by:
            return "Total"
        f, _, grain = group_by.partition(":")
        v = r.get(f)
        if grain == "month":
            x = d(v)
            return x.strftime("%Y-%m") if x else "No date"
        v = norm(v)
        return v if v not in (None, "") else "(blank)"

    def _agg(self, q, rows):
        agg, f = q["agg"], q.get("field")
        if agg == "count":
            return float(len(rows)), len(rows)
        if agg == "sum":
            w = q.get("weight_field")
            vals = [(r[f] * (r[w] / 100 if w else 1)) for r in rows if isinstance(r.get(f), (int, float)) and (not w or isinstance(r.get(w), (int, float)))]
            return float(sum(vals)), len(vals)
        if agg == "avg_days":
            vals = [(d(r.get(f)) - d(r.get(q["from_field"]))).days for r in rows if d(r.get(f)) and d(r.get(q["from_field"]))]
            return (sum(vals) / len(vals) if vals else None), len(vals)
        raise ValueError(agg)

    # ---------- public ----------
    def resolve(self, q: dict) -> dict:
        base = dict(self.kpis["kpis"].get(q.get("kpi"), {})) if q.get("kpi") else {}
        merged = {**base, **{k: v for k, v in q.items() if k != "kpi"}}
        merged["kpi"] = q.get("kpi")
        return merged

    def run(self, q: dict, filters: dict | None = None) -> dict:
        q = self.resolve(q)
        if "ratio" in q:
            return self._run_ratio(q, filters)
        ds = q["dataset"]
        all_rows = self.data.get(ds, [])
        rows = self._where(all_rows, q.get("where"))
        rows, applied, ignored = self.apply_filters(ds, rows, filters, q.get("date_field"))
        gb = q.get("group_by")
        groups = defaultdict(list)
        for r in rows:
            groups[self._key(r, gb)].append(r)
        out = []
        for k, rs in groups.items():
            v, n = self._agg(q, rs)
            out.append({"key": k, "value": v, "count": len(rs), "n_valued": n})
        out = self._order(out, q)
        total, n_total = self._agg(q, rows)
        return {
            "kpi": q.get("kpi"), "label": q.get("label"), "format": q.get("format", "num"),
            "value": total, "rows": out if gb else None,
            "scope": self._scope(q, ds, len(rows), applied, ignored, filters),
        }

    def records(self, q: dict, filters: dict | None, key: str | None = None, limit: int = 500) -> dict:
        """Drill-through (FR-21): the rows behind a figure, with governing date and exclusions."""
        q = self.resolve(q)
        if "ratio" in q:
            q = self.resolve({"kpi": q["ratio"]["num"], **{k: v for k, v in q.items() if k in ("group_by",)}})
        ds = q["dataset"]
        rows = self._where(self.data.get(ds, []), q.get("where"))
        rows, applied, ignored = self.apply_filters(ds, rows, filters, q.get("date_field"))
        if key is not None and q.get("group_by"):
            rows = [r for r in rows if self._key(r, q["group_by"]) == key]
        return {"rows": rows[:limit], "total": len(rows), "scope": self._scope(q, ds, len(rows), applied, ignored, filters)}

    def _run_ratio(self, q, filters):
        num_id = q["ratio"]["num"]
        den_ids = q["ratio"]["den"] if isinstance(q["ratio"]["den"], list) else [q["ratio"]["den"]]
        gb = q.get("group_by")
        sub = lambda kid: self.run({"kpi": kid, **({"group_by": gb} if gb else {})}, filters)
        num, dens = sub(num_id), [sub(k) for k in den_ids]
        def ratio(n, ds_):
            den = sum(x or 0 for x in ds_)
            return (n / den) if den else None
        value = ratio(num["value"], [x["value"] for x in dens])
        rows = None
        if gb:
            keys = {r["key"] for r in num["rows"] or []} | {r["key"] for x in dens for r in x["rows"] or []}
            get = lambda res, k: next((r["value"] for r in res["rows"] if r["key"] == k), 0)
            rows = [{"key": k, "value": ratio(get(num, k), [get(x, k) for x in dens]),
                     "count": int(sum(get(x, k) for x in dens))} for k in keys]
            rows = self._order(rows, q)
        scope = dict(num["scope"])
        scope["record_count"] = int(sum(x["scope"]["record_count"] for x in dens))
        scope["definition"] = q.get("definition")
        return {"kpi": q.get("kpi"), "label": q.get("label"), "format": "pct", "value": value, "rows": rows, "scope": scope}

    @staticmethod
    def _order(rows, q):
        o = q.get("order")
        if o == "key":
            rows.sort(key=lambda r: r["key"])
        elif o == "value":
            rows.sort(key=lambda r: -(r["value"] or 0))
        if q.get("top"):
            rows = rows[: q["top"]]
        return rows

    def _scope(self, q, ds, n, applied, ignored, filters):
        return {
            "dataset": ds, "record_count": n, "governing_date": q.get("date_field"),
            "definition": q.get("definition"), "exclusions": q.get("exclusions"),
            "filters_applied": applied, "filters_ignored": ignored,
            "period": (filters or {}).get("period"), "as_of": self.as_of.isoformat() if self.as_of else None,
        }
