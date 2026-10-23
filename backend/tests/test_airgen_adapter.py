"""AirgenERP against a fake Twenty REST server (shapes as reported by the Airgen Operator)."""
import json, re, uuid
from datetime import datetime, timezone
import httpx, pytest
from tests.conftest import WORKBOOK


class FakeTwenty:
    def __init__(self):
        self.store = {}     # plural -> {id: rec}
        self.calls = []

    def _now(self):
        return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def __call__(self, req: httpx.Request):
        self.calls.append((req.method, req.url.path))
        path = req.url.path.replace("/rest", "", 1)
        q = dict(req.url.params)
        m = re.fullmatch(r"/batch/(\w+)", path)
        if m and req.method == "POST":
            out = []
            for rec in json.loads(req.content):
                rec = {**rec, "id": str(uuid.uuid4()), "createdAt": self._now(), "updatedAt": self._now(), "deletedAt": None, "name": ""}
                self.store.setdefault(m[1], {})[rec["id"]] = rec; out.append(rec)
            return httpx.Response(201, json={"data": {"createX": out}})
        m = re.fullmatch(r"/(\w+)/groupBy", path)
        if m:
            recs = list(self.store.get(m[1], {}).values())
            return httpx.Response(200, json={"data": {"groupBy": [{"countNotEmptyId": len(recs), "maxUpdatedAt": max((r["updatedAt"] for r in recs), default=None)}]}})
        m = re.fullmatch(r"/(\w+)/([\w-]+)", path)
        if m and req.method == "PATCH":
            rec = self.store[m[1]][m[2]]; rec.update(json.loads(req.content)); rec["updatedAt"] = self._now()
            return httpx.Response(200, json={"data": {"updateX": rec}})
        m = re.fullmatch(r"/(\w+)", path)
        if m and req.method == "GET":
            recs = sorted(self.store.get(m[1], {}).values(), key=lambda r: r["id"])
            limit, cur = int(q.get("limit", 60)), q.get("starting_after")
            start = next((i + 1 for i, r in enumerate(recs) if r["id"] == cur), 0) if cur else 0
            page = recs[start:start + limit]
            more = start + limit < len(recs)
            return httpx.Response(200, json={"data": {m[1]: page}, "pageInfo": {"hasNextPage": more, "endCursor": page[-1]["id"] if page else None}, "totalCount": len(recs)})
        return httpx.Response(404)


@pytest.fixture
def erp():
    import yaml
    from app import config
    from app.erp.airgen import AirgenERP
    fake = FakeTwenty()
    e = AirgenERP(transport=httpx.MockTransport(fake))
    e.ensure_schema(yaml.safe_load((config.SPEC_DIR / "erp_schema.yaml").read_text()))
    e.fake = fake
    return e


def test_roundtrip_idempotent_and_drift(erp):
    from app.ingest.loader import load_workbook_into_erp
    rep = load_workbook_into_erp(WORKBOOK, erp, erp.schema)
    assert rep["opportunities"]["inserted"] == 563 and rep["goals"]["inserted"] == 28
    again = load_workbook_into_erp(WORKBOOK, erp, erp.schema)
    assert all(r["inserted"] == 0 and r["updated"] == 0 for r in again.values()), again
    rows = erp.fetch("opportunities")
    assert len(rows) == 563 and sum(r["est_gp"] or 0 for r in rows) > 0
    ex = next(r for r in rows if r["arc_opportunity_id"] == "2026-O-00231")
    assert ex["estimated_close"] == "2026-06-01" and ex["created_on"].startswith("2026-04-01")
    # drift: an edit in the ERP changes the fingerprint
    t0 = erp.change_token()
    erp.upsert("opportunities", [{**ex, "est_gp": ex["est_gp"] + 5}], "edit")
    t1 = erp.change_token()
    assert t0["opportunities"] != t1["opportunities"] and t0["goals"] == t1["goals"]


def test_unknown_columns_go_to_dynamic_fields(erp):
    erp.upsert("opportunities", [{"guid": "g1", "arc_opportunity_id": "X", "sales_region": "North", "est_gp": 1.0}], "t")
    raw = next(iter(erp.fake.store["crmOpportunities"].values()))
    assert raw["dynamicFields"] == {"sales_region": "North"} and raw["arcOpportunityId"] == "X"
    assert erp.fetch("opportunities")[0]["sales_region"] == "North"
    assert {"object": "opportunities", "name": "sales_region", "type": "str"} in erp.dynamic_fields()


def test_webhook_triggers_refresh(client):
    from app.state import get_state
    import time
    s = get_state(); v = s.version
    row = next(r for r in s.data["opportunities"] if r["status_reason"] == "In Progress")
    s.erp.upsert("opportunities", [{**row, "est_gp": (row["est_gp"] or 0) + 7}], "edit")
    assert client.post("/api/webhooks/erp-change").json() == {"accepted": True}
    for _ in range(30):
        if s.version > v: break
        time.sleep(0.2)
    assert s.version > v


def test_429_is_retried(erp, monkeypatch):
    import time as _t
    from app.erp import airgen
    monkeypatch.setattr(airgen.config, "AIRGEN_MAX_RPM", 600)
    monkeypatch.setattr(_t, "sleep", lambda *_: None)
    calls = {"n": 0}
    inner = erp.http._transport

    def flaky(req):
        calls["n"] += 1
        return httpx.Response(429, json={"statusCode": 429}, headers={"retry-after": "1"}) if calls["n"] <= 2 else inner.handle_request(req)
    erp.http = httpx.Client(transport=httpx.MockTransport(flaky))
    assert erp.fetch("goals") == [] and calls["n"] == 3


def test_paging_guard_raises_instead_of_looping(erp):
    """An ERP that ignores the cursor returns page 1 forever; the adapter must fail loudly."""
    page = [{"id": f"id{i}", "guid": f"g{i}"} for i in range(3)]
    def stuck(req):
        return httpx.Response(200, json={"data": {"crmGoals": page}, "pageInfo": {"hasNextPage": True, "endCursor": "id2"}, "totalCount": 99})
    erp.http = httpx.Client(transport=httpx.MockTransport(stuck))
    with pytest.raises(RuntimeError, match="not advancing"):
        erp.fetch("goals")
