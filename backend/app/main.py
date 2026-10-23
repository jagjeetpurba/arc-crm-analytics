from __future__ import annotations
import asyncio, json, tempfile, uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse
from . import config
from .analytics import predict
from .analytics.tables import TABLES, exceptions, filter_exceptions
from .ingest.loader import load_workbook_into_erp
from .state import get_state, start_watcher

from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(_):
    get_state()
    start_watcher()
    yield


app = FastAPI(title="ARC CRM Analytics API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
RESERVED = {"key", "limit", "severity", "rule"}


def write_auth(x_api_key: str | None = Header(default=None)):
    import os
    need = os.getenv("WRITE_API_KEY")
    if need and x_api_key != need:
        raise HTTPException(401, "write endpoints need X-API-Key")


def filters_of(request: Request) -> dict:
    return {k: v for k, v in request.query_params.items() if k not in RESERVED and v not in ("", "all")}


# ------------------------------------------------------------------ meta
@app.get("/api/health")
def health():
    s = get_state()
    return {"ok": True, "erp_mode": config.ERP_MODE, "version": s.version, "as_of": s.as_of.isoformat()}


@app.get("/api/spec")
def spec():
    s = get_state()
    curated = s.dash
    return {"title": curated["title"], "version": s.version, "spec_hash": s.spec_hash, "as_of": s.as_of.isoformat(),
            "last_sync_at": s.last_sync_at, "filters": s.options(), "global_filters": curated["global_filters"],
            "pages": s.all_pages(), "kpis": {k: {kk: v.get(kk) for kk in ("id", "label", "format", "definition", "exclusions", "date_field")} for k, v in s.kpis["kpis"].items()},
            "currency": s.schema.get("currency", "AED")}


@app.get("/api/explain/{kpi}")
def explain(kpi: str):
    s = get_state()
    k = s.kpis["kpis"].get(kpi)
    if not k:
        raise HTTPException(404)
    return {"kpi": kpi, **{x: k.get(x) for x in ("id", "label", "definition", "exclusions", "date_field", "dataset", "ratio")}}


# ------------------------------------------------------------------ data
def run_widget(w, filters):
    s = get_state()
    e = s.engine
    t = w["type"]
    if t == "kpi_strip":
        items = [{"id": k, **e.run({"kpi": k}, filters)} for k in w.get("kpis", [])]
        items += [{"id": f"inline{i}", **e.run(x["query"], filters), "label": x["label"], "format": x.get("format", "num")} for i, x in enumerate(w.get("inline", []))]
        flag = None
        tg = next((i for i in items if i["id"] == "quarterly_gp_target"), None)
        ac = next((i for i in items if i["id"] == "achieved_gp"), None)
        if tg and ac:
            p = filters.get("period")
            dflt = s.options()["period"]["default"]
            if p != dflt:
                flag = f"Target is for {dflt}; achieved GP follows period '{p or 'all'}'. Comparison percentage withheld (FR-03)."
            elif tg["value"]:
                ac["vs_target"] = ac["value"] / tg["value"]
                ac["gap"] = tg["value"] - ac["value"]
        return {"items": items, "comparison_flag": flag}
    if t in ("bar", "line"):
        return e.run(w["query"], filters)
    if t == "table":
        return TABLES[w["table"]](e, s.rules, s.data, s.as_of, filters)
    if t == "exceptions":
        return exceptions_payload(filters, None, None)
    if t.startswith("predict_"):
        return predict.indicators(s.model, s.data, s.as_of, filters)
    raise HTTPException(400, f"unknown widget type {t}")


def exceptions_payload(filters, severity, rule):
    s = get_state()
    allrows = exceptions(s.data, s.rules, s.as_of, filters)
    rows = filter_exceptions(allrows, filters)
    total = len(rows)
    if severity:
        rows = [r for r in rows if r["severity"] == severity]
    if rule:
        rows = [r for r in rows if r["rule_id"] == rule]
    return {"rows": rows[:1000], "filtered_count": len(rows), "total_count": total,
            "by_severity": {k: sum(r["severity"] == k for r in filter_exceptions(allrows, filters)) for k in ("Critical", "High", "Monitor")},
            "rules": sorted({(r["rule_id"], r["rule"]) for r in allrows}), "as_of": s.as_of.isoformat(),
            "scope": {"record_count": total, "as_of": s.as_of.isoformat(), "exclusions": "Rule-based signals; not scores of a person (FR-20)",
                      "filters_applied": {"client_manager": filters["client_manager"]} if filters.get("client_manager") else {}, "filters_ignored": {}}}


@app.get("/api/widget/{wid}")
def widget(wid: str, request: Request):
    s = get_state()
    w = s.find_widget(wid)
    if not w:
        raise HTTPException(404, f"widget {wid}")
    return {"id": wid, "data_version": s.version, **{"payload": run_widget(w, filters_of(request))}}


@app.get("/api/exceptions")
def exc(request: Request, severity: str | None = None, rule: str | None = None):
    return exceptions_payload(filters_of(request), severity, rule)


@app.get("/api/drill/{kpi}")
def drill(kpi: str, request: Request, key: str | None = None, group_by: str | None = None):
    s = get_state()
    q = {"kpi": kpi, **({"group_by": group_by} if group_by else {})}
    res = s.engine.records(q, filters_of(request), key)
    rows = [{k: v for k, v in r.items()} for r in res["rows"]]
    return {"columns": list(rows[0].keys()) if rows else [], "rows": rows, "total": res["total"], "scope": res["scope"]}


@app.get("/api/records/{obj}")
def records(obj: str, request: Request, q: str | None = None, limit: int = 50):
    """Read-only record lookup for the assistant agent. Any other query param = exact (trimmed, case-insensitive) match on that field.
    `q` = substring match across text fields. Always reads the live governed data (never a stale cache of a chat)."""
    s = get_state()
    if obj not in s.data or obj == "agent_action":
        raise HTTPException(404, f"unknown object {obj}")
    eq = {k: v for k, v in request.query_params.items() if k not in ("q", "limit")}
    rows = s.data[obj]
    for k, v in eq.items():
        rows = [r for r in rows if str(r.get(k, "")).strip().lower() == v.strip().lower()]
    if q:
        ql = q.lower()
        rows = [r for r in rows if any(ql in str(x).lower() for x in r.values() if isinstance(x, str))]
    return {"object": obj, "total": len(rows), "rows": rows[:min(limit, 200)],
            "scope": {"as_of": s.as_of.isoformat(), "data_version": s.version, "last_sync_at": s.last_sync_at, "filters_applied": eq | ({"q": q} if q else {})}}


# ------------------------------------------------------------------ sync / healing-agent API
@app.get("/api/sync/status")
def sync_status():
    s = get_state()
    return {"version": s.version, "last_sync_at": s.last_sync_at, "served_token": s.token, "drift": s.drift(),
            "as_of": s.as_of.isoformat(), "recent_events": s.events[-10:]}


@app.post("/api/sync/heal", dependencies=[Depends(write_auth)])
def heal(reason: str = "healing-agent"):
    """Called by the Airgen healing agent when it detects ERP != screen. Idempotent."""
    return get_state().refresh(reason=reason)


@app.get("/api/events")
async def events(request: Request):
    s = get_state()
    async def gen():
        seen = s.version
        yield {"event": "hello", "data": json.dumps({"version": seen, "spec_hash": s.spec_hash})}
        while True:
            if await request.is_disconnected():
                return
            if s.version != seen:
                seen = s.version
                yield {"event": "data_version", "data": json.dumps(s.events[-1])}
            await asyncio.sleep(1.5)
    return EventSourceResponse(gen(), ping=20)


# ------------------------------------------------------------------ ingestion
@app.post("/api/ingest/xlsx", dependencies=[Depends(write_auth)])
async def ingest_xlsx(file: UploadFile = File(...)):
    s = get_state()
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as t:
        t.write(await file.read())
    try:
        report = load_workbook_into_erp(Path(t.name), s.erp, s.schema)
    except Exception as e:
        raise HTTPException(422, f"ingest failed: {e}")
    ev = s.refresh(reason=f"ingest:{file.filename}")
    return {"report": report, "sync": ev}


@app.post("/api/snapshots/capture", dependencies=[Depends(write_auth)])
def capture_snapshot():
    """Append-only monthly snapshot of open opportunities (BRD §9.2 / Phase 3 prerequisite)."""
    s = get_state()
    today = s.as_of.isoformat()
    rows = [{"snapshot_key": f"{today}|{r['guid']}", "snapshot_date": today, "opportunity_guid": r["guid"], "client_manager": r.get("client_manager"),
             "stage": r.get("stage"), "forecast_category": r.get("forecast_category"), "probability": r.get("probability"),
             "est_gp": r.get("est_gp"), "estimated_close": r.get("estimated_close")}
            for r in s.data.get("opportunities", []) if (r.get("status_reason") or "").lower() == "in progress"]
    n = s.erp.append("opportunity_snapshots", rows)
    s.refresh(reason="snapshot")
    return {"snapshot_date": today, "captured": n, "open_deals": len(rows)}


@app.post("/api/audit", dependencies=[Depends(write_auth)])
async def audit(request: Request):
    """Agents log every action here (NFR-09)."""
    b = await request.json()
    row = {"action_id": b.get("action_id") or uuid.uuid4().hex, "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "agent": b.get("agent"), "kind": b.get("kind"), "target_object": b.get("target_object"), "target_key": b.get("target_key"),
           "before_json": json.dumps(b.get("before")), "after_json": json.dumps(b.get("after")), "outcome": b.get("outcome"), "prompt": b.get("prompt")}
    get_state().erp.upsert("agent_action", [row], source="audit")
    return {"ok": True, "action_id": row["action_id"]}


@app.get("/api/audit")
def audit_list(limit: int = 100):
    rows = get_state().erp.fetch("agent_action")
    return sorted(rows, key=lambda r: r.get("ts") or "", reverse=True)[:limit]
